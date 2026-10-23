"""Orchestrator: plans a task, hands it between specialised agents, checks and reviews the result.

A simple question goes straight to the single agent. Anything else becomes a short
pipeline (Reader -> Researcher -> Analyst -> Coder -> Writer) in which each agent has
one job, its own tools and model, and a check its result must pass. Agents share a
compact fact sheet instead of one long conversation, so the work fits a small context.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from . import ingest
from .agent import Agent
from .agents import AgentDef, CheckContext, load_agents, run_checks
from .router import CODE_RE, NoModelAvailable, Task, classify

KB_RE = re.compile(r"\b(sop|manual|polic|procedure|knowledge base|standard|guideline|authority|circular|"
                   r"correspondence|company rule|standing order)\w*", re.I)
ATTACHED_RE = re.compile(r"\b(attached|this|uploaded|above|following)\s+\w+", re.I)
CALC_RE = re.compile(r"\b(calculat|comput|estimat|how much|pressure drop|flow rate|convert)\w*", re.I)
DELIVER_RE = re.compile(
    r"\b(draft|write|prepare|create|make|generate|produce|save|export|put|list)\b.*"
    r"\b(word|docx|excel|xlsx|spreadsheet|sheet|powerpoint|pptx|presentation|slides?|deck|note|report|document|"
    r"memo|letter)\b", re.I | re.S)

MAX_SESSIONS = 100  # conversations remembered
MAX_PARTS = 8       # most parts a long set of attachments is read in
TRUSTED_TIER = 3  # from this model size up, the Planner may add agents and the Reviewer may send work back

PLANNER = """You are the Planner of a team of agents. Split the request into the fewest steps and give each step to one agent.
Agents:
AGENTS
Reply with exactly ONE JSON object and nothing else:
{"steps": [{"agent": "<agent name>", "goal": "<what this agent must achieve, in one sentence>"}]}
Use at most 5 steps and each agent at most once. Only use agents the request really needs."""

REVIEWER = """You are the Reviewer of a team of agents. Compare the result with the request.
Reply with exactly ONE JSON object and nothing else:
{"verdict": "pass"}  when the result does what was asked, or
{"verdict": "fix", "correction": "<one specific instruction to correct the result>"}
Ask for a fix only for a real problem: something requested is missing, a statement contradicts the fact sheet,
or the wrong kind of file was made. Do not ask for style changes or extra detail.
A presentation always starts with a title slide, which does not count as a content slide."""


class FactSheet:
    """What the team has established so far; passed to each agent instead of the full history."""

    def __init__(self):
        self.entries: list[tuple[str, str]] = []

    def add(self, agent: str, facts: list[str]) -> None:
        self.entries += [(agent, f) for f in facts]

    def facts(self, agent: str) -> list[str]:
        return [f for a, f in self.entries if a == agent]

    def text(self, limit: int) -> str:
        lines = [f"- [{a}] {f}" for a, f in self.entries]
        if not lines:
            return "(empty)"
        kept, size = [], 0
        for line in reversed(lines):  # when space is short the newest facts are kept
            if size + len(line) + 1 > limit and kept:
                kept.append("(older facts omitted)")
                break
            kept.append(line)
            size += len(line) + 1
        return "\n".join(reversed(kept))[:limit]


class Orchestrator:
    def __init__(self, agent: Agent, defs: dict[str, AgentDef] | None = None):
        self.agent = agent
        self.defs = defs or load_agents()
        self.sessions: dict[str, dict] = {}  # conversation memory, in RAM only

    def run(self, text: str, attachments: tuple[str, ...] = (), session: str | None = None) -> Iterator[dict]:
        """Run one turn. Turns that share a `session` share a folder, a fact sheet and their history."""
        session = session or uuid4().hex[:12]
        mem = self.sessions.setdefault(session, {"turns": [], "sheet": FactSheet(), "sources": [], "inputs": set()})
        context = ""
        if mem["turns"]:
            context = ("Earlier in this conversation:\n"
                       + "\n".join(f"User: {q[:300]}\nAssistant: {a[:600]}" for q, a in mem["turns"][-3:])
                       + "\n\nThe current request follows.\n\n")
        answer = "(no answer)"
        for event in self._run(Task(text, tuple(attachments), context), session, mem):
            self.agent.audit.log(session, event)
            if event["type"] == "final":
                answer = event["answer"]
            elif event["type"] == "error":
                answer = f"(the task failed: {event['message']})"
            yield event
        mem["turns"].append((text, answer))
        while len(self.sessions) > MAX_SESSIONS:
            self.sessions.pop(next(iter(self.sessions)))

    # ---- planning ----

    def template(self, task: Task) -> list[str]:
        """Rule-based plan: the safety net when the Planner's reply is unusable."""
        steps = []
        if task.attachments:
            steps.append("reader")
        # "the attached manual" refers to the attachment, not to the knowledge base.
        about_kb = KB_RE.search(ATTACHED_RE.sub(" ", task.text))
        if self.agent.kb.documents() and about_kb:
            steps.append("researcher")
        if CODE_RE.search(task.text):
            steps.append("coder")
        else:
            if CALC_RE.search(task.text):
                steps.append("analyst")
            if DELIVER_RE.search(task.text):
                steps.append("writer")
        if steps and not {"coder", "analyst", "writer"} & set(steps):
            steps.append("responder")  # a question about documents: someone has to answer it
        return [s for s in steps if s in self.defs]

    def plan(self, task: Task, d, template: list[str]) -> tuple[list[dict], str]:
        """Ask the Planner, then keep its plan within safe bounds. Returns (steps, source)."""
        goals, source = {}, "template"
        listing = "\n".join(f"- {a.name}: {a.job}" for a in self.defs.values())
        user = task.context + task.text
        if task.attachments:
            user += "\n\nAttached files: " + ", ".join(Path(a).name for a in task.attachments)
        docs = [doc["doc"] for doc in self.agent.kb.documents()]
        if docs:
            user += "\nKnowledge base documents: " + ", ".join(docs[:20])
        try:
            reply = self.agent.providers[d.model.provider].chat(
                d.model.id, [{"role": "system", "content": PLANNER.replace("AGENTS", listing)},
                             {"role": "user", "content": user}], json_mode=True)
            steps = json.loads(reply[reply.find("{"):reply.rfind("}") + 1]).get("steps")
            for s in steps:
                if s["agent"] in self.defs and isinstance(s.get("goal"), str):
                    goals.setdefault(s["agent"], s["goal"].strip())
            source = "planner" if goals else "template"
        except Exception:
            pass
        # A small Planner over-plans (it sent a presentation task to the Researcher and the Analyst), so
        # below tier 3 it only writes the goals and the rules choose the agents. A large model may add agents.
        names = set(template) | (set(goals) if d.model.tier >= TRUSTED_TIER else set())
        if not task.attachments:
            names.discard("reader")
        if not docs:
            names.discard("researcher")
        if "coder" in names and not CODE_RE.search(task.text):
            names.discard("coder")
        ordered = [a.name for a in self.defs.values() if a.name in names]
        return [{"agent": n, "goal": goals.get(n) or self.defs[n].default_goal} for n in ordered], source

    # ---- execution ----

    @staticmethod
    def _parts(texts: dict[str, str], size: int) -> list[str]:
        """Split the attachments into pieces a Reader can take, breaking at line ends."""
        parts, cur = [], ""
        for name, text in texts.items():
            block = f"--- Attached file: {name} ---\n"
            for line in text.splitlines(keepends=True):
                while len(line) > size:  # one very long line
                    parts.append(cur + block + line[:size]); cur, block, line = "", "", line[size:]
                if len(cur) + len(block) + len(line) > size and cur.strip():
                    parts.append(cur)
                    cur, block = "", f"--- Attached file: {name} (continued) ---\n"
                cur += block + line
                block = ""
            cur += "\n"
        if cur.strip():
            parts.append(cur)
        if len(parts) > MAX_PARTS:
            skipped = sum(len(p) for p in parts[MAX_PARTS:])
            parts = parts[:MAX_PARTS]
            parts[-1] += f"\n(the documents continue: {skipped} more characters were not read)"
        return parts or [""]

    def _run(self, task: Task, session: str, mem: dict) -> Iterator[dict]:
        _, complexity = classify(task)
        template = self.template(task)
        if (complexity == "low" and not task.attachments) or not template:
            answer = None
            for event in self.agent._run(task, session):  # fast path: single agent
                answer = event.get("answer", answer)
                yield event
            mem["sources"] += [task.text, answer or ""]
            return
        try:
            d = self.agent.router.route_for("general", "high")
        except NoModelAvailable as e:
            yield {"type": "error", "message": str(e)}
            return

        work = self.agent.task_folder(session)
        yield {"type": "route", "mode": "team", "capability": "team", "complexity": complexity, "model": d.model.id,
               "reason": "multi-step task: planned and handed between specialised agents",
               "workspace": f"tasks/{session}"}
        budget = d.model.context * 3
        texts = yield from self.agent.read_attachments(task.attachments, work, None)  # whole documents
        mem["inputs"] |= set(texts)

        steps, source = self.plan(task, d, template)
        yield {"type": "plan", "source": source,
               "steps": [{**s, "title": self.defs[s["agent"]].title} for s in steps]}

        mem["sources"] += [task.text, task.context, *texts.values()]
        state = {"task": task, "work": work, "texts": texts, "inputs": mem["inputs"], "sheet": mem["sheet"],
                 "budget": budget, "sources": mem["sources"], "done": [], "tool_steps": 0}
        for step in steps:
            if step["agent"] == "reader":
                # A long document is read in parts; every part adds its facts to the sheet.
                parts = self._parts(texts, budget // 2)
                for i, part in enumerate(parts, 1):
                    goal = step["goal"] + (f" (part {i} of {len(parts)})" if len(parts) > 1 else "")
                    # One part of a long document may hold nothing relevant, so it may return no facts.
                    yield from self._step({**step, "goal": goal, "doc": part, "may_be_empty": len(parts) > 1}, state)
            else:
                yield from self._step(step, state)

        review = yield from self._review(steps, state)
        yield self._final(state, review)

    def _files(self, work: Path, skip: set[str]) -> list[Path]:
        return sorted(p for p in work.rglob("*")
                      if p.is_file() and not p.name.startswith("_") and "__pycache__" not in p.parts
                      and p.name not in skip)

    def _step(self, step: dict, state: dict) -> Iterator[dict]:
        """Run one agent: its own prompt, tools, model and acceptance check."""
        a, task, work, sheet = self.defs[step["agent"]], state["task"], state["work"], state["sheet"]
        try:
            d = self.agent.router.route_for(a.capability, "high")
        except NoModelAvailable as e:
            state["done"].append({"agent": a.name, "error": str(e)})
            yield {"type": "agent_done", "agent": a.name, "title": a.title, "error": str(e)}
            return
        yield {"type": "agent_start", "agent": a.name, "title": a.title, "goal": step["goal"], "model": d.model.id}

        before = {p: p.stat().st_mtime_ns for p in self._files(work, set())}

        def changed() -> list[Path]:
            """Files this agent created or rewrote."""
            return [p for p in self._files(work, set()) if before.get(p) != p.stat().st_mtime_ns]

        trace: list[dict] = []
        budget = d.model.context * 3
        user = f"{task.context}Overall request: {task.text}\n\nYour step: {step['goal']}"
        if a.name == "reader":
            user += "\n\n" + step.get("doc", "")
        else:
            if state["inputs"]:
                user += "\n\nAttached files (already read by the Reader): " + ", ".join(sorted(state["inputs"]))
            user += "\n\nFact sheet so far:\n" + sheet.text(budget // 3)
        made = [p.name for p in self._files(work, state["inputs"])]
        if made:
            user += "\n\nFiles created so far: " + ", ".join(made)

        def accept(answer: str, facts: list[str]):
            sources = "\n".join([*state["sources"], *(t["result"] for t in trace),
                                 *(json.dumps(t["args"]) for t in trace if t["tool"] == "run_python")])
            checks = tuple(c for c in a.checks if not (step.get("may_be_empty") and c == "facts_present"))
            return run_checks(checks, CheckContext(
                request=task.text, answer=answer, facts=facts, trace=trace, sources=sources,
                new_files=changed(), known=[f for _, f in sheet.entries]))

        result = error = None
        for event in self.agent.run_loop(d, a.system(), user, self.agent.context(work), accept=accept, trace=trace):
            if event["type"] == "final":
                result = event
            elif event["type"] == "error":
                error = event["message"]
            else:
                yield {**event, "agent": a.name}

        state["sources"] += [t["result"] for t in trace]
        state["tool_steps"] += len(trace)
        done = {"agent": a.name, "title": a.title}
        if result:
            facts = result.get("facts", [])
            sheet.add(a.name, facts)
            state["sources"] += facts
            done.update(summary=result["answer"], facts=facts, model=result["model"])
            if result.get("unverified"):
                done["unverified"] = result["unverified"]
        else:
            done["error"] = error or "no result"
        state["done"].append(done)
        yield {"type": "agent_done", **done}

    def _review(self, steps: list[dict], state: dict):
        """Fixed checks for every agent, plus one model review of a written deliverable."""
        checks = [{"agent": x["agent"], "ok": "error" not in x and "unverified" not in x,
                   "problem": x.get("error") or x.get("unverified") or ""} for x in state["done"]]
        review = {"type": "review", "verdict": "pass" if all(c["ok"] for c in checks) else "issues", "checks": checks}
        writer = next((s for s in steps if s["agent"] == "writer"), None)
        files = self._files(state["work"], state["inputs"])
        if writer and files:
            verdict, tier = self._ask_reviewer(state, files)
            review["reviewed_by_model"] = verdict.get("verdict") in ("pass", "fix")
            if verdict.get("verdict") == "fix" and verdict.get("correction"):
                correction = str(verdict["correction"])[:400]
                if tier < TRUSTED_TIER:
                    # A small reviewer is often wrong (it counted the title slide as an extra slide and
                    # sent good work back), so its remark is shown to the user and not enforced.
                    review["comment"] = correction
                else:
                    yield {"type": "review", "verdict": "fix", "correction": correction, "checks": checks}
                    kept = [x for x in state["done"] if x["agent"] == "writer"]
                    backup = {f: f.read_bytes() for f in files}
                    state["done"] = [x for x in state["done"] if x["agent"] != "writer"]
                    yield from self._step({"agent": "writer", "goal": f"{writer['goal']}\nReviewer's correction, "
                                           f"which you must apply: {correction}"}, state)
                    outcome = {"correction_applied": correction}
                    if "error" in state["done"][-1] and kept:  # the redo failed: keep the first version
                        for f, data in backup.items():
                            f.write_bytes(data)
                        state["done"][-1] = kept[-1]
                        outcome = {"comment": f"{correction} (could not be applied; the first version was kept)"}
                    return (yield from self._review([], state)) | outcome
        yield review
        return review

    def _ask_reviewer(self, state: dict, files: list[Path]) -> tuple[dict, int]:
        """Returns (verdict, tier of the reviewing model)."""
        tier = 0
        try:
            d = self.agent.router.route_for("general", "high")
            tier = d.model.tier
            share = (state["budget"] // 2) // len(files)
            content = "\n\n".join(f"--- {f.name} ---\n{ingest.as_text(ingest.extract(f), share)}" for f in files)
            user = (f"Request: {state['task'].text}\n\nFact sheet:\n{state['sheet'].text(state['budget'] // 4)}"
                    f"\n\nResult files:\n{content}")
            reply = self.agent.providers[d.model.provider].chat(
                d.model.id, [{"role": "system", "content": REVIEWER}, {"role": "user", "content": user}],
                json_mode=True)
            verdict = json.loads(reply[reply.find("{"):reply.rfind("}") + 1])
            return (verdict if isinstance(verdict, dict) else {}), tier
        except Exception:
            return {}, tier

    def _final(self, state: dict, review: dict) -> dict:
        done = state["done"]
        good = [x for x in done if "summary" in x]
        if not good:
            return {"type": "error", "message": "no agent produced a result: "
                    + "; ".join(f"{x['agent']}: {x.get('error', '')}" for x in done)}
        parts = [good[-1]["summary"]]
        # Calculation steps and findings come straight from the checked facts of the agents that ran this turn.
        facts_of = lambda name: [f for x in good if x["agent"] == name for f in x.get("facts", [])]
        if facts_of("analyst"):
            parts.append("Calculation steps:\n" + "\n".join(f"- {f}" for f in facts_of("analyst")))
        elif good[-1]["agent"] not in ("writer", "responder") and facts_of(good[-1]["agent"]):
            parts.append("\n".join(f"- {f}" for f in facts_of(good[-1]["agent"])[:25]))
        if facts_of("researcher") and good[-1]["agent"] != "researcher":
            parts.append("Rules applied:\n" + "\n".join(f"- {f}" for f in facts_of("researcher")))
        files = [p.name for p in self._files(state["work"], state["inputs"])]
        if files:
            parts.append("Files: " + ", ".join(files))
        problems = [f"{c['agent']}: {c['problem']}" for c in review["checks"] if not c["ok"]]
        if review.get("correction_applied"):
            parts.append("Reviewer's correction applied: " + review["correction_applied"])
        if review.get("comment"):
            parts.append("Reviewer's comment (not applied): " + review["comment"])
        final = {"type": "final", "mode": "team", "model": good[-1]["model"], "steps": state["tool_steps"],
                 "answer": "\n\n".join(parts)}
        if problems:
            final["unverified"] = "; ".join(problems)
        return final
