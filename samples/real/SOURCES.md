# Real-world test images

Public-domain files from Wikimedia Commons, used to measure how well the local vision model reads
real material. Downloaded 4 October 2026.

| File | What it is | Source page on commons.wikimedia.org | Licence |
|---|---|---|---|
| `real_pid_omre.jpg` | Piping and instrumentation diagram, 4000 × 3266 px | File:Organic Moderated Reactor Experiment Piping and Instrumentation Diagram.jpg | Public domain |
| `real_handwritten_letter.jpg` | Cursive handwritten letter, early 1900s | File:9009-letter from James Hopper to Judge Ben B Lindsey.jpg | Public domain |
| `real_photo_motor_nameplate.jpg` | Photograph of two motor nameplates | File:POWERHOUSE INTERIOR, DETAIL OF EXCITER No. 2 GENERAL ELECTRIC INDUCTION MOTOR NAMEPLATE ... HAER CAL,26-JULA.V,1A-13.tif | Public domain |

## Measured results (`qwen2.5vl:7b`, compared by eye against the images)

| File | Result | Time |
|---|---|---|
| P&ID | All 24 text labels checked in the top-left corner were read (equipment names, numbers, pressures, notes). 5 of 9 instrument circles checked were read. 18 equipment numbers found on the whole sheet. | 315 s, 33 detail views |
| Handwritten letter | About 41 of 48 words correct. The sense is kept; small words ("you", "your", "For") and word endings ("jails", "prisoners") were misread. | 3 s |
| Nameplate photograph | Most fields correct: 215 HP, 2400 V, 51.5 A, 3 phase, 6/14/46, frame 568, 2200 V, 62.5 A, 50 cycles, serial 5287226, service factor 1.15. Errors: motor type read as "PT" (plate says "FT"), and the two RPM rows were mixed up. | 5 s |
