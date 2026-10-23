"""Creates demo input files: a scanned inspection report (image-only PDF) and an SOP for the knowledge base.

Run: python samples/make_samples.py
"""
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent

REPORT = """MANGALORE UNIT - EQUIPMENT INSPECTION REPORT
Report No: INSP/2026/0417            Date: 28 Sep 2026
Equipment: Centrifugal Pump P-101A (Crude Charge Pump)
Location: CDU-1 Pump House            Inspector: R. Nair

OBSERVATIONS
1. Mechanical seal leaking at approx. 40 drops/min (limit 10).
2. Drive-end bearing vibration 7.8 mm/s RMS (alarm 4.5, trip 7.1).
3. Bearing housing temperature 86 deg C (limit 80 deg C).
4. Coupling guard bolts loose; two bolts missing.
5. Casing and nozzles: no visible corrosion or cracks.

CONCLUSION
Pump is not fit for continued service. Standby pump P-101B is
available and tested healthy on 27 Sep 2026.

RECOMMENDED ACTION
Take P-101A out of service, replace mechanical seal and DE bearing,
refit coupling guard. Estimated cost Rs 4.8 lakh, downtime 3 days.
"""

SOP = """SOP-MNT-014: Rotating Equipment Maintenance Approval

1. Purpose
This procedure defines when rotating equipment must be taken out of service and who approves the repair.

2. Vibration limits
A pump with bearing vibration above the trip value of 7.1 mm/s RMS must be stopped within 24 hours.
Operation between alarm (4.5 mm/s) and trip is allowed for at most 7 days with daily monitoring.

3. Seal leakage
Mechanical seal leakage above 10 drops per minute on hydrocarbon service requires changeover to the standby pump.

4. Approval authority
Repairs up to Rs 5 lakh are approved by the Maintenance Manager.
Repairs above Rs 5 lakh and up to Rs 25 lakh are approved by the General Manager (Maintenance).

5. Before work starts
A cold work permit and positive isolation are required. The standby pump must be proven healthy before the changeover.
"""

# Render the report to a picture and wrap it in a PDF with no text layer, like a real scan.
src = pymupdf.open()
src.new_page().insert_text((56, 72), REPORT, fontsize=11, fontname="cour")
png = src[0].get_pixmap(dpi=130).tobytes("png")
scan = pymupdf.open()
page = scan.new_page()
page.insert_image(page.rect, stream=png)
scan.save(HERE / "inspection_report_scan.pdf")
(HERE / "inspection_report_scan.png").write_bytes(png)
(HERE / "SOP-MNT-014_rotating_equipment.txt").write_text(SOP, encoding="utf-8")

# ---- a P&ID-style drawing with known tags, to measure how well drawings are read ----
PID_TAGS = ["T-101", "P-101A", "P-101B", "E-201", "V-301", "FT-101", "PT-102", "LIC-103", "TI-104",
            "FCV-105", "PSV-106", '6"-P-1001-A1', '4"-P-1002-A1']


def make_pid() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=1191, height=842)  # A3 landscape
    s = page.new_shape()

    def label(x, y, text, size=11):
        page.insert_text((x, y), text, fontsize=size, fontname="helv")

    def bubble(x, y, tag):  # instrument
        s.draw_circle((x, y), 22)
        label(x - 19, y + 4, tag, 9)

    def valve(x, y):  # bow-tie
        s.draw_polyline([(x - 12, y - 9), (x + 12, y + 9), (x + 12, y - 9), (x - 12, y + 9), (x - 12, y - 9)])

    s.draw_rect(pymupdf.Rect(90, 220, 230, 560))            # tank
    label(130, 590, "T-101", 14); label(105, 610, "CRUDE FEED TANK", 9)
    for y, tag in ((330, "P-101A"), (500, "P-101B")):        # two pumps
        s.draw_circle((420, y), 30); s.draw_line((390, y + 30), (450, y + 30))
        label(395, y + 55, tag, 13)
        s.draw_line((230, y), (390, y)); s.draw_line((450, y), (560, y))
        valve(310, y)
    s.draw_line((560, 330), (560, 500)); s.draw_line((560, 415), (700, 415))
    label(575, 405, '6"-P-1001-A1', 10)
    valve(640, 415); label(618, 445, "FCV-105", 10)
    s.draw_rect(pymupdf.Rect(700, 380, 860, 450))            # exchanger
    s.draw_line((720, 380), (720, 450)); s.draw_line((840, 380), (840, 450))
    label(755, 475, "E-201", 14); label(725, 492, "FEED PREHEATER", 9)
    s.draw_line((860, 415), (980, 415)); label(875, 405, '4"-P-1002-A1', 10)
    s.draw_oval(pymupdf.Rect(980, 250, 1090, 580))           # vessel
    label(1010, 610, "V-301", 14); label(995, 628, "FLASH DRUM", 9)
    bubble(600, 330, "FT-101"); s.draw_line((600, 352), (600, 415))
    bubble(500, 250, "PT-102"); s.draw_line((500, 272), (500, 330))
    bubble(160, 170, "LIC-103"); s.draw_line((160, 192), (160, 220))
    bubble(920, 330, "TI-104"); s.draw_line((920, 352), (920, 415))
    bubble(1035, 190, "PSV-106"); s.draw_line((1035, 212), (1035, 250))
    s.finish(width=1.6, color=(0, 0, 0))
    s.commit()
    page.draw_rect(pymupdf.Rect(20, 20, 1171, 822), width=1.2)
    label(40, 52, "P&ID - CRUDE CHARGE SECTION (SAMPLE)   DRG NO: PID-CDU-0101   REV 2", 15)
    (HERE / "pid_sample.png").write_bytes(page.get_pixmap(dpi=110).tobytes("png"))
    (HERE / "pid_sample_tags.txt").write_text("\n".join(PID_TAGS), encoding="utf-8")


# ---- a note in a handwriting-style font (a stand-in for real handwriting) ----
NOTE = """Shift log  28/9  night shift

P-101A seal leak getting worse,
approx 40 drops/min now.
Vibration high at DE bearing.
Informed shift in-charge at 01:50.
Changeover to P-101B done 02:30.
P-101A isolated, tag put.
                      - R. Nair"""


def make_note() -> None:
    fonts = [Path(r"C:\Windows\Fonts") / f for f in ("Inkfree.ttf", "segoesc.ttf", "LHANDW.TTF")]
    font = next((f for f in fonts if f.is_file()), None)
    doc = pymupdf.open()
    page = doc.new_page(width=520, height=420)
    kw = {"fontfile": str(font), "fontname": "hand"} if font else {"fontname": "helv"}
    page.insert_text((40, 60), NOTE, fontsize=19, lineheight=1.5, **kw)
    (HERE / "handwritten_note.png").write_bytes(page.get_pixmap(dpi=120).tobytes("png"))


make_pid()
make_note()
print("created:", *sorted(p.name for p in HERE.iterdir() if p.suffix != ".py"))
