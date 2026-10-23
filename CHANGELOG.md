# Changelog

A record of what was built and every change made, newest first.
Each entry lists what changed, why, and which files were touched.

## 2026-10-04 — Entry 11: Final audit before moving to another PC

**Why:** catch anything that works here but would break on a different machine.

Found and fixed
- **The model server was contacting the internet by itself** (`workbench/modelserver.py`, new).
  During the final test the network monitor logged `ollama.exe → 34.36.133.15:443` with no download
  running. Measured in isolation: the Ollama server alone, with default settings, opened that
  connection within 75 s; started with `OLLAMA_NO_CLOUD=1` it opened none, including during a model
  call. The Ollama desktop app also starts its own server with default settings.
  `start.bat`, `setup.bat` and `check.bat` now stop the desktop app and run the server with cloud
  features off. Model downloads still work. New system-check line: "Model server stays local" (18 checks).
  Reproduced and confirmed: with the desktop app started on purpose, the workbench stopped it,
  restarted the server, and the monitor saw no external connection for the next 60 s.
- **Script line endings:** every `.bat` and `.ps1` file had Unix line endings, which `cmd.exe` can
  misread. All converted to Windows line endings.
- **Unpinned packages** (`requirements.txt`): a later install could have pulled newer, untested
  versions. Now pinned to the exact versions tested; the offline bundle was refreshed to match.
- **Port 8000 already in use** (`workbench/launch.py`): the launcher assumed any program on port 8000
  was the workbench. It now checks, and moves to the next free port (8000–8009) if it is not.
- **Starting before setup** (`start.bat`, `check.bat`): they now say "run setup.bat first" instead
  of failing with a Python error.
- **Low disk space** (`scripts/setup.ps1`): warns when less than 50 GB is free for the models.
- **Deprecated start-up hook** (`workbench/api.py`): replaced with the current FastAPI mechanism.
- Three small code-quality findings from a static check (unused import, unused variable, an f-string).

Checked and found clean
- No non-ASCII characters in any script (they break Windows PowerShell 5.1).
- No path or user name from this machine anywhere in the project.
- Every module compiles; static check reports nothing further.
- The sandbox works when the project path contains a space.

Verified
- **Rehearsal A:** the zip extracted to a new folder, set up through `setup.bat` on **Python 3.11**
  (the project was developed on 3.12): 40 + 7 tests, full system check 17 of 17.
- **Launcher with port 8000 taken** by another program: the workbench came up on port 8001.
- **Rehearsal B:** the zip extracted to a new folder with the offline bundle: packages installed
  from the bundle at the pinned versions; 40 + 7 tests and the system check passed.
- **Final build here:** started through the launcher with the Ollama desktop app running on purpose:
  the app was stopped, the browser click-through of every screen passed with no errors, the monitor
  ran 141 checks (about 5 minutes) with no external connection, and the full system check passed 18 of 18.

Not verified
- A second physical machine, a different Windows user name with non-English characters, and
  `lockdown.bat -SelfTest` (administrator prompt declined earlier).

## 2026-10-04 — Entry 10: Closing the open items from the evaluation

**Why:** five items were left open after entry 9. This entry closes what can be closed on this machine.

| Open item | Outcome |
|---|---|
| Real handwriting, real P&ID, photograph | Tested with three public-domain files (`samples/real/`, sources in `SOURCES.md`). A fault found on the real P&ID was fixed. |
| `pack_offline.bat` and the no-internet route | Bundle built (1.6 GB without models); a fresh copy was set up from the offline packages only. |
| Machine without an NVIDIA GPU | Run on a second, CPU-only model server: works, slowly. A sizing fault was fixed. |
| Approval note content (reference, approver) | New check sends the note back until both are right. Seen working on a real model. |
| Firewall lockdown | Self-test written. It needs administrator approval, which was declined when it ran here. Still unverified. |
| Second physical machine | Cannot be done from here. Still unverified. |

Added
- `samples/real/` — a real P&ID (4000 × 3266), a real cursive letter and a nameplate photograph, with
  `SOURCES.md` giving source, licence and measured results.
- `note_complete` check (`workbench/agents.py`, `config/agents.yaml`): an approval note must carry
  the source report's number as its reference and name the approving authority from the fact sheet.
