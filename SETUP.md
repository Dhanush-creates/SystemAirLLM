# Setup on another PC or laptop

The workbench is a self-contained folder. Copy it, run `setup.bat` once, then use `start.bat`.

## Checklist for the move

| Step | What to do |
|---|---|
| 1. Take with you | `dist\sovereign-workbench.zip` (5 MB). If the other PC has no internet, also the `offline\` folder (1.6 GB) and the models (see Route B). |
| 2. On the other PC | Install Python 3.11 or 3.12 (tick "Add python.exe to PATH") and Docker Desktop. Start Docker Desktop. |
| 3. Unzip | Into a short path such as `C:\workbench`. |
| 4. `setup.bat` | Installs everything and downloads the models that fit that PC (about 45 GB for a 12 GB GPU; needs internet once). |
| 5. `check.bat` | Every line should say PASS. A WARN or FAIL comes with the fix. |
| 6. `start.bat` | Opens the workbench in the browser. |
| 7. Optional | `lockdown.bat -SelfTest` to prove the firewall lockdown; approve the administrator prompt. |

Tested with Python 3.11 and 3.12. Package versions are pinned in `requirements.txt`.

## What the other machine needs

| Item | Needed? | Notes |
|---|---|---|
| Windows 10 or 11, 64-bit | Yes | The scripts are for Windows. |
| Python 3.11 or 3.12 | Yes | From python.org; tick "Add python.exe to PATH". 3.10 and 3.13 should work but were not tested. |
| Ollama | Yes | `setup.bat` installs it (winget, or `offline\OllamaSetup.exe`). |
| Docker Desktop | Recommended | Gives the no-network code sandbox. Without it code still runs, but with no isolation. |
| NVIDIA GPU | Optional | Without one the models run on the CPU, slowly. |
| Free disk | 10–45 GB | Depends on which models fit the machine. |

## What to copy

The quickest way: double-click `package.bat`. It writes `dist\sovereign-workbench.zip` (under 1 MB)
with everything needed and nothing that is rebuilt. Unzip it on the other machine into a short
path such as `C:\workbench`.

To copy by hand instead, take the whole folder **except** these, which are rebuilt or are local data:

| Folder | Why it is skipped |
|---|---|
| `.venv\` | Python environment; tied to the machine it was made on. `setup.bat` rebuilds it. |
| `workspace\`, `logs\`, `data\` | Task files, audit log and knowledge base of the old machine. Copy `data\` only if you want to keep the knowledge base. |
| `__pycache__\` | Temporary files. |

Without those the folder is about 5 MB. The models are not inside the folder; see below.

## Route A: the new machine has internet (simplest)

1. Copy the folder.
2. Install Python and Docker Desktop if they are missing. Start Docker Desktop.
3. Double-click `setup.bat`. It will:
   - build the Python environment and install the packages,
   - install and start Ollama,
   - measure the machine and download the models that fit it,
   - get the sandbox image,
   - create the demo sample files,
   - run the automated tests and the system check.
4. Double-click `start.bat`. The browser opens at `http://127.0.0.1:8000`.

After setup, the internet is no longer needed.

## Route B: the new machine has no internet (air-gapped)

On a machine that has internet and the same Python version as the target:

