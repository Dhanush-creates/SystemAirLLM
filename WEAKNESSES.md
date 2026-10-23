# Known weaknesses

An honest list of where the workbench is weak today, what was seen, and what would fix it.
Updated with every change, alongside `CHANGELOG.md`.

Status: **Open** = not addressed. **Reduced** = a guard exists but the cause remains.
**Fixed** = no longer seen in testing.

## 1. Model behaviour

| Weakness | Evidence seen | Impact | Fix | Status |
|---|---|---|---|---|
| Models invent numbers in documents | PowerPoint task contained "up to 30%" and "20–40%" with no source | A reader may trust a made-up figure | Number-grounding check: every number in a deliverable must appear in the request, the documents, the knowledge base or tool output | Reduced (agents, entry 8) |
| Final answer loses the calculation steps | After one malformed reply, the pressure-drop answer gave only the result | "Steps shown" requirement not met in the answer text | Analyst agent returns each step as a fact; the final answer is assembled from those facts | Fixed (agents, entry 8) |
| Model claims a file it never created | `qwen3:4b` answered with a file path after zero tool calls | False report of completed work | Answer is rejected unless the named file exists | Reduced |
| Model uses the wrong tool | `qwen2.5-coder:7b` wrote code into a Word file | Task fails or loops | Each agent sees only the tools for its job | Fixed (agents, entry 8) |
| Model repeats the same failing step | 7B coder repeated one edit until the step limit | Wasted time, no result | Stuck detection: escalate to a bigger model, or stop after 3 repeats | Reduced |
| Small models are unreliable | 4B and 7B models needed pushing back in most multi-step tasks | Below 8 GB of GPU memory, expect slow and rough results | Use 8 GB or more for the demo; AirLLM as a slow last resort | Open |
| Passing tests is not proof of correctness | A model fixed a failing test by copying the code's output into the test | Wrong engineering formula could pass | Human review; reference cases in the knowledge base | Open |
| Small Planner over-plans | A 14B Planner added the Researcher and Analyst to a presentation task; unrelated SOP figures ended up in the slides | Irrelevant content | Below tier 3 the rules choose the agents; the Planner only writes goals | Reduced |
| Small Reviewer gives wrong corrections | A 14B Reviewer counted the title slide as an extra slide and sent good work back; the redo failed | Good work damaged | Below tier 3 the Reviewer's remark is shown, not enforced | Reduced |
| Number check not yet seen working on a real model | In the final runs no model invented a figure | The check is proven only by the automated test | Keep testing with tasks that tempt invention | Open |
| A model call can run without end in JSON mode | One call ran over ten minutes | Task appears frozen | Replies capped at 3,000 tokens; 300 s timeout | Fixed |
| Small models copy examples from the prompt | A 4B model cited "SOP-014.pdf", the example in its instructions | False citation (caught by the file check) | Examples in prompts are now generic | Reduced |
| Approval note could omit the approver or carry the wrong reference | 6 GB run: no approver named; a 12 GB run: the SOP citation in the reference field | Incomplete note | `note_complete` check sends the note back until the report number and the approver are present | Fixed |
| Vision model loops on dense drawings | On a real P&ID one tag was repeated hundreds of times and reading stopped | Most of the drawing unread | Repeats removed; finer detail views; a looping view is split and re-read | Fixed (slow: about 5 minutes for a dense sheet) |
| Small instrument circles on drawings are missed | Real P&ID: 5 of 9 circles checked were read | Instrument lists from dense drawings will be incomplete | A larger vision model; a dedicated symbol detector | Open |
| A misread in the scan passes every check | CPU run: report number read as "INSF/2026/0417" | The note repeats the misreading | Checks compare against what was read, not against the paper; human review | Open |
| Wrong words pass the checks | A note gave the inspection date as 27 Sep when the report said 28 Sep | The checks verify numbers, files, tests and citations, not meaning | Human review; every draft says "review before signing" | Open |
| Reasoning is off by default | Hidden reasoning is switched off for speed (3–7× faster, same results on three test tasks) | A hard task may be answered less carefully on the first try | Reasoning is switched on for the retry when a result is sent back; set `think: true` per model in `config/models.yaml` | Reduced |
| A model can return nothing | `qwen3:4b` spent its whole reply on hidden reasoning | Wasted steps; a 6 GB run took 336 s | Empty replies are retried without reasoning; the same run now takes 48 s | Fixed |
| Number check flagged tag fragments | "P-101" was read as an invented number 101 and a correct note was sent back twice | Slow task, false "not verified" | Digits inside tags and dates are no longer checked | Fixed |
| Task classification is keyword-based | Routing depends on words such as "code", "draft", "calculate" | An unusual phrasing can pick the wrong model or plan | Small-model classifier | Open |

## 2. Capacity