- `lockdown.bat -SelfTest` (`scripts/lockdown.ps1`): applies the firewall rules, checks from the
  workbench's Python that the internet is blocked and `127.0.0.1` still works, removes the rules,
  and writes `logs\lockdown_selftest.txt`.
- `WORKBENCH_CONFIG` environment variable (`workbench/registry.py`) to point at another config file.
- 4 new tests; 40 core tests in total.

Changed
- **Dense drawings** (`workbench/ingest.py`): on the real P&ID the vision model repeated one tag
  hundreds of times and stopped reading. Now: repeated lines are removed, very large images are
  read in 9 detail views instead of 4, and a view where the model looped is split in four and read
  again. The prompt also asks for the text inside instrument circles.
- **No-GPU sizing** (`workbench/registry.py`): without an NVIDIA GPU the budget was half the system
  RAM, which on a 32 GB machine chose 14B models to run on the CPU. It is now capped at 6 GB so
  the small models are used.

Verified
- **Real P&ID:** before the fix, 15 of 24 labels checked by eye in one corner plus a repetition loop;
  after, 24 of 24 labels and 5 of 9 instrument circles, 18 equipment numbers on the sheet. 315 s, 33 detail views.
- **Real handwriting:** about 41 of 48 words correct; the sense is kept. 3 s.
- **Nameplate photograph:** 11 fields correct, 2 wrong (motor type letters, RPM rows mixed). 5 s.
- **Offline bundle:** 24 package files (35 MB), sandbox image 107 MB, Ollama installer 1.5 GB. A fresh copy
  installed its packages with the network option disabled and passed 40 + 7 tests and the system
  check. The image file loads.
- **CPU-only server** (GPU hidden from a second Ollama instance; `ollama ps` showed "100% CPU"):
  full system check 17 of 17; a question in 17 s; the scanned-report approval note in 465 s,
  correct approver, but the report number was misread as "INSF/2026/0417" by the small vision model.
- **Approval-note check on 12 GB:** Writer sent back once for the reference; final note has
  reference INSP/2026/0417 and "Approval from the Maintenance Manager". 47 s.
- 40 core tests, 7 API tests, full system check 17 of 17.

Not verified
- `lockdown.bat`: the administrator prompt was declined, so no rules were applied or tested.
  No rules were left on the machine.
- A second physical machine.
- Copying the models into the offline bundle (`pack_offline.bat -Models`), which is a plain folder copy of about 50 GB.
- The installer inside the bundle was downloaded but not run.

## 2026-10-04 — Entry 9: Judge-style evaluation, the fixes it led to, and the release package

**Why:** assess the system the way a judge would against the problem statement, fix what that
exposed, and make the folder ready to move.

Added
- **Conversation memory** (`workbench/orchestrator.py`, `workbench/api.py`, UI): turns that share a
  session share a folder, a fact sheet and their history. **New chat** button starts a fresh one.
- **Long documents read in parts** (`orchestrator.py`): the Reader takes a long attachment in up to
  8 parts and each part adds facts. A part with nothing relevant may return no facts.
- **Responder agent** (`config/agents.yaml`): a question about documents now ends with a written
  answer instead of a list of raw facts.
- **Large drawings read in detail views** (`workbench/ingest.py`): images 3000 px or wider, and
  scanned PDF pages of A3 size and up, are read as an overview plus four overlapping quarters.
- **Evidence report** (`workbench/report.py`, `/network/report`): one printable page with the model
  endpoints, monitoring period, every connection seen, and the egress test results.
- **Network log file** `logs/network.jsonl`: every non-local connection and blocked attempt.
- **Firewall lockdown** (`lockdown.bat`, `unlock.bat`, `scripts/lockdown.ps1`) and a
  **firewall test** button (`/network/firewall-test`).
- **Extended sandbox image** (`scripts/sandbox.Dockerfile`): Python with numpy, pandas, sympy and
  openpyxl. Built by `setup.bat`; the basic image is the fallback.
- **Request queue** (`api.py`): a second task waits for the first instead of fighting for the GPU.
- **API tests** `tests/test_api.py`: a real server over HTTP with a mock model, 7 tests.
- **Sample files** (`samples/make_samples.py`): a P&ID-style drawing with a known tag list and a
  note in a handwriting-style font.