1. Double-click `pack_offline.bat`. It fills `offline\` with the Python packages, the sandbox
   image and the Ollama installer.
2. To include the models too, run `pack_offline.bat -Models` from a terminal. This copies
   every installed Ollama model and can be 50 GB or more.
3. Copy the whole folder, including `offline\`, to the target on a USB drive.
4. On the target: install Python and Docker Desktop from their installers, then run `setup.bat`.
   It uses `offline\` and does not touch the network.

What has been checked: the bundle was built here (1.6 GB without models: packages 35 MB, sandbox
image 107 MB, Ollama installer 1.5 GB), and a fresh copy of the project installed its packages
from it with the network option disabled and passed every test. Not checked: running the
installer from the bundle, the 50 GB model copy, and a machine that really has no internet.

## Without an NVIDIA GPU

The workbench runs on the CPU with the small models (the budget is capped at 6 GB so that large
models are not chosen). Measured on a CPU-only model server on this machine (Core Ultra 7 265K):
a simple question took 17 s, and the scanned-report approval note took 465 s. Usable for a
check, too slow for a live demonstration.

## Enforcing the air gap

`lockdown.bat` blocks outbound traffic from the model server and the workbench with Windows
Firewall; `unlock.bat` removes the rules. `lockdown.bat -SelfTest` applies the rules, checks that
the internet is blocked and `127.0.0.1` still works, removes them, and writes
`logs\lockdown_selftest.txt`. It asks for administrator approval. It has not been run successfully yet.

## How the system adapts to the hardware

`config/models.yaml` has `profile: auto`. At start the workbench measures the NVIDIA GPU
memory (or, with no NVIDIA GPU, half the system RAM) and uses only models that fit.
`setup.bat` downloads the two largest models that fit for each job.

| Memory budget | General | Coding | Vision |
|---|---|---|---|
| 12 GB or more | `qwen3:14b`, `qwen3:8b` | `qwen2.5-coder:14b`, `:7b` | `gemma3:12b`, `qwen2.5vl:7b` |
| 8 GB | `qwen3:8b`, `qwen3:4b` | `qwen2.5-coder:7b`, `:3b` | `qwen2.5vl:7b`, `gemma3:4b` |
| 6 GB | `qwen3:4b` | `qwen2.5-coder:7b`, `:3b` | `gemma3:4b` |
| 4 GB | `qwen3:4b` | `qwen2.5-coder:3b` | none fits |

Smaller models are less reliable. On the 6 GB setting the 4B general model first claimed
to have written a file it had not; the workbench caught that and made it do the work. Expect
slower and rougher results below 8 GB.

To force a budget: set the environment variable `WORKBENCH_VRAM` to a number of GB.

## Checking that everything works

| Command | What it checks | Time |
|---|---|---|
| `setup.bat` | Installs, then runs the tests and the quick check | minutes |
| `check.bat` | 47 automated tests, then the full check: every function plus a call to each model, one agent task and one agent-team task | 2–4 min |
| UI → System check | The same checks, in the browser | seconds, or minutes for the full check |
| `.venv\Scripts\python -m workbench.doctor --pull` | Downloads the models recommended for this machine | depends |

Each check prints PASS, WARN or FAIL with a suggested fix.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `setup.bat`: "this folder's path is too long" | Windows limits paths to 260 characters. Move the folder somewhere short, such as `C:\workbench`. |
| `setup.bat`: Python not found | Install Python and tick "Add python.exe to PATH", then reopen the window. |
| System check: Model server FAIL | Ollama is not running. `start.bat` starts it; otherwise open Ollama. |
| System check: Models installed WARN or FAIL | Run `.venv\Scripts\python -m workbench.doctor --pull` (needs internet), or copy models with Route B. |
| System check: Sandbox isolation WARN | Start Docker Desktop, then run `setup.bat` again. |
| Network monitor shows an external connection from `ollama.exe` | A model download is in progress, or the Ollama desktop app was started after the workbench. Close the workbench and run `start.bat` again: it stops the desktop app and runs the server with cloud features off. |
| System check: "Model server stays local" WARN | Same cause and fix as above. |
| Tasks are very slow | The first call loads the model into memory. With no GPU every call is slow; use a machine with an NVIDIA GPU for the demo. |
| Port 8000 is used by another program | `start.bat` moves to the next free port (8001, 8002, …) and opens the browser there. |
| `start.bat`: "not set up on this machine yet" | Run `setup.bat` first. |
| `setup.bat`: package install failed with the offline bundle | The bundle's packages are for Python 3.12. Install Python 3.12, or run setup with internet. |
