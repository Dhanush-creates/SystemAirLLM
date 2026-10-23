"""Core tests. No model needed: a scripted mock stands in. Run: python tests/test_core.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workbench.agent import Agent, parse_action
from workbench.agents import CHECKS, CheckContext, load_agents, ungrounded
from workbench.orchestrator import FactSheet, Orchestrator
from workbench import ingest
from workbench.audit import Audit
from workbench.kb import KnowledgeBase
from workbench.netmon import scope
from workbench.netguard import EgressBlocked, check_local
from workbench.providers import MockProvider
from workbench.registry import Registry
from workbench.router import Router, Task
from workbench import tools

CFG = {
    "profile": "workstation",
    "profiles": {"workstation": {"vram_gb": 12}, "server": {"vram_gb": 96}},
    "providers": {"mock": {"type": "mock"}},
    "sandbox": "local",
    "models": [
        {"id": "small", "provider": "mock", "capabilities": ["general"], "tier": 1, "vram_gb": 6},
        {"id": "big", "provider": "mock", "capabilities": ["general"], "tier": 2, "vram_gb": 10},
        {"id": "coder", "provider": "mock", "capabilities": ["code"], "tier": 2, "vram_gb": 9},
        {"id": "vis", "provider": "mock", "capabilities": ["vision"], "tier": 1, "vram_gb": 6},
        {"id": "huge", "provider": "mock", "capabilities": ["general", "code"], "tier": 4, "vram_gb": 80},
    ],
}


def make_agent(script, profile=None):
    tmp = Path(tempfile.mkdtemp())
    agent = Agent(Registry(CFG, profile), {"mock": MockProvider(script)},
                  workspace=tmp / "ws", audit=Audit(tmp / "audit.jsonl"), kb=KnowledgeBase(tmp / "kb.sqlite"))
    return agent, tmp


def test_profile_filters_models():
    assert [m.id for m in Registry(CFG).usable("general")] == ["small", "big"]
    assert "huge" in [m.id for m in Registry(CFG, "server").usable("general")]


def test_routing_by_task_type_and_complexity():
    def pick(text, attachments=(), profile=None):
        return Router(Registry(CFG, profile), {"mock": MockProvider()}).route(Task(text, attachments)).model.id

    assert pick("What is a flange?") == "small"
    assert pick("Draft an approval note analysing the inspection findings") == "big"
    assert pick("Write a python function to parse a CSV") == "coder"
    # Attachments make a task complex; the vision model reads them in the input layer instead.
    assert pick("What does this show?", ("drawing.png",)) == "big"
    # Same task, server hardware: the 120B-class model is chosen with no code change.
    assert pick("Draft an approval note analysing the inspection findings", profile="server") == "huge"


def test_netguard():
    check_local("http://127.0.0.1:11434/v1")
    for url in ("https://8.8.8.8/v1", "http://192.168.1.50:8000/v1"):
        try:
            check_local(url)
            raise AssertionError(f"{url} should be blocked")
        except EgressBlocked:
            pass
    check_local("http://192.168.1.50:8000/v1", allow_private=True)


def test_parse_action_tolerates_noise():
    assert parse_action('<think>hmm</think>```json\n{"final": "ok"}\n```')["final"] == "ok"
    assert parse_action("no json here") is None
    assert parse_action('{"unrelated": 1}') is None


def test_agent_end_to_end():
    script = [
        json.dumps({"tool": "write_file", "args": {"path": "calc.py", "content": "print(6 * 7)"}}),
        json.dumps({"tool": "run_python", "args": {"code": "exec(open('calc.py').read())"}}),
        json.dumps({"final": "The result is 42."}),
    ]
    agent, tmp = make_agent(script)
    events = list(agent.run("Write a python script that multiplies 6 by 7 and run it"))
    assert events[0]["type"] == "route" and events[0]["model"] == "coder"
    results = [e for e in events if e["type"] == "tool_result"]
    assert "exit=0" in results[1]["result"] and "42" in results[1]["result"]
    assert events[-1] == {"type": "final", "model": "coder", "steps": 3, "answer": "The result is 42."}
    assert (tmp / "ws" / events[0]["workspace"] / "calc.py").exists()  # each task has its own folder
    assert len(agent.audit.tail()) == len(events)


def test_escalates_to_bigger_model():
    agent, _ = make_agent(lambda model, messages: "garbage" if model == "small" else '{"final": "ok"}')
    events = list(agent.run("What is a flange?"))
    assert [e["type"] for e in events] == ["route", "invalid", "invalid", "escalate", "final"]
    assert events[-1]["model"] == "big"


def test_escalates_when_model_repeats_itself():
    def script(model, messages):
        return '{"tool": "list_files", "args": {}}' if model == "small" else '{"final": "ok"}'

    agent, _ = make_agent(script)
    events = list(agent.run("What is a flange?"))
    assert [e["type"] for e in events] == [
        "route", "tool_call", "tool_result", "tool_call", "tool_result", "escalate", "final"]
    assert events[-1]["model"] == "big"


def test_escalation_only_model_is_last_resort():
    slow = {"id": "slow70b", "provider": "mock", "capabilities": ["general"], "tier": 4,
            "vram_gb": 10, "escalation_only": True}
    reg = Registry({**CFG, "models": CFG["models"] + [slow]})
    script = lambda model, messages: '{"final": "ok"}' if model == "slow70b" else "garbage"
    tmp = Path(tempfile.mkdtemp())
    agent = Agent(reg, {"mock": MockProvider(script)}, workspace=tmp / "ws", audit=Audit(tmp / "a.jsonl"),
                  kb=KnowledgeBase(tmp / "kb.sqlite"))
    events = list(agent.run("Draft a report on pump maintenance"))
    assert events[0]["model"] == "big"  # never picked first, even for a complex task
    assert events[-1]["type"] == "final" and events[-1]["model"] == "slow70b"


def test_claimed_file_must_exist():
    script = [
        json.dumps({"final": "I created report.docx for you."}),  # a lie: nothing was created
        json.dumps({"tool": "make_docx", "args": {"path": "report.docx", "title": "R", "content": "- done"}}),
        json.dumps({"final": "I created report.docx for you."}),
    ]
    agent, _ = make_agent(script)
    events = list(agent.run("What is a flange?"))
    assert [e["type"] for e in events] == ["route", "invalid", "tool_call", "tool_result", "final"]
    assert "do not exist" in events[1]["reply"] and "unverified_files" not in events[-1]


def test_gives_up_when_stuck_with_no_bigger_model():
    agent, _ = make_agent(lambda model, messages: '{"tool": "list_files", "args": {}}')
    events = list(agent.run("Draft a report on pump maintenance"))  # starts on the biggest model
    assert [e["type"] for e in events].count("stuck") == 3
    assert events[-1]["type"] == "error" and "repeating" in events[-1]["message"]


def test_gives_up_after_a_run_of_failing_tool_calls():
    # A different missing page every time: never the same call twice, but never a success either.
    n = iter(range(10, 99))
    agent, _ = make_agent(lambda model, messages: json.dumps({"tool": "read_file", "args": {"path": f"p{next(n)}.txt"}}))
    events = list(agent.run("Draft a report on pump maintenance"))
    assert events[-1]["type"] == "error" and "repeating" in events[-1]["message"]
    assert sum(e["type"] == "tool_call" for e in events) == 5  # 3 failures to notice, 2 more warnings, then stop


def test_code_tasks_do_not_see_office_tools():
    assert "make_docx" in tools.describe() and "make_docx" not in tools.describe(exclude={"office"})
    ctx = tools.ToolContext(Path(tempfile.mkdtemp()), "local")
    assert "use write_file" in tools.run("make_docx", {"path": "x.py", "title": "t", "content": "c"}, ctx)


def test_falls_back_when_model_fails():
    def script(model, messages):
        if model == "big":
            raise ConnectionError("server down")
        return '{"final": "ok"}'

    agent, _ = make_agent(script)
    events = list(agent.run("Draft a report on pump maintenance"))
    assert [e["type"] for e in events] == ["route", "fallback", "final"]
    assert events[-1]["model"] == "small"


def test_small_models_are_backups_on_big_hardware():
    tiny = {"id": "tiny", "provider": "mock", "capabilities": ["general"], "tier": 0, "vram_gb": 3}
    reg = Registry({**CFG, "models": CFG["models"] + [tiny]})
    d = Router(reg, {"mock": MockProvider()}).route(Task("What is a flange?"))
    assert d.model.id == "small" and [m.id for m in d.candidates] == ["small", "big", "tiny"]
    # On a 4 GB machine the tiny model is the only one that fits, so it is used.
    low = Registry({**CFG, "profile": "laptop", "profiles": {"laptop": {"vram_gb": 4}}, "models": CFG["models"] + [tiny]})
    assert Router(low, {"mock": MockProvider()}).route(Task("What is a flange?")).model.id == "tiny"


def test_sandbox_prints_last_expression():
    ctx = tools.ToolContext(Path(tempfile.mkdtemp()), "local")
    assert "42" in tools.run("run_python", {"code": "x = 6\nx * 7"}, ctx)
    assert "printed nothing" in tools.run("run_python", {"code": "x = 1"}, ctx)
    assert "ΔP = 5 ρ" in tools.run("run_python", {"code": "print('ΔP = 5 ρ')"}, ctx)  # symbols survive


def test_reasoning_is_off_by_default_and_on_after_a_rejection():
    seen = []

    class Recorder(MockProvider):
        def chat(self, model, messages, json_mode=False, think=None):
            seen.append(think)
            return "garbage" if len(seen) == 1 else '{"final": "ok"}'

    tmp = Path(tempfile.mkdtemp())
    agent = Agent(Registry(CFG), {"mock": Recorder()}, workspace=tmp / "ws", audit=Audit(tmp / "a.jsonl"),
                  kb=KnowledgeBase(tmp / "kb.sqlite"))
    list(agent.run("What is a flange?"))
    assert seen == [None, True]  # registry default first, reasoning forced on for the retry


def test_empty_reply_is_retried_without_reasoning():
    from workbench.providers import OpenAIProvider
    calls = []
    p = OpenAIProvider("http://127.0.0.1:9/v1")

    def fake(model, messages, as_json, thinking):
        calls.append((as_json, thinking))
        if (as_json, thinking) == (True, True):
            return ""                        # all tokens spent on hidden reasoning
        if (as_json, thinking) == (True, False):
            raise OSError("HTTP 500: token repeat limit reached")
        return '{"final": "ok"}'

    p._once = fake
    assert p.chat("m", [], json_mode=True) == '{"final": "ok"}'
    assert calls == [(True, True), (True, False), (False, False)]
    p.no_think = {"m"}                       # registry says think: false -> starts without reasoning
    calls.clear()
    p.chat("m", [], json_mode=True)
    assert calls == [(True, False), (False, False)]


def test_tools_are_confined_to_workspace():
    ctx = tools.ToolContext(Path(tempfile.mkdtemp()), "local")
    assert tools.run("read_file", {"path": "../../secret.txt"}, ctx).startswith("ERROR: PermissionError")
    assert tools.run("no_such_tool", {}, ctx).startswith("ERROR: unknown tool")


def _scan_png(text: str) -> bytes:
    """A picture of text: no text layer, like a scanned page."""
    import pymupdf
    page = pymupdf.open().new_page()
    page.insert_text((72, 72), text)
    return page.get_pixmap().tobytes("png")


def test_input_layer_every_file_type():
    import pymupdf
    tmp = Path(tempfile.mkdtemp())
    ctx = tools.ToolContext(tmp, "local", vision=lambda prompt, png: ("crack at weld W-12", "mock-vision"))
    read = lambda name: tools.run("read_document", {"path": name}, ctx)

    (tmp / "a.txt").write_text("plain text file")
    assert "plain text file" in read("a.txt")

    assert "created" in tools.run("make_docx", {"path": "n", "title": "T",
                                                "content": "# Scope\n- point one\n| a | b |\n|---|---|\n| 1 | 2 |"}, ctx)
    assert "point one" in read("n.docx") and "1 | 2" in read("n.docx")

    assert "created" in tools.run("make_approval_note", {
        "path": "note.docx", "subject": "Repair of P-101", "background": "Inspection on site.",
        "findings": ["Seal leak", "Bearing wear"], "recommendation": "Replace seal.",
        "approval_sought": "Approve the repair."}, ctx)
    note = read("note.docx")
    assert "Seal leak" in note and "Approved by" in note and "Repair of P-101" in note

    assert "created" in tools.run("make_xlsx", {"path": "s.xlsx", "rows": [["Item", "Qty"], ["Valve", 4],
                                                                           ["Total", "=SUM(B2:B2)"]]}, ctx)
    assert "Valve | 4" in read("s.xlsx") and "=SUM(B2:B2)" in read("s.xlsx")

    assert "created" in tools.run("make_pptx", {"path": "d.pptx", "title": "Review",
                                                "slides": [{"title": "Status", "bullets": ["On track", "No LTI"]}]}, ctx)
    assert "No LTI" in read("d.pptx")

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hydrotest pressure 15 bar for line L-101, held for thirty minutes.")
    doc.save(tmp / "t.pdf")
    assert ingest.extract(tmp / "t.pdf")[0]["via"] == "text layer"

    png = _scan_png("scanned page")
    (tmp / "scan.png").write_bytes(png)
    page = ingest.extract(tmp / "scan.png", ctx.vision)[0]
    assert page["via"] == "vision model mock-vision" and "W-12" in page["text"]

    scanned = pymupdf.open()
    p = scanned.new_page()
    p.insert_image(p.rect, stream=png)
    scanned.save(tmp / "scan.pdf")
    assert ingest.extract(tmp / "scan.pdf", ctx.vision)[0]["via"] == "vision model mock-vision"
    assert ingest.extract(tmp / "scan.pdf")[0]["via"] == "none"  # no vision model: says so, does not invent

    assert read("x.exe").startswith("ERROR")


def test_attachment_is_read_by_vision_model_then_given_to_driver():
    seen = {}

    def script(model, messages):
        if isinstance(messages[-1]["content"], list):  # the image request
            seen["vision_model"] = model
            return "Inspection: corrosion on flange F-7"
        seen["driver"], seen["prompt"] = model, messages[1]["content"]
        return '{"final": "done"}'

    agent, tmp = make_agent(script)
    (tmp / "ws" / "uploads").mkdir(parents=True)
    (tmp / "ws" / "uploads" / "report.png").write_bytes(_scan_png("scan"))
    events = list(agent.run("What does this report say?", ("uploads/report.png",)))
    ing = next(e for e in events if e["type"] == "ingest")
    assert ing["via"] == ["vision model vis"] and seen["vision_model"] == "vis"
    assert seen["driver"] == "big" and "corrosion on flange F-7" in seen["prompt"]


def test_knowledge_base_search_and_tool():
    tmp = Path(tempfile.mkdtemp())
    kb = KnowledgeBase(tmp / "kb.sqlite")
    kb.add("sop-hotwork.pdf", [{"page": 1, "text": "Scope of the procedure."},
                               {"page": 3, "text": "Hot work permits are valid for one shift only."}])
    kb.add("leave-policy.docx", [{"page": 1, "text": "Casual leave is twelve days per year."}])
    hit = kb.search("hot work permit validity")[0]
    assert (hit["doc"], hit["page"]) == ("sop-hotwork.pdf", 3)
    out = tools.run("search_kb", {"query": "casual leave"}, tools.ToolContext(tmp, "local", kb=kb))
    assert out.startswith("[leave-policy.docx p.1]")
    kb.remove("leave-policy.docx")
    assert [d["doc"] for d in kb.documents()] == ["sop-hotwork.pdf"]


def test_network_scope():
    assert scope("127.0.0.1") == "this machine"
    assert scope("192.168.1.5") == "local network"
    assert scope("8.8.8.8") == "external"


# ---- agent team ----

NOTE_ARGS = {"path": "approval_note.docx", "subject": "Repair of P-101A", "background": "Seal leak found.",
             "findings": ["Seal leak 40 drops/min (limit 10)"], "recommendation": "Repair, cost Rs 4.8 lakh.",
             "approval_sought": "Maintenance Manager approval [sop.txt p.1]"}
TEAM_REQUEST = "Read the attached report, check the SOP for the approval authority and draft an approval note as a Word file."


def make_team(profile=None, **overrides):
    """A scripted team: each role's reply depends on how many times that role has been called."""
    tool = lambda name, args: json.dumps({"tool": name, "args": args})
    final = lambda text, facts: json.dumps({"final": text, "facts": facts})
    replies = {
        "Planner": lambda n: "not json",  # forces the rule-based template
        "Reviewer": lambda n: '{"verdict": "pass"}',
        "Reader": lambda n: final("Read the report.", ["Seal leak 40 drops/min (limit 10)", "Estimated cost Rs 4.8 lakh"]),
        "Researcher": lambda n: tool("search_kb", {"query": "approval authority repair"}) if n == 1 else
            final("Found the rule.", ["Repairs up to Rs 5 lakh are approved by the Maintenance Manager [sop.txt p.1]"]),
        "Writer": lambda n: tool("make_approval_note", NOTE_ARGS) if n % 2 else
            final("Created approval_note.docx.", ["approval_note.docx"]),
        "Analyst": lambda n: tool("run_python", {"code": "print(0.02 * 200 / 0.15 * 1000 * 2**2 / 2)"}) if n == 1 else
            final("Computed the pressure drop.", ["pressure drop = 53333.33 Pa (f * L/D * rho*v^2/2)"]),
        "Responder": lambda n: '{"final": "The report says the seal leaks at 40 drops/min.", "facts": []}',
        "single": lambda n: '{"final": "A flange joins pipes."}',
        **overrides,
    }
    calls = {}

    def script(model, messages):
        system = messages[0]["content"]
        role = next((r for r in replies if f"You are the {r}" in system), "single")
        calls[role] = calls.get(role, 0) + 1
        return replies[role](calls[role])

    agent, tmp = make_agent(script, profile)
    agent.kb.add("sop.txt", [{"page": 1, "text": "Repairs up to Rs 5 lakh are approved by the Maintenance Manager."}])
    (tmp / "ws" / "uploads").mkdir(parents=True)
    (tmp / "ws" / "uploads" / "report.txt").write_text(
        "Seal leak 40 drops/min (limit 10). Estimated cost Rs 4.8 lakh.", encoding="utf-8")
    return Orchestrator(agent), tmp, calls


