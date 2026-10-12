#!/usr/bin/env python3
"""Generate the editable DACH three-lane ingestion figure and a 2x PNG.

Run: python3 generate_flow.py
Requires PyMuPDF only for raster export; SVG generation uses the standard library.
This is a conceptual configuration drawing, not evidence of deployment.
"""

from html import escape
from pathlib import Path
import re

import fitz


OUT = Path(__file__).resolve().parents[2] / "outputs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
WIDTH, HEIGHT = 1600, 990
NAVY = "#183047"
MUTED = "#52677b"
LINE = "#d7e0e7"
BLUE = "#286c9e"
TEAL = "#087f76"
VIOLET = "#6b58a4"
RED = "#b5473c"

parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Three parallel ARES ingestion lanes and Metadata reject notification path">
<defs>
  <marker id="arrow-blue" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M1 1 L9 5 L1 9 Z" fill="{BLUE}"/></marker>
  <marker id="arrow-teal" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M1 1 L9 5 L1 9 Z" fill="{TEAL}"/></marker>
  <marker id="arrow-violet" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M1 1 L9 5 L1 9 Z" fill="{VIOLET}"/></marker>
  <marker id="arrow-red" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M1 1 L9 5 L1 9 Z" fill="{RED}"/></marker>
</defs>
<rect width="1600" height="990" fill="#ffffff"/>
''']


def rect(x, y, w, h, fill, stroke="none", sw=1.5, r=12):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def text(x, y, value, size=22, color=NAVY, weight=400, anchor="start", family="Arial, Helvetica, sans-serif", spacing=None):
    # At 26 cm printed width, 20 SVG units are about 9.2 pt.
    size = max(size, 20)
    extra = f' letter-spacing="{spacing}"' if spacing is not None else ""
    parts.append(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{extra}>{escape(value)}</text>')


def path(d, color, width=2.4, marker=None, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>')
    # Draw arrowheads as native polygons. PyMuPDF omits SVG marker-end during
    # raster export, while explicit geometry survives in both outputs.
    if marker and width >= 2:
        tokens = re.findall(r"[MHV]|-?\d+(?:\.\d+)?", d)
        i = 0
        cur = (0.0, 0.0)
        prev = cur
        while i < len(tokens):
            command = tokens[i]
            if command == "M":
                cur = (float(tokens[i + 1]), float(tokens[i + 2]))
                i += 3
            elif command == "H":
                prev = cur
                cur = (float(tokens[i + 1]), cur[1])
                i += 2
            elif command == "V":
                prev = cur
                cur = (cur[0], float(tokens[i + 1]))
                i += 2
            else:
                raise ValueError(f"Unsupported SVG path: {d}")
        x, y = cur
        px, py = prev
        if x > px:
            points = f"{x},{y} {x-9},{y-5} {x-9},{y+5}"
        elif x < px:
            points = f"{x},{y} {x+9},{y-5} {x+9},{y+5}"
        elif y > py:
            points = f"{x},{y} {x-5},{y-9} {x+5},{y-9}"
        else:
            points = f"{x},{y} {x-5},{y+9} {x+5},{y+9}"
        parts.append(f'<polygon points="{points}" fill="{color}"/>')


def box_label(x, y, w, h, lines, color, fill="#ffffff", border=None, sizes=None):
    rect(x, y, w, h, fill, border or color, 1.8, 10)
    if sizes is None:
        sizes = [22] * len(lines)
    total = sum(sizes) + (len(lines) - 1) * 6
    cursor = y + (h - total) / 2 + sizes[0] * .82
    for i, line in enumerate(lines):
        text(x + w / 2, cursor, line, sizes[i], color, 700 if i == 0 else 400, "middle")
        if i + 1 < len(lines):
            cursor += sizes[i + 1] + 6


def stage(x, y, w, h, lines, color, sizes=None):
    rect(x, y, w, h, "#ffffff", color, 1.3, 8)
    if sizes is None:
        sizes = [20] * len(lines)
    total = sum(sizes) + (len(lines) - 1) * 3
    cursor = y + (h - total) / 2 + sizes[0] * .83
    for i, line in enumerate(lines):
        text(x + w / 2, cursor, line, sizes[i], color, 700 if i == 0 else 400, "middle")
        if i + 1 < len(lines):
            cursor += sizes[i + 1] + 3


# Header and column captions.
text(62, 67, "THREE INGESTION LANES · ONE CONTENT RECORD", 38, NAVY, 700, spacing=.2)
text(62, 108, "Three of N supported lanes shown; writes converge on the same OpenSearch index and content ID.", 22, MUTED)
text(1545, 52, "DACH", 20, BLUE, 700, "end", spacing=2)
text(1545, 83, "JOYN · JOYN_AT · JOYN_CH", 19, MUTED, 600, "end")
path("M62 126 H1545", LINE, 1.8)
text(76, 151, "SOURCE", 18, MUTED, 700, spacing=1.5)
text(293, 151, "INGRESS*", 18, MUTED, 700, spacing=1.5)
text(475, 151, "CONFIGURED LOADER", 18, MUTED, 700, spacing=1.5)
text(1382, 151, "SHARED INDEX", 18, MUTED, 700, spacing=1.5)

# Shared index. Three connectors enter distinct ports without joining each other.
rect(1380, 165, 170, 695, "#f3f6f9", NAVY, 2.1, 14)
text(1465, 212, "OpenSearch", 28, NAVY, 700, "middle")
text(1465, 245, "ONE INDEX", 19, MUTED, 700, "middle", spacing=1)
path("M1405 258 H1525", LINE, 1.5)
text(1465, 357, "same content ID", 21, NAVY, 700, "middle")
text(1465, 388, "field ownership", 20, MUTED, 400, "middle")
text(1465, 418, "by lane", 20, MUTED, 400, "middle")
for cy, color, label in [(275, BLUE, "SUPER"), (480, TEAL, "METADATA"), (775, VIOLET, "COUNTERS")]:
    rect(1400, cy - 18, 130, 37, "#ffffff", color, 1.4, 6)
    text(1465, cy + 7, label, 19, color, 700, "middle")

# Super lane.
box_label(76, 166, 175, 56, ["Kafka"], BLUE, "#eff5f9", sizes=[24])
path("M163.5 222 V241", BLUE, 2.5, "arrow-blue")
box_label(76, 243, 175, 91, ["Kafka", "Consumer", "continuous sink"], BLUE, "#f7fafc", sizes=[22, 22, 18])
box_label(276, 247, 171, 82, ["ares-ingress", "gRPC Streaming"], BLUE, "#ffffff", sizes=[20, 20])
rect(470, 165, 860, 180, "#f2f7fb", BLUE, 2.2, 13)
text(495, 203, "SUPER LOADER", 30, BLUE, 700)
text(1309, 201, "uw · CREATE / UPDATE", 20, BLUE, 700, "end")
for x,w,lines in [(495,140,["Input", "decorators"]),(645,245,["Pipeline", "Include / filter", "fingerprint_super"]),(900,140,["Output", "decorators"]),(1050,130,["Schedules", "on", "visibilities"]),(1190,125,["Flat-v1", "+ Merge"])]:
    stage(x, 232, w, 78, lines, BLUE)
for a,b in [(635,645),(890,900),(1040,1050),(1180,1190)]:
    path(f"M{a+1} 271 H{b-3}", BLUE, 1.8, "arrow-blue")
text(495, 334, "exclude visibilities before flat-v1 · Merge rebuilds fingerprint", 20, BLUE)
path("M251 289 H271", BLUE, 2.5, "arrow-blue")
path("M447 289 H465", BLUE, 2.5, "arrow-blue")
path("M1330 275 H1375", BLUE, 2.5, "arrow-blue")

# Metadata lane.
box_label(76, 428, 175, 100, ["Metadata", "Producer", "Mythematics"], TEAL, "#f2f9f7", sizes=[22, 22, 18])
box_label(276, 439, 171, 82, ["ares-ingress", "gRPC Streaming"], TEAL, "#ffffff", sizes=[20, 20])
rect(470, 390, 860, 180, "#f0f8f6", TEAL, 2.2, 13)
text(495, 428, "METADATA ENRICHER LOADER", 29, TEAL, 700)
text(1309, 426, "u · UPDATE ONLY", 20, TEAL, 700, "end")
for x,w,lines in [(495,140,["Input", "decorators"]),(645,245,["Pipeline", "Metadata selection", "fingerprint_metadata"]),(900,140,["Output", "decorators"]),(1050,130,["Flat if", "configured"]),(1190,125,["Merge", "fingerprint"])]:
    stage(x, 457, w, 78, lines, TEAL)
for a,b in [(635,645),(890,900),(1040,1050),(1180,1190)]:
    path(f"M{a+1} 496 H{b-3}", TEAL, 1.8, "arrow-teal")
text(495, 559, "Parallel Mythematics provider · detailed integration outside UMAS scope", 20, TEAL)
path("M251 480 H271", TEAL, 2.5, "arrow-teal")
path("M447 480 H465", TEAL, 2.5, "arrow-teal")
path("M1330 480 H1375", TEAL, 2.5, "arrow-teal")

# The compact reject strip sits between the second and third lanes. Its red return
# uses the empty left margin; it never crosses a lane's ingress/index arrow.
rect(292, 585, 1038, 73, "#fffafa", "#e8c6c2", 1.5, 10)
text(315, 608, "REJECT NOTIFICATION", 18, RED, 700, spacing=1.2)
text(315, 633, "Producer decides · no automatic resubmission", 20, RED)
box_label(1135, 595, 175, 53, ["S3 rejects"], RED, "#ffffff", sizes=[20])
box_label(845, 595, 253, 53, ["AWS notification / SQS"], RED, "#ffffff", sizes=[20])
path("M1240 570 V590", RED, 2.2, "arrow-red")
path("M1135 621 H1103", RED, 2.2, "arrow-red")
path("M845 623 H815 V660 H52 V518 H71", RED, 2.2, "arrow-red")

# Counters lane.
box_label(76, 727, 175, 97, ["Analytics", "Producer"], VIOLET, "#f7f5fb", sizes=[22, 22])
box_label(276, 737, 171, 82, ["ares-ingress", "gRPC Streaming"], VIOLET, "#ffffff", sizes=[20, 20])
rect(470, 690, 860, 170, "#f7f5fb", VIOLET, 2.2, 13)
text(495, 729, "COUNTERS LOADER", 29, VIOLET, 700)
text(1309, 727, "u · UPDATE ONLY", 20, VIOLET, 700, "end")
for x,w,lines in [(495,245,["ID + numeric schema"]),(754,245,["Counter snapshot", "absolute values"]),(1013,302,["Existing content only", "views + unique viewers"])]:
    stage(x, 751, w, 70, lines, VIOLET)
for a,b in [(740,754),(999,1013)]:
    path(f"M{a+1} 786 H{b-4}", VIOLET, 1.8, "arrow-violet")
text(495, 849, "No fingerprint · no Merge · no schedules", 20, VIOLET)
path("M251 775 H271", VIOLET, 2.5, "arrow-violet")
path("M447 775 H465", VIOLET, 2.5, "arrow-violet")
path("M1330 775 H1375", VIOLET, 2.5, "arrow-violet")

# Footer defines the asterisk. Distinct acceptance and indexing stages matter.
path("M62 888 H1545", LINE, 1.8)
text(62, 925, "* gRPC Streaming via ares-ingress: ACK validates and queues; indexing is asynchronous.", 21, NAVY, 600)
text(62, 958, "Conceptual DACH configuration · three lanes shown of N possible · no deployed state implied", 19, MUTED)
parts.append("</svg>")

svg = "\n".join(parts)
svg_path = OUT / "ingestion-three-lanes.svg"
png_path = OUT / "ingestion-three-lanes.png"
svg_path.write_text(svg, encoding="utf-8")
doc = fitz.open(stream=svg.encode("utf-8"), filetype="svg")
pixmap = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
pixmap.save(png_path)
print(f"{svg_path} ({WIDTH}x{HEIGHT} SVG)")
print(f"{png_path} ({pixmap.width}x{pixmap.height} PNG)")
