# Sovereign Workbench

A self-hosted, air-gapped AI workbench for confidential industrial work, built for SIH problem
statement 26117 (MRPL). It runs open-weight models on the organisation's own machine, plans
multi-step tasks, reads scans and drawings, produces Word, Excel and PowerPoint files, runs code
in a sandbox, searches the organisation's own documents, and shows that nothing leaves the machine.

## Quick start

| Step | Action |
|---|---|
| 1 | Install Python 3.10+ and Docker Desktop; start Docker Desktop |
| 2 | Double-click `setup.bat` (once per machine; needs internet once, or an `offline\` folder) |
| 3 | Double-click `start.bat`; the browser opens at `http://127.0.0.1:8000` |
| 4 | Double-click `check.bat` to verify every function, including the models |

Moving to another machine: `SETUP.md`. Demo walk-through: `DEMO.md`.

## What it does

| Capability | How |
|---|---|
| Several models, chosen automatically | A registry (`config/models.yaml`) and a router pick the model by task type, complexity and the machine's memory. Adding a model is one line. |
| Runs on small and large hardware | Measures the GPU and uses what fits, from 4B laptop models to a 120B-class server model, with the same code. |
| Agent team | Planner, Reader, Researcher, Analyst, Coder, Writer, Responder and Reviewer. Each has its own tools and model, and its result must pass a check. |
| Reads many inputs | Text, PDF, scanned PDF, images, drawings, Word, Excel, PowerPoint. Scans and images are read by a local vision model; large drawings in detail views; long documents in parts. |
| Real deliverables | Approval notes, Word documents, Excel sheets with formulas, PowerPoint decks, tested code, calculations with steps. |
| Knowledge base | Upload manuals and SOPs; answers cite document and page. |
| Conversation memory | Follow-up messages see the earlier turns, facts and files. |
| Sovereignty proof | Live network monitor, egress test, printable evidence report, audit log, optional firewall lockdown. The model server is run with its cloud features switched off. |

## Files

| Path | Purpose |
|---|---|
| `setup.bat`, `start.bat`, `check.bat` | Install, run, verify |
| `pack_offline.bat` | Bundle everything for a machine with no internet |
| `package.bat` | Make a clean zip of the project for moving |
| `lockdown.bat`, `unlock.bat` | Block or restore outbound network access with Windows Firewall |
| `config/` | `models.yaml` (models, hardware profiles), `agents.yaml` (agent team) |
| `workbench/` | The application |
| `samples/` | Demo inputs: scanned report, P&ID drawing, handwriting-style note, SOP |
| `tests/` | `test_core.py` and `test_api.py`; no model needed |

## Documents

| File | Contents |
|---|---|
| `SETUP.md` | Moving to another machine, online and offline |
| `DEMO.md` | Step-by-step demonstration for judges |
| `EVALUATION.md` | Judge-style assessment against the problem statement |
| `WEAKNESSES.md` | Known weak points, evidence and status |
| `CHANGELOG.md` | Every change, with what was and was not verified |
| `build.md` | Design, architecture and requirement coverage |
# AURA_SYSTEM