def types(events):
    return [e["type"] for e in events]


def test_number_grounding():
    sources = "Cost Rs 4.8 lakh. Pressure drop 53333.33333 Pa. Friction factor 0.02. Tag P-101A."
    assert ungrounded("Cost 4.8 lakh, drop 53,333.33 Pa (53.33 kPa), factor 2%, 3 steps", sources) == []
    assert ungrounded("Cuts downtime by up to 30% and cost by 25%", sources) == ["30", "25"]
    # Digits inside tags and dates are identifiers, not quantities: a shortened tag is not a made-up number.
    assert ungrounded("Pump P-101 inspected on 28/9, see line 6\"-P-1001", sources) == []
    assert ungrounded("Savings of 15-20 lakh", sources) == ["15"]


def test_agent_checks():
    ctx = lambda **kw: CheckContext(**{"request": "write tests", "answer": "", "facts": [], "trace": [], "sources": "", **kw})
    passed = {"tool": "run_tests", "args": {}, "result": "exit=0\nRan 2 tests in 0.0s\n\nOK\n"}
    failed = {"tool": "run_tests", "args": {}, "result": "exit=1\nRan 2 tests in 0.0s\n\nFAILED (failures=1)\n"}
    assert CHECKS["tests_passed"](ctx(trace=[failed, passed])) is None
    assert "did not pass" in CHECKS["tests_passed"](ctx(trace=[passed, failed]))
    assert "never called" in CHECKS["tests_passed"](ctx())
    search = {"tool": "search_kb", "args": {}, "result": "[sop.txt p.1] Repairs up to Rs 5 lakh ..."}
    assert CHECKS["citations_real"](ctx(trace=[search], facts=["Manager approves [sop.txt p.1]"])) is None
    assert CHECKS["citations_real"](ctx(trace=[search], facts=["Manager approves [made-up.pdf p.9]"]))
    assert CHECKS["citations_real"](ctx(facts=["x"])).startswith("Search")
    assert CHECKS["file_created"](ctx()) and CHECKS["facts_present"](ctx())