| Weakness | Evidence seen | Impact | Fix | Status |
|---|---|---|---|---|
| 4,096-token context on a 12 GB GPU | Ollama loads the models at this size | A long document does not fit in one call | Agents pass a compact fact sheet; a long attachment is read in up to 8 parts (an 8-page manual was answered correctly); raise `OLLAMA_CONTEXT_LENGTH` on bigger hardware | Reduced |
| Long attachments beyond 8 parts are cut off | Limit in `orchestrator.py` | Very long manuals are read only in part | Put long manuals in the knowledge base instead of attaching them | Open |
| One task at a time | One GPU, one loaded model | A second request waits in a queue and is told so | More GPUs on the server | Reduced |
| Model swap delay | 10–30 s each time the general, coding or vision model changes | Slower multi-agent tasks | Order steps to minimise swaps; more GPU memory | Open |
| At most 10 vision-read pages per document | Limit in `ingest.py` | Long scanned documents are read only in part | Background indexing of long scans | Open |
| Team mode makes several model calls | A three-agent task is 5–8 calls | 40 s for the approval note on 12 GB | Simple questions take the single-agent fast path; reasoning off by default | Reduced |

## 3. Sovereignty

| Weakness | Evidence seen | Impact | Fix | Status |
|---|---|---|---|---|
| The network monitor observes; it does not block | By design | It proves, it does not enforce | `lockdown.bat` adds outbound firewall blocks, with a test button in the UI; or unplug the network | Reduced: the lockdown script has not been run (needs administrator rights) |
| The monitor samples every 2 seconds | By design | A connection shorter than that could be missed | Firewall lockdown for enforcement | Open |
| Ollama contacted an external address by itself | Measured: the server alone, with no download running, held a connection to `34.36.133.15:443` (its cloud features). The desktop app also starts its own server | Real outbound traffic from the model server; the indicator would turn red in a demo | `start.bat`, `setup.bat` and `check.bat` now stop the desktop app and run the server with `OLLAMA_NO_CLOUD=1`. Measured after the fix: no external connection in 60 s, including a model call. The system check has a "Model server stays local" line | Fixed |
| Model downloads are external traffic | `ollama pull` connects to the model registry | Expected during setup only | Do setup before going offline; then run `lockdown.bat` | By design |
| Docker containers are not visible to the monitor | They run inside Docker's virtual machine | Sandbox traffic cannot be observed from the host | Sandbox runs with `--network none`; the egress test proves it | Reduced |
| DNS lookup for a hostname endpoint | `netguard` resolves the configured host | One DNS query if an endpoint is set by name | Use IP addresses in `config/models.yaml` | Open |

## 4. Product gaps

| Weakness | Impact | Fix | Status |
|---|---|---|---|
| Conversation memory is kept in RAM | Follow-ups work within a conversation, but restarting the server forgets all conversations (files remain on disk) | Store sessions on disk | Reduced |
| No login, roles or per-department knowledge bases | Anyone on the machine sees everything | Authentication and access control | Open |
| Knowledge search is keyword-only | A question worded differently from the document may miss. Word variants now match ("approval" finds "approved"), synonyms do not | Add local embedding search | Reduced |
| Sandbox libraries are fixed | The sandbox has numpy, pandas, sympy and openpyxl; anything else is unavailable because it has no network | Add packages to `scripts/sandbox.Dockerfile` and rebuild | Fixed for the common cases |
| Folder path length on Windows | Setup failed in a folder whose path was 153 characters long | Setup cannot build the Python environment | Setup now stops with a clear message; use a short path such as `C:\workbench` | Fixed |
| Plain layout in generated documents | No organisation letterhead or template | Word and PowerPoint templates | Open |

## 5. Not yet verified

| Item | Why it matters |
|---|---|
| Setup on a second physical machine | Only run here and on fresh copies of the folder, including one set up from the offline bundle |
| `lockdown.bat` firewall rules | The administrator prompt was declined when the self-test ran. Run `lockdown.bat -SelfTest` and read `logs\lockdown_selftest.txt` |
| Models inside the offline bundle | `pack_offline.bat -Models` (a 50 GB folder copy) was not run; the Ollama installer in the bundle was downloaded but not run |
| A machine that truly has no GPU | Tested with the GPU hidden from a second model server, not on GPU-less hardware |

## 6. Measured on real material (4 October 2026)

Public-domain files in `samples/real/`, compared by eye. See `samples/real/SOURCES.md`.

| Input | Result | Limit to keep in mind |
|---|---|---|
| Real P&ID, 4000 × 3266 px | 24 of 24 text labels checked; 5 of 9 instrument circles | Small instrument circles are often missed. Reading takes about 5 minutes |
| Real cursive handwriting | About 85% of words correct | Short words and word endings are misread; treat as a draft transcription |
| Nameplate photograph | 11 fields right, 2 wrong | A wrong letter or a swapped row is possible; check values that matter |
| CPU only, no GPU | Works; approval note in 465 s | The small vision model misread one letter of the report number |
| Large-model behaviour | Planner adding agents and Reviewer sending work back are tested only with a mock model |
| AirLLM with real weights | Package and model not installed |
