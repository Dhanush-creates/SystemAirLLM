"""Agent loop: route -> read attachments -> (model reply -> tool call -> observation)* -> final answer.

Tool calls use a plain JSON protocol in the reply text, so the same loop works on
any model, from a 4B model to a 120B one.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from . import ingest, tools
from .audit import Audit
from .kb import KnowledgeBase
from .providers import build_providers
from .registry import ROOT, Registry
from .router import NoModelAvailable, Router, Task

SYSTEM = """You are an on-premise industrial work assistant. You complete tasks step by step using tools.
Reply with exactly ONE JSON object and nothing else.

To use a tool:   {"thought": "<why>", "tool": "<tool name>", "args": {<arguments>}}
When finished:   {"thought": "<why>", "final": "<answer for the user>"}

Rules: use one tool per reply. Read tool observations before deciding the next step.
Code goes in files made with write_file. After writing code, run it to verify it. Verify tests with run_tests only:
importing a test file does not run it. Code is verified only when the output shows tests ran and passed; if a test
fails, fix the code or the test and run again.
Never invent file contents, results, statistics or figures: use only numbers given in the request, the attachments,
the knowledge base or computed by a tool. If a number is not available, describe the point in words.
A file exists only if a tool created it. Never say a file was created unless a tool reported creating it.
When a document, spreadsheet or presentation is requested, create the real file with make_approval_note,
make_docx, make_xlsx or make_pptx; do not just describe it. Attached files are already shown to you below the request.
For company rules, manuals or SOPs use search_kb and cite sources as [document p.N].
For calculations, compute with run_python (print every intermediate value) and show the formula, the inputs and
each step in your answer, using only the numbers the tool printed.

Tools:
TOOLS"""

RETRY = "Invalid reply. Respond with exactly one JSON object in the specified format."
STUCK = ("\n\nYou already did exactly this and got the same result. Do not repeat it. Re-check your "
         "assumptions (an expected value in a test may itself be wrong: recompute it by hand) and try "
         "something different, or use a different tool. If the work is already done, give the final answer now.")
MAX_INVALID = 2  # invalid replies before escalating to a bigger model
MAX_STUCK = 3    # repeats with no bigger model to escalate to, before giving up
MAX_FAILURES = 3  # tool calls failing in a row count as going in circles
FILE_RE = re.compile(r"[\w\-]+\.(?:docx|xlsx|pptx|pdf|py|txt|csv|md|json)\b", re.I)
# Tool groups hidden per task type, so a small model is not tempted by the wrong tool.
HIDDEN = {"code": {"office"}}


def parse_action(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    if isinstance(obj, dict) and ("final" in obj or isinstance(obj.get("tool"), str)):
        return obj
    return None


def _fit(messages: list[dict], budget: int) -> None:
    """Drop the oldest exchange pairs until the history fits the model's context."""
    while len(messages) > 4 and sum(len(m["content"]) for m in messages) > budget:
        del messages[2:4]