def test_approval_note_must_carry_report_number_and_approver():
    base = {"request": "draft a note", "answer": "", "facts": [], "new_files": [],
            "sources": "Report No: INSP/2026/0417  Date: 28 Sep 2026 ...",
            "known": ["Repairs up to Rs 5 lakh are approved by the Maintenance Manager [sop.txt p.1]"]}
    call = lambda **args: [{"tool": "make_approval_note", "args": args, "result": "created"}]
    check = lambda trace: CHECKS["note_complete"](CheckContext(trace=trace, **base))
    assert check(call(reference="INSP/2026/0417", approval_sought="Approval of the Maintenance Manager")) is None
    assert "INSP/2026/0417" in check(call(reference="[sop.txt p.1]", approval_sought="Maintenance Manager"))
    assert "Maintenance Manager" in check(call(reference="INSP/2026/0417", approval_sought="Approve the repair"))
    assert check([]) is None  # not an approval note: nothing to check


def test_no_gpu_budget_is_capped_for_cpu():
    import subprocess
    from workbench import registry
    real = subprocess.run
    registry.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("nvidia-smi"))
    try:
        budget, device = registry.detect_budget()
    finally:
        registry.subprocess.run = real
    assert budget <= registry.CPU_BUDGET_GB and "CPU" in device


