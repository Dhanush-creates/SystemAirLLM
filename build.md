# Sovereign On-Premise Agentic AI Workbench — Build Plan

SIH problem statement 26117 (MRPL). A self-hosted, air-gapped AI workbench: multiple
open-weight models, automatic model selection, an agent that plans and uses local
tools, real deliverables (Word/PPT/Excel/code), and visible proof that nothing leaves
the machine.

Every change is recorded in `CHANGELOG.md`. Known weak points are in `WEAKNESSES.md`. A judge-style
assessment against the problem statement is in `EVALUATION.md`. Start with `README.md`.

## 1. Requirement coverage

Status: **Working** = run with real models on this machine. **Built** = code and automated
tests pass, not yet run with a real model. **Not built** = still to do.

| Problem-statement requirement | Our solution | Status |
|---|---|---|
| Runs entirely on the organisation's own GPU server | FastAPI + Ollama on one machine; every endpoint must be local (`netguard.py`) | Working |
| Multiple open-weight models at once | Model registry `config/models.yaml`; 6 models installed | Working |
| Automatic model selection by task | Router: task type (general / code) × complexity (low / high) × hardware profile; vision model chosen for scans and images | Working |
| New models addable without redesign | One YAML entry per model; any OpenAI-compatible server | Working |
| Scales from small to 120B-class models | Hardware profiles, tiers, escalation, fallback, optional AirLLM | Working (AirLLM: Built) |
| Agent plans multi-step work and iterates | Agent team: Planner, Reader, Researcher, Analyst, Coder, Writer, Reviewer, each with its own tools, model and acceptance check (`orchestrator.py`, `config/agents.yaml`); single agent for simple questions | Working |
| File read and write | `read_file`, `write_file`, `list_files`, confined to the workspace | Working |
| Code execution in a sandbox | `run_python`, `run_tests` in Docker with `--network none` | Working |
| Spreadsheet work | `make_xlsx` (with formulas), Excel reading in `read_document` | Working |
| Internal document search | `search_kb` over a local SQLite full-text index with page citations | Working |
| Scanned PDFs, handwriting, drawings, photographs | Input layer `ingest.py`: text layer where present, local vision model otherwise | Working for a printed scan; handwriting and real P&IDs not yet tried |
| Real deliverables: approval notes, Word, PPT, Excel | `make_approval_note`, `make_docx`, `make_pptx`, `make_xlsx` | Working (approval note, Excel, PowerPoint run with real models; plain Word tested directly) |
| Working code | Coding model writes code and tests, verified in the sandbox | Working |
| Calculations with steps shown | Computed with `run_python`; prompt requires formula, inputs and steps | Working (the final answer sometimes omits the steps; they are in the tool output) |
| Grounding in manuals, SOPs, past correspondence | Knowledge base upload + `search_kb` + citations | Working |
| Proof that no external calls are made | Network monitor (OS sockets of our processes), egress test, audit log | Working |
| Usable like Claude or Codex | Web UI: chat, attachments, live agent steps, downloads | Working (every screen clicked through in headless Edge) |
| Runs on other machines, large or small | `setup.bat`, hardware auto-detection, system check, offline pack (`SETUP.md`) | Working on this machine and on a simulated 6 GB laptop; not yet run on a second physical machine |

## 2. Design principle: one codebase, big model to small model

| Mechanism | What it does |
|---|---|
| Model registry | Each model is one entry: provider, capabilities, tier, VRAM need, context size. |
| Hardware detection | `profile: auto` measures NVIDIA GPU memory (or half the system RAM). Named profiles `workstation` / `server` and `WORKBENCH_VRAM` override it. |
| Complexity-aware routing | The two largest models that fit are first choices: complex task → the largest, simple task → the lighter one. Smaller models are backups. |
| Answer checks | A file named in the answer must exist; a model repeating itself is stopped. |
| Trust scales with model size | Below tier 3 the rules pick the agents and the Reviewer only comments. From tier 3 the Planner may add agents and the Reviewer may send work back. |
| Fact sheet | Agents pass a compact list of checked facts instead of the whole conversation, so multi-step work fits a small context. |
| Escalation | Two invalid replies, or a repeated action with the same result, moves the task to a bigger model. |
| Fallback | If a model or its server fails, the next available candidate takes over. |
| AirLLM option (off by default) | Runs a 70B-class model on a small GPU one layer at a time. Slow, so it is used only when the normal models fail. Not yet run with real weights. |
| Universal JSON action protocol | Tool calls are plain JSON in the reply, so they work on any model. |
| Context budgeting | History, attachments and tool output are trimmed to each model's context size. |

## 3. Architecture

```
Browser UI (ui.html) ──► FastAPI (api.py) ──► Network monitor (netmon.py)
                              │
                         Agent loop (agent.py) ── audit log (audit.py)
                              │
   ┌──────────────┬───────────┼────────────────┬──────────────────┐
 Input layer    Router      Tools            Knowledge base    Providers ── netguard
 (ingest.py)  (router.py)  (tools/)          (kb.py, SQLite)   (providers.py)
 text, PDF,       │        files, sandbox,                       Ollama / vLLM /
 scans, images, Registry   documents, office                     AirLLM / mock
 Word, Excel,  (registry.py)
 PowerPoint
```

Request flow: task and attachments → router picks the driving model → input layer reads
each attachment (vision model for scans and images) → agent loops (model reply → tool
call → observation) → final answer and files. Every event is streamed to the UI and
written to the audit log.

## 4. Input layer: what each file type goes through