class Agent:
    def __init__(self, registry: Registry, providers: dict | None = None,
                 workspace: Path | None = None, audit: Audit | None = None, max_steps: int = 20,
                 kb: KnowledgeBase | None = None):
        self.registry = registry
        self.providers = providers or build_providers(registry)
        self.router = Router(registry, self.providers)
        self.workspace = Path(workspace or ROOT / "workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.audit = audit or Audit(ROOT / "logs" / "audit.jsonl")
        self.max_steps = max_steps
        self.kb = kb or KnowledgeBase(ROOT / "data" / "kb.sqlite")

    def context(self, workspace: Path | None = None) -> tools.ToolContext:
        return tools.ToolContext(workspace or self.workspace, self.registry.sandbox, self.vision, self.kb)

    def vision(self, prompt: str, png: bytes) -> tuple[str, str]:
        """Read an image with the first available vision model (registry order = preference)."""
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        content = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]
        for m in self.registry.usable("vision"):
            provider = self.providers[m.provider]
            if provider.available(m.id):
                return provider.chat(m.id, [{"role": "user", "content": content}]), m.id
        raise RuntimeError("no vision model available")

    def run(self, text: str, attachments: tuple[str, ...] = (), session: str | None = None) -> Iterator[dict]:
        session = session or uuid4().hex[:12]
        for event in self._run(Task(text, tuple(attachments)), session):
            self.audit.log(session, event)
            yield event

    def task_folder(self, session: str) -> Path:
        """Each task works in its own folder, so files from earlier tasks cannot leak in."""
        work = self.workspace / "tasks" / session
        work.mkdir(parents=True, exist_ok=True)
        return work

    def read_attachments(self, attachments: tuple[str, ...], work: Path, share: int):
        """Input layer: copy each attachment into the task folder and read it.

        Yields `ingest` events; the generator's return value is {file name: text}. `share` is the
        most characters to keep per file; None keeps the whole text.
        """
        texts: dict[str, str] = {}
        for name in attachments:
            try:
                src = self.context().resolve(name)
                if src.parent != work:
                    shutil.copy2(src, work / src.name)
                name = src.name
                pages = ingest.extract(work / name, self.vision)
                texts[name] = ingest.as_text(pages, share)
                yield {"type": "ingest", "file": name, "pages": len(pages), "chars": len(ingest.as_text(pages)),
                       "via": sorted({p["via"] for p in pages}), "preview": texts[name][:400]}
            except Exception as e:
                texts[name] = f"(could not be read: {e})"
                yield {"type": "ingest", "file": name, "error": str(e)}
        return texts

    def _run(self, task: Task, session: str) -> Iterator[dict]:
        """Single-agent mode: one model, all the tools that suit the task type."""
        try:
            d = self.router.route(task)
        except NoModelAvailable as e:
            yield {"type": "error", "message": str(e)}
            return
        work = self.task_folder(session)
        yield {"type": "route", "mode": "single", "capability": d.capability, "complexity": d.complexity,
               "model": d.model.id, "reason": d.reason, "workspace": f"tasks/{session}"}

        share = (d.model.context * 3 // 2) // max(1, len(task.attachments))
        texts = yield from self.read_attachments(task.attachments, work, share)
        user = task.context + task.text + "".join(f"\n\n--- Attached file: {n} ---\n{t}" for n, t in texts.items())
        earlier = sorted(p.name for p in work.iterdir() if p.is_file() and not p.name.startswith("_")
                         and p.name not in texts)
        if earlier:
            user += "\n\nFiles already in the workspace: " + ", ".join(earlier)
        toolset = tools.describe(exclude=HIDDEN.get(d.capability, ()))
        yield from self.run_loop(d, SYSTEM.replace("TOOLS", toolset), user, self.context(work))

    def run_loop(self, d, system: str, user: str, ctx: tools.ToolContext,
                 accept=None, trace: list | None = None) -> Iterator[dict]:
        """The agent loop, shared by single-agent mode and every agent of a team.

        d       routing decision: the starting model and its escalation candidates
        accept  optional check (answer, facts) -> correction text or None
        trace   optional list that receives every tool call as {"tool", "args", "result"}
        Ends with a `final` or an `error` event.
        """
        spec, tried = d.model, {d.model.id}
        work = ctx.workspace
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        invalid = stuck = challenged = failures = 0
        seen: set[tuple] = set()

        def escalate(reason: str):
            """Move to a bigger model if one exists. Returns the event, or None."""
            nonlocal spec
            nxt = self.router.next_model(d, tried, bigger_than=spec.tier)
            if nxt is None:
                return None
            event = {"type": "escalate", "from": spec.id, "to": nxt.id, "reason": reason}
            spec = nxt
            tried.add(spec.id)
            return event

        for step in range(1, self.max_steps + 1):
            budget = spec.context * 3  # ~4 chars per token, leaving room for the reply
            _fit(messages, budget)
            try:
                # Fast by default; once a reply has been rejected the model is asked to reason it through.
                harder = True if (invalid or challenged or stuck) else None
                reply = self.providers[spec.provider].chat(spec.id, messages, json_mode=True, think=harder)
            except Exception as e:  # any provider failure: move to the next model
                nxt = self.router.next_model(d, tried)
                if nxt is None:
                    yield {"type": "error", "message": f"model {spec.id} failed: {e}"}
                    return
                yield {"type": "fallback", "from": spec.id, "to": nxt.id, "reason": str(e)}
                spec = nxt
                tried.add(spec.id)
                continue

            action = parse_action(reply)
            if action is None:
                invalid += 1
                yield {"type": "invalid", "step": step, "model": spec.id, "reply": reply[:300]}
                if invalid >= MAX_INVALID:
                    event = escalate(f"{invalid} invalid replies")
                    if event:
                        invalid = 0
                        yield event
                messages += [{"role": "assistant", "content": reply[:2000]},
                             {"role": "user", "content": RETRY}]
                continue

            if "final" in action:
                answer = str(action["final"])
                facts = action.get("facts") or []
                facts = [str(f)[:400] for f in (facts if isinstance(facts, list) else [facts])][:15]
                # A file named in the answer must really exist (task folder or knowledge base).
                known = {p.name.lower() for p in work.rglob("*") if p.is_file()}
                known |= {doc["doc"].lower() for doc in self.kb.documents()}
                missing = sorted({n for n in FILE_RE.findall(answer) if n.lower() not in known})
                problem = None
                if missing:
                    problem = (f"answer names files that do not exist: {', '.join(missing)}. No tool created "
                               "them. Create them with the right tool, then give the final answer.")
                elif accept:
                    problem = accept(answer, facts)
                if problem and challenged < 2:
                    challenged += 1
                    yield {"type": "invalid", "step": step, "model": spec.id, "reply": problem}
                    if challenged == 2:
                        event = escalate("result did not pass its check")
                        if event:
                            yield event
                    messages += [{"role": "assistant", "content": json.dumps(action)},
                                 {"role": "user", "content": f"Not accepted: {problem}"}]
                    continue
                final = {"type": "final", "model": spec.id, "steps": step, "answer": answer}
                if facts:
                    final["facts"] = facts
                if problem:
                    final["unverified"] = problem
                yield final
                return

            name = action["tool"]
            args = action["args"] if isinstance(action.get("args"), dict) else {}
            yield {"type": "tool_call", "step": step, "model": spec.id, "tool": name,
                   "args": args, "thought": action.get("thought", "")}
            result = tools.run(name, args, ctx)[: budget // 4]
            if trace is not None:
                trace.append({"tool": name, "args": args, "result": result})
            yield {"type": "tool_result", "step": step, "tool": name, "result": result}
            observation = f"Observation from {name}:\n{result}"

            # Same action with the same result as before, or one failed call after another:
            # the model is going in circles.
            key = (name, json.dumps(args, sort_keys=True), result)
            failures = failures + 1 if result.startswith("ERROR") else 0
            if key in seen or failures >= MAX_FAILURES:
                event = escalate("repeating the same action with the same result")
                if event:
                    yield event
                else:
                    stuck += 1
                    yield {"type": "stuck", "step": step, "model": spec.id}
                    if stuck >= MAX_STUCK:
                        yield {"type": "error", "message":
                               f"{spec.id} kept repeating the same step and no larger model is available on this "
                               "hardware. Rephrase the task, or install a larger model."}
                        return
                observation += STUCK
            seen.add(key)
            messages += [{"role": "assistant", "content": json.dumps(action)},
                         {"role": "user", "content": observation}]

        yield {"type": "error", "message": f"step limit ({self.max_steps}) reached"}