def test_vision_repetition_loop_is_removed():
    looping = "MELT TANK\nEQ NO. 78741\n" + "301-Y-2-O\n" * 200 + "150 GAL"
    text, looped = ingest._clean(looping)
    assert looped and text.count("301-Y-2-O") == ingest.MAX_REPEAT and "150 GAL" in text
    assert ingest._clean("2-5\n2-5\n2-5\nHOOD") == ("2-5\n2-5\n2-5\nHOOD", False)  # a few repeats are real


def test_fact_sheet_fits_budget():
    sheet = FactSheet()
    sheet.add("reader", [f"finding number {i} " + "x" * 80 for i in range(50)])
    text = sheet.text(600)
    assert len(text) <= 600 and "finding number 49" in text and "older facts omitted" in text


def test_simple_task_takes_fast_path():
    team, _, calls = make_team()
    events = list(team.run("What is a flange?"))
    assert events[0]["mode"] == "single" and "plan" not in types(events) and "Planner" not in calls


def test_team_run_end_to_end():
    team, tmp, calls = make_team()
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["source"] == "template" and [s["agent"] for s in plan["steps"]] == ["reader", "researcher", "writer"]
    assert [e["agent"] for e in events if e["type"] == "agent_done"] == ["reader", "researcher", "writer"]
    assert all("unverified" not in e and "error" not in e for e in events if e["type"] == "agent_done")
    review = next(e for e in events if e["type"] == "review")
    assert review["verdict"] == "pass" and review["reviewed_by_model"]
    final = events[-1]
    assert final["type"] == "final" and "approval_note.docx" in final["answer"] and "unverified" not in final
    assert "[sop.txt p.1]" in final["answer"]
    assert (tmp / "ws" / events[0]["workspace"] / "approval_note.docx").is_file()
    # The writer is given the fact sheet, not the raw attachment.
    assert calls == {"Planner": 1, "Reader": 1, "Researcher": 2, "Writer": 2, "Reviewer": 1}