| Input | How it is read |
|---|---|
| Plain text, CSV, JSON, code | Read directly |
| PDF with a text layer | Text extracted per page (PyMuPDF) |
| Scanned PDF page (no text layer) | Page rendered to an image, read by the vision model |
| Image: PNG, JPG, BMP, TIFF, GIF | Resized to at most 1600 px, read by the vision model |
| Word `.docx` | Paragraphs and tables (python-docx) |
| Excel `.xlsx` | Each sheet as rows, formulas kept (openpyxl) |
| PowerPoint `.pptx` | Text of each slide (python-pptx) |

Limits: at most 10 vision-read pages per document; long text is truncated to the model's
context and the agent can ask for a specific page with `read_document`.

## 5. Modules

| File | Role |
|---|---|
| `config/models.yaml` | Models, providers, hardware profiles, AirLLM toggle |
| `workbench/registry.py` | Loads config, filters models by profile |
| `workbench/router.py` | Task classification, model selection, escalation order |
| `workbench/providers.py` | OpenAI-compatible client, AirLLM provider, mock provider |
| `workbench/netguard.py` | Refuses any non-local model endpoint |
| `workbench/netmon.py` | Samples OS network connections of workbench and model-server processes |
| `workbench/agent.py` | The agent loop (`run_loop`), attachment ingestion, escalation, fallback; single-agent mode |
| `workbench/orchestrator.py` | Agent team: planning, fact sheet, step execution, review, final answer |
| `workbench/agents.py`, `config/agents.yaml` | Agent definitions and their acceptance checks |
| `workbench/ingest.py` | Input layer for all file types |
| `workbench/kb.py` | Knowledge base (SQLite FTS5, BM25) |
| `workbench/tools/` | `files`, `sandbox`, `documents`, `office` |
| `workbench/audit.py` | JSONL audit trail |
| `workbench/api.py` | HTTP API |
| `workbench/ui.html` | Web UI (single file, no external resources) |
| `workbench/doctor.py` | System check (18 checks) and model download for this hardware |
| `workbench/modelserver.py` | Runs the model server with its cloud features off and stops the Ollama desktop app |
| `workbench/launch.py` | Starts Ollama, the server and the browser |
| `setup.bat`, `start.bat`, `check.bat`, `pack_offline.bat`, `scripts/` | Setup, start, verify, offline packaging |
| `samples/make_samples.py` | Creates the demo scanned report and SOP |
| `workbench/report.py` | Printable sovereignty evidence report |
| `lockdown.bat`, `unlock.bat`, `package.bat` | Firewall lockdown and release packaging |
| `tests/test_core.py`, `tests/test_api.py` | 40 logic tests and 7 HTTP tests, run without any model |

## 6. Phases

- [x] **Phase 1 — Core:** registry, router, providers, agent loop, file tools, sandbox, audit, tests
- [x] **Phase 2 — Real models:** Ollama, six models, Docker sandbox image
- [x] **Phase 3 — Input layer:** upload, PDF, scans, images, Word, Excel, PowerPoint
- [x] **Phase 4 — Knowledge base:** upload, index, search with citations
- [x] **Phase 5 — Deliverables:** approval note, Word, Excel, PowerPoint
- [x] **Phase 6 — UI and network monitor**
- [x] **Phase 7 — Portability and verification:** setup and offline scripts, hardware auto-detection, system check, browser click-through, real-model runs of every deliverable, simulated 6 GB laptop
- [x] **Phase 8 — Agent team:** specialised agents with acceptance checks, Planner, Reviewer, fact sheet, UI plan strip (`CHANGELOG.md` entry 8). Open weak points are tracked in `WEAKNESSES.md`.
- [x] **Phase 9 — Judge-style evaluation and release:** conversation memory, long documents in parts, Responder agent, detail views for drawings, evidence report, firewall lockdown scripts, extended sandbox, request queue, API tests, 3–7× faster replies, release zip (`CHANGELOG.md` entry 9, `EVALUATION.md`)
- [x] **Phase 10 — Closing open items:** real P&ID, handwriting and photograph measured; dense-drawing fix; offline bundle built and used; CPU-only run; approval-note content check; lockdown self-test (`CHANGELOG.md` entry 10)
- [x] **Phase 11 — Final audit before the move:** line endings, pinned packages, port fallback, rehearsals on Python 3.11 and from the offline bundle (`CHANGELOG.md` entry 11)
- [ ] **Phase 12 — On the other PC**
  - [ ] Run setup on the actual laptop; run `pack_offline.bat` and try the offline route
  - [ ] Run `lockdown.bat -SelfTest` and approve the administrator prompt
  - [ ] Stop Ollama's desktop app from checking for updates (run `ollama serve` only)
  - [ ] Semantic (embedding) search alongside keyword search
  - [ ] Try AirLLM with real weights
  - [ ] User login and per-department knowledge bases

## 7. Running

```
setup.bat      # once per machine: environment, Ollama, models, sandbox image, tests, check
start.bat      # starts Ollama if needed, the server, and the browser at http://127.0.0.1:8000
check.bat      # 47 tests + full system check including the models
package.bat    # clean zip of the project in dist\ for another machine
```

Moving to another machine: see `SETUP.md`. Docker Desktop must be running for the isolated sandbox.

## 8. Known limits

- Without Docker running, the sandbox falls back to a local process with no network isolation.
- The network monitor observes and reports; it does not block. The enforcing controls are
  the endpoint guard, the sandbox's disabled network, and (to be added) the firewall.
- Models load with a 4,096-token context on this GPU, so long documents are truncated.
- Task classification is keyword-based.
- Passing tests in the sandbox shows the code runs, not that an engineering formula is right.
