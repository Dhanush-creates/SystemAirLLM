# Evaluation against the problem statement

A self-assessment written the way a judge would mark it: each requirement of SIH problem
statement 26117, the evidence, and a verdict. Verdicts: **Met**, **Partly met**, **Not met**.
All evidence is from runs on this machine (RTX 5070, 12 GB) on 3–4 October 2026.

## 1. Expected solution (the four demonstrations and the proof)

| Required | Evidence | Verdict |
|---|---|---|
| Working local deployment on one workstation with a mid-range GPU | `setup.bat` then `start.bat`; full system check 17 of 17; a clean copy unzipped elsewhere set up and passed the same check | Met |
| Model auto-selection across at least two task types | General tasks → `qwen3:14b`; coding → `qwen2.5-coder:14b`; scans and drawings → `qwen2.5vl:7b`. The choice and its reason are shown on every task | Met |
| An agentic task end to end: scanned inspection report → key findings → approval note as Word | Reader, Researcher and Writer agents; scan read by the vision model; SOP cited; `approval_note.docx` names the correct approver. 40 s | Met |
| A coding task run and verified in a sandbox | Coder writes the function and tests; tests run in Docker with networking disabled; a failing run is sent back until it passes. 26 s | Met |
| A multimodal task on an image or scanned document | P&ID-style drawing → Excel list, 11 of 11 equipment and instrument tags correct. 41 s | Met, on a clean sample drawing |
| Logs or a visible monitor showing no external calls | Live monitor of OS connections, egress test (both attempts blocked), printable evidence report, audit log, `logs/network.jsonl` | Met for observation; enforcement by firewall is scripted but untested (see section 4) |

## 2. Description requirements

| Required | Evidence | Verdict |
|---|---|---|
| Self-hosted; nothing leaves the premises | Model endpoint refused unless it is on this machine; server binds to `127.0.0.1`; UI loads no external resource (tested). The model server's own cloud connection, found by the monitor, is switched off by the launcher (measured: none in 60 s) | Met |
| Not locked to one model; several at once | Nine models installed; registry in `config/models.yaml` | Met |
| New models addable without redesign | One YAML line; any OpenAI-compatible server; three small models were added this way during development | Met |
| Plans multi-step work | Planner and rule-based plan shown as stages in the UI | Met; on models below 14B-class size the rules choose the agents and the Planner only writes goals |
| Local tools: file read/write, sandboxed code, spreadsheets, document search | 13 tools, each agent limited to its own | Met |
| Iterates instead of answering once | Results failing a check are sent back; stuck models are escalated or stopped | Met |
| Scanned PDFs | Scan-only PDF read correctly | Met |
| Handwritten notes | Real cursive letter: about 85% of words correct, sense kept. Handwriting-style note: 7 of 7 items | Met, as a draft transcription |
| Engineering drawings | Real public-domain P&ID (4000 × 3266): 24 of 24 labels checked, 5 of 9 instrument circles, in about 5 minutes. Sample drawing → Excel: 11 of 11 tags | Partly met: text labels are read well, small instrument circles are often missed |
| Photographs | Real nameplate photograph: 11 fields right, 2 wrong | Met, with occasional misreads |
| Real deliverables: approval notes, PPT, Word, Excel, working code, calculations with steps | All six produced by real models and opened/read back | Met |
| Grounded in the organisation's manuals and SOPs through a local connector | Knowledge base with upload, search and page citations; citations are checked against what the search returned | Met; search is keyword-based |

## 3. What works beyond the brief

- **Scales down and up:** the same code completed the approval-note task on a simulated 6 GB
  laptop with 4B models (48 s) and is configured for a 120B-class server model.
- **Checks on results:** numbers must come from the documents, the knowledge base or tool
  output; a file named in an answer must exist; tests must pass; citations must be real.
- **Conversation memory, long-document reading in parts, request queue, evidence report.**
- **Self-check:** a System check screen that tests every function on the machine it runs on.

## 4. Where a judge could still find fault

| Finding | Why it matters | Status |
|---|---|---|
| Instrument circles on dense drawings | 5 of 9 read on the real P&ID; a dense sheet takes about 5 minutes | Open: do not rely on it for a complete instrument list |
| Firewall lockdown is untested | The administrator prompt was declined when the self-test ran | Open: run `lockdown.bat -SelfTest` once and read `logs\lockdown_selftest.txt` |
| Not run on a second physical machine | Verified here, on fresh copies of the folder, from the offline bundle, and on a CPU-only model server | Open |
| The monitor cannot see inside Docker | Sandbox traffic is not observable from the host | Mitigated: the sandbox has networking disabled and the egress test proves it |
| Content can still be wrong | A model once wrote the wrong inspection date in a note; number checks do not catch wrong words | Mitigated: every draft says "review before signing" |
| Approval note reference and approver | Earlier runs had the wrong reference or no approver | Fixed: a check sends the note back until both are right |
| Small models are rough | On 4B models the note omitted the approver's name and one summary garbled a tag | Open: use 8 GB or more for the demo |
| Short context (4,096 tokens) on 12 GB | Long documents are read in parts, at most 8 parts and 10 scanned pages | Mitigated |
| Keyword search only | A question worded differently from the SOP may miss it | Open |
| One user at a time, no login | Fine for a demo, not for deployment | Open |
| Large-model behaviour is tested only with a mock | Planner adding agents and Reviewer sending work back at 120B scale | Open |

## 5. Timings on this machine (12 GB, second run of each)

| Task | Time |
|---|---|
| Scanned report → approval note (3 agents) | 32–40 s |
| Code with tests in the sandbox | 26 s |
| Calculation with steps | 15 s |
| Drawing → Excel tag list | 24–41 s |
| Question on an 8-page manual | 11–25 s |
| Handwriting-style note → summary | 19 s |
| PowerPoint, 3 slides | 9 s |
| Follow-up question in the same conversation | 5–18 s |

## 6. Verification totals

| Check | Result |
|---|---|
| `tests/test_core.py` (logic, agents, checks, input types) | 40 of 40 |
| Offline bundle: fresh copy set up without the network | Passed |
| CPU-only model server: full system check | 17 of 17 |
| `tests/test_api.py` (real server over HTTP, mock model) | 7 of 7 |
| Full system check | 18 of 18 |
| Fresh copy from the zip, set up on Python 3.11 | Passed |
| Browser click-through, every screen | No errors |
| Clean package unzipped, set up and checked | Passed |