def test_planner_plan_is_used_but_kept_in_bounds():
    plan = json.dumps({"steps": [{"agent": "writer", "goal": "Write the note for P-101A."},
                                 {"agent": "coder", "goal": "Write code."}, {"agent": "ghost", "goal": "x"}]})
    team, _, _ = make_team(Planner=lambda n: plan)
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    p = next(e for e in events if e["type"] == "plan")
    # Planner's goal is kept; the unknown agent and the unneeded coder are dropped; template agents are restored.
    assert p["source"] == "planner" and [s["agent"] for s in p["steps"]] == ["reader", "researcher", "writer"]
    assert p["steps"][2]["goal"] == "Write the note for P-101A."


def test_writer_is_sent_back_for_invented_numbers():
    tool = lambda args: json.dumps({"tool": "make_docx", "args": args})
    bad = {"path": "summary.docx", "title": "Summary", "content": "- Repair cuts downtime by 30%"}
    good = {"path": "summary.docx", "title": "Summary", "content": "- Repair reduces downtime"}
    writer = lambda n: [tool(bad), '{"final": "Created summary.docx.", "facts": ["summary.docx"]}',
                        tool(good), '{"final": "Created summary.docx.", "facts": ["summary.docx"]}'][n - 1]
    team, _, _ = make_team(Writer=writer)
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    rejected = [e for e in events if e["type"] == "invalid" and e.get("agent") == "writer"]
    assert len(rejected) == 1 and "30" in rejected[0]["reply"]
    assert "unverified" not in events[-1]


