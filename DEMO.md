# Demonstration script

About 12 minutes. Sample files are in `samples\` (run `setup.bat` once to create them).
Times are from an RTX 5070 (12 GB); the first task is slower while a model loads.

## Before the judges arrive

1. Start Docker Desktop.
2. Double-click `start.bat`. It stops the Ollama desktop app if it is running and starts the model
   server with its cloud features off, so the server makes no external connection.
3. Open **System check** → **Full check**. All 18 lines should pass.
4. Open **Knowledge base** → add `samples\SOP-MNT-014_rotating_equipment.txt`.
5. Optional, strongest proof: disconnect the network cable and Wi-Fi, or run `lockdown.bat`.

## 1. Sovereignty first (1 minute)

- Point at the indicator at the top right: **No external connections**.
- Open **Network monitor**: every live connection is to `127.0.0.1`.
- Click **Run egress test**: both deliberate attempts to reach the internet are blocked.

## 2. Agentic task: scanned report to approval note (about 40 s)

- **Workbench** → Attach `samples\inspection_report_scan.pdf` (a scan with no text layer).
- Type: *Read the attached scanned inspection report, check the maintenance SOP in the knowledge base for the approval authority, and draft an approval note as a Word file.*
- Show: the plan strip (Reader → Researcher → Writer), the vision model reading the scan,
  the SOP citation, the review, and the downloadable `approval_note.docx`.
- Open the Word file: findings, recommendation, approver from the SOP, signature block.

## 3. Conversation memory (about 10 s)

- In the same chat type: *Who has to approve this repair, and why?*
- It answers from the earlier turn, citing the SOP.

## 4. Model auto-selection and coding in a sandbox (about 30 s)

- Click **New chat**. Type: *Write a python function that computes pipe pressure drop using the Darcy-Weisbach equation, with unit tests, and run the tests.*
- Show: the model badge changes to the coding model; the tests run in a Docker container with
  no network; if a test fails the Coder is sent back until they pass.

## 5. Multimodal: engineering drawing to Excel (about 40 s)

- **New chat** → Attach `samples\pid_sample.png`.
- Type: *List every equipment and instrument tag in the attached drawing in an Excel sheet with the columns Tag and Type.*
- Open the Excel file. Also available: `samples\handwritten_note.png` with *What happened during this shift?*

## 6. Calculation with steps (about 15 s)

- **New chat**. Type: *Calculate the pressure drop in a 200 m long pipe of 0.15 m diameter carrying water at 2 m/s. Friction factor 0.02, density 1000 kg/m3. Show the steps.*
- The answer lists each step; every number comes from code run in the sandbox (53,333.33 Pa).

## 7. Close on the proof (1 minute)

- **Network monitor** → **Open evidence report**: one printable page with the endpoints,
  the monitoring period, every connection seen, and the egress test results.
- **Audit log**: every routing decision, tool call and answer of the session.
- **Models** and **Agents** screens: adding a model or an agent is one entry in a YAML file.

## Questions a judge may ask

| Question | Answer |
|---|---|
| Did the monitor ever catch anything? | Yes. It caught the model server (Ollama) holding a connection to an external address on its own. That led to running the server with its cloud features off; afterwards the monitor recorded none. |
| How do I know it is not calling a cloud API? | The model endpoint is refused unless it is on this machine; the monitor reads the OS connection table; the egress test tries and fails; run it with the cable unplugged. |
| What if the venue machine is weaker? | The system measures the GPU and picks smaller models. A simulated 6 GB machine completed the approval-note task with 4B models in 48 s, less polished. |
| Can you add a new model? | One line in `config/models.yaml`, then `ollama pull`. Any OpenAI-compatible server works. |
| What about a 120B model? | Set the server profile; the same code routes to it, and it is then trusted to plan and to send work back for correction. |
| Does it make things up? | Numbers in results are checked against the documents, the knowledge base and tool output; unverified work is flagged. Text can still be wrong, so drafts say "review before signing". |
| What are the limits? | See `WEAKNESSES.md`: short context on a 12 GB GPU, one task at a time, keyword search, small models are rougher. |