- **Release package** (`package.bat`, `scripts/package.ps1`) → `dist\sovereign-workbench.zip`.
- `README.md`, `DEMO.md`, `EVALUATION.md`.

Changed
- **Models answer 3 to 7 times faster** (`workbench/providers.py`, `config/models.yaml`,
  `workbench/agent.py`): the qwen3 models' hidden reasoning is switched off by default
  (`think: false`) and switched back on for the retry when a result is sent back.
  Measured on three tasks with identical results: note 91 → 32 s, calculation 51 → 7 s, drawing 61 → 24 s.
- **Empty replies are retried** (`providers.py`): `qwen3:4b` could spend its whole reply on hidden
  reasoning and return nothing. Such a reply is retried without reasoning, then without JSON mode.
- **Number check no longer flags tag fragments** (`workbench/agents.py`): "P-101" was reported as an
  invented number 101, sending a correct note back twice. Digits inside tags and dates are identifiers.
- **The Researcher is not called for "the attached manual"** (`orchestrator.py`), and may return no rules.
- **Final answer uses only this turn's facts**, so an earlier turn's rules no longer reappear.
- **Writer rules:** name the approver and the report number in an approval note; reuse the file name when sent back.
- **Setup** (`scripts/setup.ps1`): stops with a clear message when the folder path is too long for
  Windows; builds or loads the extended sandbox image; runs the API tests.
- Upload limit 50 MB; session ids validated (they become folder names).
- **The Reader has no tools** (`config/agents.yaml`): the input layer already gives it the text. With a
  tool it once asked for pages 10 to 25 of an 8-page file until the step limit. Question on the
  8-page manual: 25 → 11 s.
- **A run of failing tool calls counts as going in circles** (`workbench/agent.py`): three failures in a
  row trigger escalation or, with no bigger model, a stop after two more.

Verified with real models, 12 GB profile
| Task | Result | Time |
|---|---|---|
| Scanned report → approval note | Correct, SOP cited, approver named | 40 s |
| Code with tests | Passed in the sandbox | 26 s |
| Calculation | 53,333.33 Pa with steps | 15 s |
| Drawing → Excel | 11 of 11 tags | 41 s |
| Question on an 8-page manual (answer on page 6) | Correct: 85 m3/h, FCV-105 | 25 s |
| PowerPoint | 3 content slides, no invented figures | 9 s |
| Three-turn conversation | Follow-ups used the earlier facts and files | 5–69 s per turn |

- Vision: sample drawing 12 of 13 tags; large small-print sheet 9 of 13 without detail views, 12 of 13 with.
  Handwriting-style note 7 of 7 items.
- Simulated 6 GB laptop (4B models): approval note 48 s (was 336 s before the reasoning change);
  note summary 8 s. The note still does not name the approver in its "Approval Sought" section.
- 37 core tests, 7 API tests, full system check 17 of 17, browser click-through with no errors.
- After the last two changes the document tasks were run again: manual 11 s, approval note 32 s,
  drawing 24 s (11 of 11 tags), handwriting-style note 19 s. In that run the note's reference field
  held the SOP citation instead of the report number.
- Release zip extracted to a new folder: setup, both test suites and the full system check passed.

Not verified
- `lockdown.bat`: this session had no administrator rights. The firewall test button works and
  reported "not blocked", as expected with no lockdown.
- Real handwriting, a real P&ID, a photograph.
- A second physical machine; a machine without an NVIDIA GPU; `pack_offline.bat`.

## 2026-10-04 — Entry 8: Agent team for multi-step tasks, and the weaknesses file

**Why:** one generic agent with every tool broke down on small models (wrong tool, invented
numbers, lost calculation steps, context overflow). Specialised agents give each job its own
prompt, tools, model and acceptance check.

Added
- `WEAKNESSES.md` — every known weak point: evidence, impact, fix, status. Kept current from now on.
- `config/agents.yaml` — the team: Reader, Researcher, Analyst, Coder, Writer. Each entry sets
  the job, model type, allowed tools and checks. Adding an agent = adding an entry.
- `workbench/agents.py` — loads the definitions and holds the checks: `facts_present`,
  `numbers_grounded`, `files_grounded`, `file_created`, `code_ran`, `tests_passed`, `citations_real`.
  Number grounding: every number in a result must appear in the request, the documents, the
  knowledge base or tool output (rounding and unit scale such as Pa/kPa allowed).