FIX = lambda n: '{"verdict": "fix", "correction": "Add the report number."}'


def test_large_reviewer_sends_work_back_once():
    team, _, calls = make_team(profile="server", Reviewer=FIX)  # server profile: the 120B-class model reviews
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    assert [e["verdict"] for e in events if e["type"] == "review"] == ["fix", "pass"]
    assert [e["agent"] for e in events if e["type"] == "agent_done"].count("writer") == 2
    assert calls["Reviewer"] == 1 and "correction applied: Add the report number." in events[-1]["answer"]


def test_small_reviewer_comments_but_does_not_send_back():
    team, _, _ = make_team(Reviewer=FIX)
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    assert [e["verdict"] for e in events if e["type"] == "review"] == ["pass"]
    assert [e["agent"] for e in events if e["type"] == "agent_done"].count("writer") == 1
    assert "comment (not applied): Add the report number." in events[-1]["answer"]


def test_failed_correction_keeps_first_version():
    # After the correction the writer only repeats itself; the first note must survive.
    writer = lambda n: (json.dumps({"tool": "make_approval_note", "args": NOTE_ARGS}) if n != 2 else
                        '{"final": "Created approval_note.docx.", "facts": ["approval_note.docx"]}')
    team, tmp, _ = make_team(profile="server", Reviewer=FIX, Writer=writer)
    events = list(team.run(TEAM_REQUEST, ("uploads/report.txt",)))
    assert events[-1]["type"] == "final" and "could not be applied" in events[-1]["answer"]
    assert (tmp / "ws" / events[0]["workspace"] / "approval_note.docx").is_file()


