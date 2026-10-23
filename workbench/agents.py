"""Agent definitions (config/agents.yaml) and the checks an agent's result must pass."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import ingest, tools
from .registry import ROOT

DEFAULT_CONFIG = ROOT / "config" / "agents.yaml"

WORKER = """You are the TITLE in a team of agents working on-premise for an industrial organisation.
Your job: JOB
Reply with exactly ONE JSON object and nothing else.

To use a tool:   {"thought": "<why>", "tool": "<tool name>", "args": {<arguments>}}
When finished:   {"thought": "<why>", "final": "<one or two sentences on what you did>", "facts": ["<fact>", "<fact>"]}

Rules: use one tool per reply. Do only your own job; other agents handle the rest.
Never invent numbers, names, dates or file contents: use only the request, the fact sheet, the documents and tool output.
A file exists only if a tool created it.
RULES
Tools:
TOOLS"""


@dataclass(frozen=True)
class AgentDef:
    name: str
    title: str
    order: int
    job: str
    capability: str
    tools: tuple[str, ...]
    checks: tuple[str, ...]
    default_goal: str
    rules: str = ""

    def system(self) -> str:
        return (WORKER.replace("TITLE", self.title).replace("JOB", self.job)
                .replace("RULES", self.rules.strip())
                .replace("TOOLS", tools.describe(only=self.tools) or "(none)"))


def load_agents(path: Path = DEFAULT_CONFIG) -> dict[str, AgentDef]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["agents"]
    defs = {}
    for name, a in raw.items():
        unknown = [c for c in a.get("checks", []) if c not in CHECKS] + [t for t in a["tools"] if t not in tools.TOOLS]
        if unknown:
            raise ValueError(f"agent '{name}' names unknown tools or checks: {unknown}")
        defs[name] = AgentDef(name=name, title=a["title"], order=a["order"], job=a["job"],
                              capability=a["capability"], tools=tuple(a["tools"]),
                              checks=tuple(a.get("checks", [])), default_goal=a["default_goal"],
                              rules=a.get("rules", ""))
    return dict(sorted(defs.items(), key=lambda kv: kv[1].order))


# ---- number grounding ----

# A quantity standing on its own. Digits inside a tag, a cell reference or a date (P-101A, B12, 28/9)
# are identifiers, not quantities, and are not checked.
NUM_RE = re.compile(r"(?<![A-Za-z\d.,/\-])\d[\d,]*(?:\.\d+)?(?![A-Za-z\d/])")
ANY_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")  # the sources are read generously: every run of digits counts
SCALES = (0, 3, -3, 6, -6, 2, -2)  # same value in another unit: Pa/kPa/MPa, fraction/percent


def _numbers(text: str, pattern: re.Pattern = NUM_RE) -> list[tuple[str, float]]:
    out = []
    for m in pattern.findall(text):
        s = m.replace(",", "")
        try:
            out.append((s, float(s)))
        except ValueError:
            pass
    return out


def ungrounded(text: str, sources: str) -> list[str]:
    """Numbers in `text` that appear nowhere in `sources`, allowing rounding and unit scale."""
    have = {v for _, v in _numbers(sources + " " + time.strftime("%d %m %Y"), ANY_NUM_RE)}
    bad = []
    for s, v in _numbers(text):
        if v == int(v) and 0 <= v <= 12:  # list numbering, small counts
            continue
        decimals = len(s.split(".")[1]) if "." in s else 0
        ok = any(abs(x - v * 10 ** k) <= 0.5 * 10 ** (k - decimals) + 1e-9 for k in SCALES for x in have)
        if not ok and s not in bad:
            bad.append(s)
    return bad


# ---- checks: each returns None when satisfied, or the correction to send back ----

@dataclass
class CheckContext:
    request: str
    answer: str
    facts: list[str]
    trace: list[dict]          # this agent's tool calls: {"tool", "args", "result"}
    sources: str               # everything a number may legitimately come from
    new_files: list[Path] = field(default_factory=list)
    known: list[str] = field(default_factory=list)  # every fact on the sheet so far


def facts_present(c: CheckContext):
    return None if c.facts else 'Put your findings in the "facts" list, one finding per item.'


def numbers_grounded(c: CheckContext):
    bad = ungrounded(" ".join([c.answer, *c.facts]), c.sources)
    if bad:
        return (f"These numbers are not in the source material: {', '.join(bad)}. Use only numbers from the "
                "documents, the fact sheet or tool output, or describe the point in words.")


def files_grounded(c: CheckContext):
    text = ""
    for f in c.new_files:
        try:
            text += " " + ingest.as_text(ingest.extract(f))
        except Exception:
            pass
    bad = ungrounded(text, c.sources)
    if bad:
        return (f"The file contains numbers that are not in the fact sheet or the request: {', '.join(bad)}. "
                "Create the file again without them, or describe those points in words.")


def file_created(c: CheckContext):
    if not c.new_files:
        return "No file was created. Create it with make_approval_note, make_docx, make_xlsx or make_pptx."


def code_ran(c: CheckContext):
    if not any(t["tool"] in ("run_python", "run_tests") and "exit=0" in t["result"] for t in c.trace):
        return "Nothing has run successfully yet. Run the code with run_python and use its output."


def tests_passed(c: CheckContext):
    runs = [t["result"] for t in c.trace if t["tool"] == "run_tests"]
    if runs:
        m = re.search(r"Ran (\d+) test", runs[-1])
        if m and int(m.group(1)) > 0 and re.search(r"^OK", runs[-1], re.M):
            return None
        return "The last test run did not pass. Fix the code or the test, then call run_tests again."
    if re.search(r"\btests?\b", c.request, re.I):
        return "Tests were asked for but run_tests was never called. Write the tests and run them."
    return code_ran(c)


CITE_RE = re.compile(r"\[([^\]\n]+?) p\.\d+\]")


def citations_real(c: CheckContext):
    searches = [t["result"] for t in c.trace if t["tool"] == "search_kb"]
    if not searches:
        return "Search the knowledge base with search_kb before answering."
    found = set(CITE_RE.findall(" ".join(searches)))
    if not found:
        return None if not c.facts else "The knowledge base returned nothing, so the facts list must be empty."
    for fact in c.facts:  # an empty list is accepted: the Researcher may find that no rule applies
        cited = CITE_RE.findall(fact)
        if not cited or any(doc not in found for doc in cited):
            return ("Every fact must end with its source exactly as search_kb returned it, "
                    f"for example [{sorted(found)[0]} p.1].")


REPORT_NO_RE = re.compile(r"\b(?:Report|Ref(?:erence)?|Doc(?:ument)?)\.?\s*(?:No|Number)\.?\s*[:\-]?\s*"
                          r"([A-Z0-9][A-Z0-9/\-]{3,})", re.I)
APPROVER_RE = re.compile(r"approved by (?:the )?([A-Z][A-Za-z]+(?: \(?[A-Z][A-Za-z]+\)?)*)")


def note_complete(c: CheckContext):
    """An approval note must carry the source report's number and name the approving authority."""
    calls = [t["args"] for t in c.trace if t["tool"] == "make_approval_note"]
    if not calls:
        return None
    args = calls[-1]
    numbers = list(dict.fromkeys(REPORT_NO_RE.findall(c.sources)))
    if numbers and not any(n.lower() in str(args.get("reference", "")).lower() for n in numbers):
        return (f'The reference of the note must be the report number "{numbers[0]}". '
                "Create the note again with that reference.")
    approvers = sorted(set(APPROVER_RE.findall(" ".join(c.known))))
    sought = str(args.get("approval_sought", "")).lower()
    if approvers and not any(a.lower() in sought for a in approvers):
        return ("The approval_sought section must name the approving authority given in the fact sheet "
                f"({' or '.join(approvers)}). Create the note again.")


CHECKS = {f.__name__: f for f in (facts_present, numbers_grounded, files_grounded, file_created,
                                  code_ran, tests_passed, citations_real, note_complete)}


def run_checks(names: tuple[str, ...], c: CheckContext) -> str | None:
    for name in names:
        problem = CHECKS[name](c)
        if problem:
            return problem
    return None