- `workbench/orchestrator.py` — Planner, shared fact sheet, step execution, Reviewer, final answer.
  A simple question still goes to the single agent (fast path).
- UI: plan strip showing each agent as a stage with live status; steps grouped under each agent;
  new **Agents** screen.
- `/agents` endpoint; system check gains "Agent team task end to end" (17 checks in total).

Changed
- `workbench/agent.py` — the loop is now `run_loop(...)`, shared by single-agent mode and every
  team agent. It takes an acceptance check and records each tool call. A failed check sends the
  work back (up to twice, then a bigger model), and is reported as "not verified" if still failing.
- `workbench/router.py` — `route_for(capability, complexity)` so each agent gets its own model.
- `workbench/tools/__init__.py` — `describe(only=...)` to show an agent only its tools.
- `workbench/providers.py` — every reply is capped at 3,000 tokens and the request timeout is
  300 s. Before, one model call in JSON mode ran for over ten minutes without returning.
- `workbench/kb.py` — search now matches word variants ("approval" finds "approved"). Existing
  knowledge bases are migrated automatically.
- `workbench/api.py` — `/chat` runs through the orchestrator.
- `tests/test_core.py` — 12 new tests; 31 in total.

Design decisions made during testing
- **The Planner only writes goals on small models.** A 14B Planner sent a presentation task to
  the Researcher and Analyst, which pulled unrelated SOP figures into the slides. Below tier 3
  the rules choose the agents and the Planner writes each agent's goal; a tier 3+ model may add agents.
- **The Reviewer only comments on small models.** A 14B Reviewer counted the title slide as an
  extra slide and sent good work back, after which the Writer looped and the task failed. Below
  tier 3 its remark is shown to the user and not enforced; a tier 3+ Reviewer can send work back
  once, and if the redo fails the first version is restored.

Verified with real models (12 GB profile)
| Task | Agents | Result | Time |
|---|---|---|---|
| Scanned inspection report → approval note | Reader, Researcher, Writer | Correct note, SOP cited | 81 s |
| Pressure-drop calculation | Analyst | 53,333.33 Pa with all four steps in the answer | 36 s |
| Pressure-drop function with tests | Coder | Tests passed after one send-back | 66 s |
| PowerPoint, 3 slides | Writer | Created, no invented figures | 28 s |
| Scanned image → Excel (through the browser) | Reader, Writer | Correct sheet, downloaded | — |

- Simulated 6 GB laptop (4B models): approval-note task completed in 127 s. The note's findings
  are correct, but its "Approval Sought" section does not name the approver; the final answer does.
- 31 of 31 tests; full system check 17 of 17; browser click-through with no console errors.

Not verified
- The number-grounding check rejecting an invented figure from a real model: in the final runs
  the Writer did not invent any, so the check has only been exercised by the automated test.
- Tier 3+ behaviour (Planner adding agents, Reviewer sending work back) with a real large model.

## 2026-10-03 — Entry 7: Portable setup, hardware auto-detection, system check, and fixes from full verification

**Why:** the folder must run on another PC or laptop, adapt to its hardware, and prove that
every function works there.