def test_analyst_steps_reach_the_final_answer():
    team, _, _ = make_team()
    events = list(team.run("Calculate the pressure drop in a 200 m pipe of 0.15 m diameter at 2 m/s, "
                           "friction factor 0.02, density 1000 kg/m3."))
    assert [e["agent"] for e in events if e["type"] == "agent_start"] == ["analyst"]
    assert "Calculation steps" in events[-1]["answer"] and "53333.33 Pa" in events[-1]["answer"]


def test_long_document_is_read_in_parts():
    team, tmp, calls = make_team()
    long_text = "\n".join(f"Line {i}: seal leak 40 drops/min, cost Rs 4.8 lakh." for i in range(400))
    (tmp / "ws" / "uploads" / "long.txt").write_text(long_text, encoding="utf-8")
    events = list(team.run("What does the attached report say?", ("uploads/long.txt",)))
    starts = [e["goal"] for e in events if e["type"] == "agent_start"]
    assert calls["Reader"] >= 2 and "part 1 of" in starts[0]
    # A question about a document ends with the Responder's answer, not a list of raw facts.
    plan = next(e for e in events if e["type"] == "plan")
    assert [s["agent"] for s in plan["steps"]] == ["reader", "responder"]
    assert events[-1]["type"] == "final" and events[-1]["answer"].startswith("The report says")


def test_attached_manual_does_not_call_the_researcher():
    team, _, _ = make_team()
    assert team.template(Task("What is the minimum flow according to the attached manual?", ("m.pdf",))) == ["reader", "responder"]
    assert team.template(Task("Check the SOP for the approval authority and draft an approval note.", ("r.pdf",))) == [
        "reader", "researcher", "writer"]


def test_conversation_memory_and_shared_folder():
    seen = []
    single = lambda n: (seen.append(n), '{"final": "Noted."}')[1]
    team, tmp, _ = make_team(single=single)
    first = list(team.run(TEAM_REQUEST, ("uploads/report.txt",), session="chat1"))
    prompts = []
    team.agent.providers["mock"].script = lambda model, messages: (prompts.append(messages[1]["content"]),
                                                                   '{"final": "Noted."}')[1]
    second = list(team.run("Thanks. Who approves it?", session="chat1"))
    assert second[0]["workspace"] == first[0]["workspace"]              # same folder
    assert "Earlier in this conversation" in prompts[0] and TEAM_REQUEST[:40] in prompts[0]
    assert "approval_note.docx" in prompts[0]                           # earlier files are listed
    other = list(team.run("Who approves it?", session="chat2"))
    assert other[0]["workspace"] != first[0]["workspace"] and "Earlier" not in prompts[-1]


def test_agent_definitions_load():
    defs = load_agents()
    assert list(defs) == ["reader", "researcher", "analyst", "coder", "writer", "responder"]
    assert "make_docx" in defs["writer"].system() and "make_docx" not in defs["coder"].system()


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"\n{len(tests)} passed")