Added
- `setup.bat`, `scripts/setup.ps1` — one-time setup: Python environment, packages, Ollama,
  models that fit the machine, sandbox image, samples, tests, system check. Uses `offline\`
  when present.
- `pack_offline.bat`, `scripts/pack_offline.ps1` — builds `offline\` (packages, sandbox image,
  Ollama installer, optionally the models) for a machine with no internet.
- `check.bat` — runs the tests and the full system check.
- `workbench/doctor.py` — system check with 16 checks (12 quick, 4 that call the models), each
  reporting PASS / WARN / FAIL and a fix. `--pull` downloads the models recommended for the hardware.
- `workbench/launch.py` — starts Ollama if needed, then the server, then the browser. Used by `start.bat`.
- `SETUP.md` — how to move the folder and set it up, online or offline.
- UI: **System check** screen; Models screen shows the measured memory budget and recommended models.

Changed
- `workbench/registry.py`, `config/models.yaml` — `profile: auto` measures NVIDIA GPU memory, or
  half the system RAM when there is no GPU. `WORKBENCH_VRAM` overrides it. Three small models
  added for low-memory laptops: `qwen3:4b`, `qwen2.5-coder:3b`, `gemma3:4b`.
- `workbench/router.py` — only the two largest models that fit are first choices; smaller ones
  are backups. Requests for presentations, spreadsheets and documents count as complex.
- `workbench/agent.py`
  - Each task now runs in its own folder, `workspace/tasks/<id>/`. Before, `run_tests` picked up
    test files left by earlier tasks and reported a pass for the wrong code.
  - An answer that names a file which does not exist is rejected and the model is told to create it.
    After two rejections the answer is passed through with a visible warning.
  - A model that keeps repeating itself with no bigger model available now stops after 3 repeats
    with a clear message, instead of using all 20 steps.
  - Coding tasks no longer see the Word/Excel/PowerPoint tools (a 7B model was writing code into a Word file).
  - Prompt: no invented statistics; a file exists only if a tool created it.
- `workbench/tools/sandbox.py`
  - Output is read as UTF-8. Before, any output containing ρ, Δ or ° came back as "None" on Windows.
  - A trailing bare expression is printed, as in a notebook; empty output adds a hint to use print().
  - Tool description states that only the standard library is available.
- `workbench/tools/office.py` — refuses a non-matching file extension; drops empty slides; clearer slide count.
- `workbench/api.py` — `/doctor` endpoint; `/models` reports device and recommended models;
  `__pycache__` hidden from file lists.
- `workbench/ui.html` — favicon (removed a 404), per-task file links, warning for unverified files.
- `start.bat` — uses the project's own Python environment and the launcher.
- `tests/test_core.py` — 5 new tests; 19 in total.

Verified
- 19 of 19 tests pass.
- `setup.ps1` run on this machine from a clean state, and again on a copy of the folder in a
  different location with a space in its path: both finished with all checks passing.
- Full system check on this machine: 16 of 16 pass, including a call to the general, coding and
  vision models and one agent task.
- Browser click-through in headless Edge, started through the launcher: image attachment → Excel
  file created and downloaded; knowledge-base upload and search; Models; Network monitor and egress
  test; Audit log; System check. No console errors.
- Real-model tasks: Excel from a scanned image (content correct), PowerPoint (3 content slides),
  pressure-drop calculation computed in the sandbox (53,333.33 Pa, matches a hand calculation).
- Simulated 6 GB laptop (`WORKBENCH_VRAM=6`, small models only): full system check 16 of 16;
  file task, coding task with tests, and scanned report → approval note all completed.
- Network monitor: showed two external connections from `ollama.exe` while models were
  downloading, and none once the downloads had finished.

Not verified
- Setup on a second physical machine, a machine with no NVIDIA GPU, or a machine with no internet.
- `pack_offline.bat` has not been run.
- Handwriting and real engineering drawings. AirLLM with real weights.

Known weaknesses seen in testing
- The PowerPoint task included invented percentages despite the prompt rule against it.
- After a malformed reply, the final answer of the calculation task gave the result without the
  steps; the steps are visible in the tool output.
- Models reach for numpy or sympy first; the sandbox has only the standard library, so they
  lose a step.

## 2026-10-03 — Entry 6: Web UI, network monitor, input layer, knowledge base, deliverables

**Why:** cover every requirement in the problem statement and give a usable product.

Added
- `workbench/ingest.py` — input layer. Reads text, PDF (text layer), scanned PDF pages and
  images (through the local vision model), Word, Excel and PowerPoint, page by page.
- `workbench/kb.py` — knowledge base on SQLite full-text search with BM25 ranking and page
  citations. One local file, no external service.
- `workbench/netmon.py` — network monitor. Samples the OS connections of the workbench and
  model-server processes every 2 seconds and remembers any address outside this machine.
- `workbench/tools/documents.py` — tools `read_document` and `search_kb`.
- `workbench/tools/office.py` — tools `make_docx`, `make_approval_note`, `make_xlsx`, `make_pptx`.
- `workbench/ui.html` — rewritten as a full interface: Workbench (chat, attachments, live
  steps, file downloads), Knowledge base, Models, Network monitor, Audit log. Light and dark
  themes. One file, no external fonts or scripts.
- `samples/make_samples.py` — creates a scanned inspection report (image-only PDF) and an SOP.
- `CHANGELOG.md` — this file.

Changed
- `workbench/api.py` — new endpoints: `/upload`, `/files`, `/files/{path}`, `/kb`,
  `/kb/upload`, `/kb/search`, `/kb/{name}`, `/network`, `/network/canary`.
- `workbench/agent.py` — attachments are read by the input layer before the loop starts and
  their text is given to the model; new `ingest` event; vision-model call; knowledge base
  attached to the tool context; system prompt extended for deliverables, citations and
  calculation steps.
- `workbench/router.py` — attachments no longer make the vision model the driver. The driver
  is chosen from the request text; the vision model is used by the input layer.
- `workbench/tools/__init__.py` — tool context carries the vision function and knowledge base.
- `config/models.yaml` — vision models listed in preference order (`qwen2.5vl:7b` first).
- `requirements.txt` — added psutil, pymupdf, python-docx, openpyxl, python-pptx.
- `tests/test_core.py` — 4 new tests (every input type, attachment flow, knowledge base,
  network scope); 14 in total.
- `build.md` — rewritten with a requirement-coverage table.

Verified
- 14 of 14 tests pass.
- Real run: scanned inspection report (image-only PDF) → read by `qwen2.5vl:7b` → SOP found
  in the knowledge base → `qwen3:14b` produced `approval_note.docx` naming the correct
  approval authority, in 4 steps.
- Network monitor reported zero external connections during the run. Egress test: model
  client pointed at an internet address was refused; a connection from inside the sandbox
  failed with "Network is unreachable".
- UI loaded in headless Edge and its status indicator updated from the API.

Not verified
- A full task clicked through the browser UI.
- Excel, PowerPoint and calculation tasks with a real model (tools are tested directly).
- Handwriting and real engineering drawings.

## 2026-10-03 — Entry 5: First web page, start script, context fix

- `workbench/ui.html`, `start.bat` — minimal page and a double-click launcher.
- `workbench/providers.py` — server error messages are kept instead of a bare "HTTP 500".
- `workbench/agent.py` — step limit raised from 12 to 20.
- `config/models.yaml` — context set to 4096 to match what Ollama loads on a 12 GB GPU.
- Verified: coding task completed by `qwen2.5-coder:14b`, tests passed in the sandbox in 9 steps.

## 2026-10-03 — Entry 4: AirLLM option

- `workbench/providers.py` — `AirLLMProvider`: runs a model larger than the GPU one layer at a
  time. Off by default; local weights only; Hugging Face hub forced offline.
- `workbench/registry.py`, `workbench/router.py` — `escalation_only` models are never picked
  first and are used only when other models fail.
- `config/models.yaml` — `airllm` provider block and an `airllm/big` model entry.
- Not verified with real weights: the `airllm` package and a large model are not installed.

## 2026-10-03 — Entry 3: Fixes found by the first real coding run

- Problem: the 7B coding model imported its test file instead of running it and reported success.
  Fix: `run_tests` tool in `workbench/tools/sandbox.py`; prompt rule in `workbench/agent.py`.
- Problem: the model repeated the same failing edit until the step limit.
  Fix: stuck detection in `workbench/agent.py` — a repeated action with the same result
  escalates to a bigger model, or tells the model to change approach.
- `workbench/router.py` — a missing specialist model now falls back to a general model;
  tasks that mention tests or verification count as complex.

## 2026-10-03 — Entry 2: Real models

- Installed Ollama 0.35.1. Models: `qwen3:8b`, `qwen3:14b`, `qwen2.5-coder:7b`,
  `qwen2.5-coder:14b`, `gemma3:12b`, `qwen2.5vl:7b` (about 42 GB).
- Pulled `python:3.12-slim` for the sandbox; confirmed it has no network access.
- Verified: first real agent task (write a file, read it back) completed by `qwen3:8b`.

## 2026-10-03 — Entry 1: Core system

- `config/models.yaml`, `workbench/registry.py` — model registry and hardware profiles.
- `workbench/router.py` — task classification and model selection.
- `workbench/providers.py`, `workbench/netguard.py` — model client restricted to local endpoints.
- `workbench/agent.py` — agent loop with JSON actions, escalation and fallback.
- `workbench/tools/` — file tools and Python sandbox.
- `workbench/audit.py`, `workbench/api.py`, `workbench/__main__.py` — audit log, API, command line.
- `tests/test_core.py`, `requirements.txt`, `build.md`.
