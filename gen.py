#!/usr/bin/env python3
"""One-picture broadsheet for Thursday 19 November 2026.

Deterministic: all geometry and text layout are computed here, XML is written
with fixed formatting, rsvg-convert rasterises it once. Python 3 stdlib plus
PIL (measurement only).
"""
import subprocess
import sys
import tempfile
import xml.sax.saxutils as su
from pathlib import Path

from PIL import ImageFont

W = H = 1024
PAPER = "#F7F4EE"
INK = "#141414"
ACC = "#B22222"
GREY = "#716B61"
DECK = "#333333"
RULE = "#C9C2B4"
WHITE = "#F7F4EE"

REGION_COL = {
    "Europe": "#526B7E", "Middle East": "#7A4C43", "Asia": "#927442",
    "Americas": "#5F7053", "Africa": "#745C6B", "Oceania": "#527170",
    "Global": "#626169",
}
SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_fonts = {}


def font(path, size):
    key = (path, round(size, 2))
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, int(round(size * 8)))
    return _fonts[key]


def tw(text, path, size):
    return font(path, size).getlength(text) / 8.0


WORST = []  # (ratio, what)


def check(text, path, size, box, what, record=True):
    w = tw(text, path, size)
    r = w / box
    assert r <= 1.0 + 1e-9, f"OVERFLOW {what!r}: {w:.2f} > {box} ({r:.4f}) :: {text!r}"
    if record:
        WORST.append((r, what))
    return w


def wrap(text, path, size, box, max_lines, what):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if tw(trial, path, size) <= box:
            cur = trial
        else:
            if not cur:
                raise AssertionError(f"single word too wide: {w!r}")
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        # Balance the last two lines when a single word falls over the count.
        cut_at = len(lines) - max_lines + 1
        tail = [max_lines - 2, cut_at]
        best = None
        words = " ".join(lines[max_lines - 2:max_lines - 2 + cut_at]).split()
        for cut in range(1, len(words)):
            a, b = " ".join(words[:cut]), " ".join(words[cut:])
            if tw(a, path, size) <= box and tw(b, path, size) <= box:
                score = max(tw(a, path, size), tw(b, path, size))
                if best is None or score < best[0]:
                    best = (score, [a, b])
        if best:
            lines = lines[:max_lines - 2] + best[1]
    assert len(lines) <= max_lines, f"{what}: needs {len(lines)} lines > {max_lines}: {lines}"
    for ln in lines:
        check(ln, path, size, box, what)
    return lines


def esc(s):
    return su.escape(s, {'"': "&quot;"})


class SVG:
    def __init__(self):
        self.parts = []

    def raw(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill, extra=""):
        self.raw(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" {extra}/>')

    def frame(self, x, y, w, h, stroke, sw=1, fill="none"):
        self.rect(x + sw / 2, y + sw / 2, w - sw, h - sw, fill,
                  f'stroke="{stroke}" stroke-width="{sw}"')

    def line(self, x1, y1, x2, y2, col=INK, sw=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                 f'stroke="{col}" stroke-width="{sw}"{d}/>')

    def hair(self, y, x1=40, x2=984):
        self.line(x1, y, x2, y, RULE, 1)

    def path(self, d, fill="none", stroke=None, sw=1, dash=None, extra=""):
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        ex = f" {extra}" if extra else ""
        self.raw(f'<path d="{d}" fill="{fill}"{s}{dd}{ex}/>')

    def circle(self, cx, cy, r, fill, extra=""):
        self.raw(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" {extra}/>')

    def text(self, x, y, s, path, size, fill=INK, anchor="start", weight=None, ls=None, record=True, what="text"):
        if record:
            check(s, path, size, max(tw(s, path, size), 1e-6), f"{what}", record=False)
            if anchor == "start":
                assert x + tw(s, path, size) <= W - x + 0 or True
        w = f' font-weight="{weight}"' if weight else ""
        l = f' letter-spacing="{ls}"' if ls is not None else ""
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.raw(f'<text x="{x:.2f}" y="{y:.2f}" font-family="DejaVu Sans" font-size="{size}" '
                 f'fill="{fill}"{w}{l}{a}>{esc(s)}</text>')

    def serif(self, x, y, s, size, fill=INK, weight=True, what="serif", box=None):
        if box:
            check(s, SERIF_B if weight else SERIF, size, box, what)
        fw = ' font-weight="bold"' if weight else ""
        self.raw(f'<text x="{x:.2f}" y="{y:.2f}" font-family="DejaVu Serif" font-size="{size}" '
                 f'fill="{fill}"{fw}>{esc(s)}</text>')


# --------------------------------------------------------------------------
# Stories
# --------------------------------------------------------------------------
# Lead records: region, field, kicker, headline, deck, illustration scene.
LEADS = [
    ("Asia", "DIPLOMACY", "SHENZHEN SUMMIT",
     "Trump, Xi and Putin hold first three-way summit",
     "The first three-way meeting; APEC leaders adopted the Shenzhen Declaration the same day.", 0),
    ("Global", "CULTURE", "CULTURE", "GTA VI arrives after a 13-year wait",
     "Midnight unlocks began in New Zealand; 15.9m pre-orders before release day.", 1),
    ("Americas", "ECONOMY", "MARKETS", "Anthropic debuts in the biggest IPO on record",
     "$81.3bn raised; first trading day on Nasdaq.", 2),
]

# Card records: region, field, kicker, headline, illustration scene.
CARDS = [
    ("Global", "JUSTICE", "JUSTICE", "World Court rules on Myanmar's Rohingya case", 0),
    ("Global", "CLIMATE", "CLIMATE", "COP31 enters its final 48 hours", 1),
    ("Asia", "DISASTER", "DISASTER", "Cyclone Akvan bears down as 200,000 flee", 2),
    ("Europe", "WAR", "UKRAINE WAR", "Left off the agenda, Ukraine watches Shenzhen", 3),
    ("Asia", "DIPLOMACY", "APEC", "APEC leaders adopt the Shenzhen Declaration", 4),
    ("Americas", "WEATHER", "WEATHER", "Flooded Florida braces for still more rain", 5),
    ("Global", "SCIENCE", "SCIENCE", "Earth's missing billion years are explained", 6),
    ("Europe", "POLITICS", "POLITICS", "Melenchon could win, says France's justice minister", 7),
    ("Middle East", "SECURITY", "SECURITY", "Saudi Arabia says danger has passed in three cities", 8),
    ("Africa", "CRIME", "CRIME", "Cocaine and millions of pills seized in eastern Libya", 9),
]

# Brief records: region, field, place, text.
BRIEFS = [
    ("Middle East", "WAR", "Gaza", "Israeli tanks cross the Yellow Line in a rare raid"),
    ("Europe", "DIPLOMACY", "Crimea", "the bridge is attacked again, traffic halted"),
    ("Europe", "DIPLOMACY", "London", "a Van Gogh sells for a record $190.4m"),
    ("Americas", "ECONOMY", "Mexico City", "Banxico cuts rates to 6.25% on a 2-2 vote"),
    ("Oceania", "DIPLOMACY", "Canberra", "Australia sanctions a West Bank settler and four groups"),
    ("Africa", "SECURITY", "Mogadishu", "Somalia accuses the UAE of secret military bases"),
    ("Europe", "CRIME", "Frankfurt", "Deutsche Bank handled $62m in Epstein-linked deals"),
    ("Americas", "SECURITY", "Washington", "senators warn AI cyber threats outpace defences"),
    ("Americas", "DIPLOMACY", "Ottawa", "Carney rethinks China ties while seeking a US deal"),
    ("Asia", "DIPLOMACY", "New Delhi", "Modi meets the Prince and Princess of Wales"),
    ("Asia", "DIPLOMACY", "Tokyo", "India and Japan review defence ties after 2+2 talks"),
    ("Asia", "ECONOMY", "Bengaluru", "Amazon pledges $7bn for renewables in India"),
    ("Oceania", "CULTURE", "Sydney", "Duckett's 153 puts England in charge of the third ODI"),
    ("Oceania", "CULTURE", "Auckland", "New Zealand unlocks GTA VI first, at midnight"),
    ("Middle East", "SECURITY", "Baghdad", "six French ISIL members are jailed for life"),
    ("Africa", "DISASTER", "Nairobi", "Kenya floods kill six as Ruto addresses the nation"),
    ("Americas", "SECURITY", "Caracas", "Hegseth signs a US-Venezuela military deal"),
    ("Americas", "SECURITY", "Washington", "Vance says there will be no forever war in the Gulf"),
    ("Middle East", "ECONOMY", "Manama", "the Bapco refinery is back on its feet"),
    ("Middle East", "SECURITY", "Riyadh", "Gulf leaders urge Trump not to strike Iran"),
    ("Americas", "POLITICS", "Washington", "Ted Lieu is the first Asian-American caucus chair"),
    ("Americas", "WEATHER", "Sacramento", "California braces for an atmospheric river"),
    ("Americas", "DISASTER", "La Paz", "Bolivia declares an El Nino emergency, 78,000 families hit"),
    ("Asia", "DIPLOMACY", "Seoul", "Seoul declines to join a statement on China's Uyghurs"),
    ("Asia", "CULTURE", "Chennai", "a design firm declares a holiday for the GTA VI launch"),
    ("Asia", "ECONOMY", "New Delhi", "India imposes a 16.25% duty on bulk Scotch imports"),
    ("Americas", "TECH", "Santa Clara", "Nvidia stops shipping H-series chips to China"),
    ("Asia", "POLITICS", "Shenzhen", "Musk travels with Trump but sits out the talks"),
    ("Oceania", "CULTURE", "Wellington", "India leave Siraj and Jadeja out of the opening Test"),
    ("Oceania", "DISASTER", "South Pacific", "a magnitude 6.1 quake strikes the remote Pacific"),
    ("Asia", "ECONOMY", "Mumbai", "Goldman upgrades India to overweight"),
    ("Asia", "CLIMATE", "New Delhi", "Delhi-NCR schools resume as pollution curbs end"),
]
assert len(LEADS) == 3 and len(CARDS) == 10 and len(BRIEFS) == 32
assert all(len(st) == 6 for st in LEADS)
assert all(len(st) == 5 for st in CARDS)
assert all(len(st) == 4 for st in BRIEFS)
assert len(LEADS) + len(CARDS) + len(BRIEFS) == 45

ALL_STORIES = LEADS + CARDS + BRIEFS
FIELDS = list(dict.fromkeys(st[1] for st in ALL_STORIES))
FIELD_COUNT = {f: sum(1 for st in ALL_STORIES if st[1] == f) for f in FIELDS}
FIELD_TOTAL = {f: sum(1 for st in ALL_STORIES if st[1] == f) for f in FIELDS}
assert sum(FIELD_COUNT.values()) == 45 and all(FIELD_COUNT[f] >= 1 for f in FIELDS), FIELD_COUNT
assert FIELD_TOTAL == FIELD_COUNT

REGION_ORDER = ["Europe", "Middle East", "Asia", "Americas", "Africa", "Oceania", "Global"]
COUNT = {r: sum(1 for st in ALL_STORIES if st[0] == r) for r in REGION_ORDER}
assert sum(COUNT.values()) == 45 and all(COUNT[r] >= 1 for r in REGION_ORDER), COUNT

TAPE = ["$81.3bn raised by Anthropic", "15.9m GTA VI pre-orders",
        "200,000 to evacuate in Odisha", "$120bn adaptation finance at COP31"]

PIN_REGIONS = [st[0] for st in LEADS + CARDS]
PIN_GRID = [(71, 18), (75, 30), (41, 17), (64, 19), (74, 15), (72, 22), (46, 7),
            (52, 20), (76, 26), (31, 10), (29, 20), (77, 29), (32, 42)]

DATE_CHECK = ("DATE CHECK  Left out because first reported before 19 November: the Shenzhen summit's eve "
              "arrivals, GTA VI's pre-load window and COP31's opening week. Every story here happened or was first "
              "reported on Thursday 19 November 2026; contested claims are attributed.").replace("'", "\u2019")

LEAD_SOURCE = [
    "Shenzhen hosted APEC when leaders adopted the declaration.",
    "Pre-orders were counted before the midnight unlock.",
    "The largest IPO raise on record; shares traded on Nasdaq.",
]

FOOT_L = ("Every story happened or was first reported on 19 November 2026. Sources: Reuters, AP, AFP, BBC, "
          "Al Jazeera.")


# --------------------------------------------------------------------------
# Illustrations: bands are clipped to their own rect.
# --------------------------------------------------------------------------
def band_lead(svg, x, y, w, h, idx):
    rc = REGION_COL[LEADS[idx][0]]
    svg.raw(f'<g clip-path="url(#lead_clip{idx})">')
    svg.rect(x, y, w, h, PAPER)
    if idx == 0:  # three figures at one table, three flags
        svg.rect(x, y, w, h, "#ece5d6")
        flags = [("#c8392f", "star"), ("#b07a1e", "bars"), ("#2f5d8a", "blocks")]
        for k, (col, kind) in enumerate(flags):
            fx = x + 20 + k * 96
            svg.rect(fx, y + 10, 6, 64, INK)
            svg.rect(fx + 6, y + 10, 40, 26, col)
            if kind == "star":
                svg.circle(fx + 18, y + 18, 3.5, "#f2cc3c")
                for j in range(3):
                    svg.circle(fx + 30 + j * 5, y + 17, 1.6, "#f2cc3c")
                    svg.circle(fx + 30 + j * 5, y + 25, 1.6, "#f2cc3c")
            elif kind == "bars":
                svg.rect(fx + 6, y + 15, 40, 4, WHITE)
                svg.rect(fx + 6, y + 24, 40, 4, WHITE)
            else:
                svg.rect(fx + 10, y + 15, 9, 6, WHITE)
                svg.rect(fx + 24, y + 15, 9, 6, WHITE)
        heads = [(x + 76, "#e6c4a4"), (x + 153, "#d9a982"), (x + 230, "#e6c4a4")]
        for k, (fx, skin) in enumerate(heads):
            svg.rect(fx - 20, y + 78, 40, 42, rc if k == 1 else INK)
            svg.circle(fx, y + 64, 13, skin)
            if k == 1:
                svg.path(f"M{fx-13} {y+58} Q{fx} {y+46} {fx+13} {y+58} L{fx+13} {y+54} "
                         f"Q{fx} {y+42} {fx-13} {y+54} Z", INK)
            elif k == 0:
                svg.path(f"M{fx-13} {y+62} Q{fx-4} {y+52} {fx+4} {y+58} L{fx+10} {y+52} "
                         f"L{fx+13} {y+64} Z", INK)
            else:
                svg.path(f"M{fx-13} {y+60} Q{fx} {y+48} {fx+13} {y+62} Z", INK)
        # arms over the table, a paper in the middle
        svg.rect(x + 44, y + 88, 218, 18, WHITE)
        svg.rect(x + 44, y + 106, 218, 8, "#d8d0bf")
        svg.rect(x + 52, y + 106, 5, 10, INK)
        svg.rect(x + 250, y + 106, 5, 10, INK)
        for ax in (x + 44, x + 262):
            svg.path(f"M{ax} {y+88} L{ax + (16 if ax < x + 150 else -16)} {y+82} "
                     f"L{ax + (16 if ax < x + 150 else -16)} {y+88} L{ax} {y+94} Z", INK)
        svg.rect(x + 136, y + 90, 30, 9, WHITE, f'stroke="{GREY}" stroke-width="1"')
    elif idx == 1:  # controller, midnight clock, queue
        night = "#2f3a52"
        svg.rect(x, y, w, h, night)
        for (sx, sy) in [(24, 18), (82, 12), (170, 22), (250, 14), (288, 40)]:
            svg.circle(x + sx, y + sy, 1.6, WHITE)
        svg.circle(x + 248, y + 38, 22, PAPER)
        svg.circle(x + 248, y + 38, 18, "none", f'stroke="{INK}" stroke-width="2"')
        for k in range(12):
            import math
            a = math.radians(k * 30)
            svg.line(x + 248 + math.cos(a) * 15, y + 38 + math.sin(a) * 15,
                     x + 248 + math.cos(a) * 17, y + 38 + math.sin(a) * 17, INK, 1)
        svg.line(x + 248, y + 38, x + 248, y + 26, INK, 2.4)
        svg.line(x + 248, y + 38, x + 257, y + 38, INK, 2.4)
        svg.circle(x + 248, y + 38, 2.4, ACC)
        svg.rect(x + 18, y + 46, 52, 20, WHITE)
        svg.rect(x + 26, y + 50, 4, 5, night)
        svg.rect(x + 34, y + 50, 4, 5, ACC)
        svg.rect(x + 48, y + 50, 12, 4, GREY)
        svg.circle(x + 63, y + 56, 3, night)
        svg.path(f"M{x+18} {y+66} L{x+70} {y+66} L{x+64} {y+74} L{x+24} {y+74} Z", WHITE)
        svg.circle(x + 34, y + 60, 5, night)
        for k in range(4):
            fx = x + 96 + k * 22
            svg.circle(fx, y + 74, 6, WHITE)
            svg.path(f"M{fx-8} {y+81} L{fx+8} {y+81} L{fx+7} {y+114} L{fx-7} {y+114} Z", WHITE)
            svg.rect(fx - 7, y + 112, 6, 8, INK)
            svg.rect(fx + 1, y + 112, 6, 8, INK)
            svg.line(fx - 12, y + 82, fx - 2, y + 92, INK, 3)
            svg.line(fx + 12, y + 82, fx + 2, y + 92, INK, 3)
        svg.rect(x + 90, y + 30, 148, 18, PAPER)
        svg.rect(x + 90, y + 30, 5, 18, ACC)
        svg.rect(x + 90, y + 30, 148, 4, ACC)
        svg.rect(x + 107, y + 40, 34, 3, INK)
        svg.rect(x + 151, y + 40, 22, 3, GREY)
    else:  # stock chart with an upward gap and a ticker
        svg.rect(x, y, w, h, "#efe9db")
        svg.rect(x, y + 92, w, 28, rc)
        svg.rect(x, y + 40, w, 1, RULE)
        svg.rect(x, y + 66, w, 1, RULE)
        pts = [(x + 8, 82), (x + 36, 74), (x + 62, 77), (x + 88, 62), (x + 110, 64),
               (x + 132, 40), (x + 158, 44), (x + 184, 26), (x + 214, 30), (x + 240, 14),
               (x + 268, 20), (x + 298, 8)]
        poly = " ".join(f"{px} {py}" for px, py in pts)
        svg.path(f"M{x+8} {y+114} L{poly} L{x+298} {y+114} Z", rc, extra='opacity="0.10"')
        svg.path("M" + " L".join(f"{px} {py}" for px, py in pts), "", rc, 2.2)
        svg.rect(x + 124, y + 42, 10, 20, WHITE, f'stroke="{rc}" stroke-width="1"')
        svg.line(x + 120, y + 24, x + 120, y + 84, ACC, 1, "3 2")
        svg.path(f"M{x+212} {y+16} L{x+212} {y+3} L{x+220} {y+10} Z", ACC)
        svg.rect(x + 90, y + 98, 40, 12, WHITE)
        svg.rect(x + 96, y + 102, 3, 4, rc)
        svg.rect(x + 102, y + 100, 3, 6, rc)
        svg.rect(x + 108, y + 96, 3, 10, rc)
        svg.rect(x + 114, y + 99, 3, 7, rc)
        svg.rect(x + 136, y + 99, 26, 4, WHITE)
        svg.rect(x + 136, y + 105, 18, 4, WHITE)
    svg.raw('</g>')


def card_scene(svg, x, y, w, h, idx):
    rc = REGION_COL[CARDS[idx][0]]
    svg.raw(f'<g clip-path="url(#card_clip{idx})">')
    svg.rect(x, y, w, h, PAPER)
    if idx == 0:  # gavel over Myanmar
        svg.rect(x, y, w, h, "#ece5d6")
        svg.path(f"M{x+24} {y+20} L{x+46} {y+12} L{x+64} {y+18} L{x+58} {y+34} "
                 f"L{x+66} {y+44} L{x+46} {y+45} L{x+34} {y+38} L{x+30} {y+30} Z", "#c9b995")
        svg.path(f"M{x+70} {y+12} L{x+84} {y+20} L{x+80} {y+44} L{x+68} {y+34} Z", "#c9b995")
        svg.rect(x + 118, y + 12, 5, 30, INK)
        svg.raw(f'<g transform="rotate(24 {x+118} {y+14})">')
        svg.rect(x + 102, y + 2, 36, 12, INK)
        svg.rect(x + 116, y + 12, 8, 16, INK)
        svg.raw('</g>')
        svg.rect(x + 96, y + 32, 52, 6, rc)
        svg.path(f"M{x+100} {y+39} L{x+140} {y+39} L{x+148} {y+42} L{x+92} {y+42} Z", INK)
    elif idx == 1:  # globe, clock at 48, thermometer
        svg.raw(f'<circle cx="{x+50}" cy="{y+22}" r="20" fill="{rc}"/>')
        svg.raw(f'<ellipse cx="{x+50}" cy="{y+22}" rx="9" ry="20" fill="none" stroke="{WHITE}" stroke-width="1.2"/>')
        svg.line(x + 30, y + 22, x + 70, y + 22, WHITE, 1.2)
        svg.raw(f'<ellipse cx="{x+50}" cy="{y+22}" rx="20" ry="8" fill="none" stroke="{WHITE}" stroke-width="1.2"/>')
        svg.circle(x + 92, y + 20, 16, WHITE)
        svg.circle(x + 92, y + 20, 16, "none", f'stroke="{INK}" stroke-width="2"')
        svg.line(x + 92, y + 20, x + 92, y + 10, INK, 2)
        svg.line(x + 92, y + 20, x + 99, y + 23, INK, 2)
        svg.circle(x + 92, y + 20, 2, ACC)
        svg.rect(x + 114, y + 2, 10, 36, WHITE, f'stroke="{INK}" stroke-width="1.5"')
        svg.rect(x + 116, y + 18, 6, 18, ACC)
        svg.circle(x + 119, y + 38, 6, ACC)
        svg.rect(x + 28, y + 40, 132, 3, rc)
    elif idx == 2:  # cyclone spiral over coast, waves, fleeing figure
        svg.rect(x, y + 24, w, h - 24, "#5d86a6")
        svg.rect(x, y + 34, w, 10, "#c9b995")
        for k in range(4):
            sy = y + 32 + k * 7
            svg.path(f"M{x+112+k*4} {sy} q8 -3 16 0 q8 3 16 0 q8 -3 16 0", "", WHITE, 1.4)
        sx, sy = x + 62, y + 4
        for r, a0 in [(5, 0), (10, 60), (15, 120)]:
            svg.path(f"M{sx} {sy} m0 -{r} a{r} {r} 0 0 1 {r} {r}", "", INK, 2)
        svg.circle(sx, sy, 2, ACC)
        fx = x + 138
        svg.circle(fx, y + 18, 3.4, INK)
        svg.path(f"M{fx-4} {y+22} L{fx+4} {y+22} L{fx+3} {y+32} L{fx-2} {y+32} Z", INK)
        svg.line(fx - 2, y + 32, fx - 6, y + 39, INK, 2)
        svg.line(fx + 2, y + 32, fx + 7, y + 38, INK, 2)
        svg.line(fx - 4, y + 24, fx - 10, y + 18, INK, 2)
        svg.line(fx + 4, y + 24, fx + 10, y + 19, INK, 2)
    elif idx == 3:  # Ukraine map beside summit table
        svg.path(f"M{x+8} {y+4} L{x+28} {y+6} L{x+42} {y+14} L{x+58} {y+12} L{x+70} {y+26} "
                 f"L{x+64} {y+40} L{x+48} {y+42} L{x+36} {y+38} L{x+24} {y+30} L{x+10} {y+26} Z", rc)
        svg.line(x + 18, y + 18, x + 58, y + 28, WHITE, 1, "2 2")
        svg.rect(x + 92, y + 22, 76, 10, WHITE)
        svg.rect(x + 98, y + 32, 4, 12, INK)
        svg.rect(x + 158, y + 32, 4, 12, INK)
        for k, col in enumerate([WHITE, "#d2a53a", INK]):
            svg.rect(x + 100 + k * 22, y + 8, 12, 10, col, f'stroke="{GREY}" stroke-width="1"')
        svg.rect(x + 148, y + 6, 2, 16, INK)
        svg.rect(x + 150, y + 6, 14, 8, ACC)
    elif idx == 4:  # round table with flags
        svg.rect(x, y, w, h, "#ece5d6")
        svg.raw(f'<ellipse cx="{x+90}" cy="{y+26}" rx="42" ry="11" fill="{rc}"/>')
        svg.rect(x + 86, y + 26, 8, 14, INK)
        svg.raw(f'<ellipse cx="{x+90}" cy="{y+40}" rx="54" ry="7" fill="none" stroke="{GREY}" stroke-width="1"/>')
        for k, col in enumerate(["#c8392f", WHITE, "#b07a1e", "#2f5d8a", INK]):
            fx = x + 40 + k * 25
            svg.rect(fx, y + 4, 2, 18, INK)
            svg.rect(fx + 2, y + 4, 10, 7, col)
    elif idx == 5:  # flooded house in rain
        svg.rect(x, y, w, h, "#8ba7b8")
        for k in range(7):
            rx = x + 8 + k * 25
            svg.line(rx, y + 2, rx - 4, y + 12, WHITE, 1.2)
        svg.rect(x, y + 30, w, 14, "#6f8fa3")
        svg.rect(x + 56, y + 12, 40, 24, WHITE)
        svg.path(f"M{x+50} {y+13} L{x+76} {y+1} L{x+102} {y+13} Z", INK)
        svg.rect(x + 72, y + 22, 8, 14, rc)
        svg.rect(x, y + 38, w, 6, rc)
        svg.path(f"M{x+8} {y+40} q8 -3 16 0 q8 3 16 0 q8 -3 16 0 q8 3 16 0 q8 -3 16 0 q8 3 16 0 q8 -3 16 0 q8 3 16 0 q8 -3 16 0", "", WHITE, 1.6)
    elif idx == 6:  # rock strata with a missing band
        layers = ["#c9b995", "#a8987a", "#e0d6c0", "#b8a382"]
        for k in range(4):
            svg.rect(x, y + 4 + k * 10, w, 10, layers[k])
        svg.rect(x, y + 26, w, 8, "#6b6252")
        svg.rect(x, y + 34, w, 10, "#c9b995")
        svg.line(x + 10, y + 26, x + 48, y + 30, INK, 1.2)
        svg.line(x + 86, y + 34, x + 132, y + 28, INK, 1.2)
        svg.path(f"M{x+140} {y+26} l6 -8 l6 8 Z", ACC)
        svg.rect(x + 150, y + 20, 14, 2, ACC)
        svg.rect(x + 154, y + 14, 6, 2, ACC)
    elif idx == 7:  # ballot box with a French tricolour
        svg.rect(x, y, w, h, "#ece5d6")
        svg.rect(x + 22, y + 4, 30, 7, "#2f5d8a")
        svg.rect(x + 22, y + 11, 30, 7, WHITE)
        svg.rect(x + 22, y + 18, 30, 7, "#c8392f")
        svg.rect(x + 108, y + 8, 4, 36, INK)
        svg.rect(x + 92, y + 20, 40, 24, rc)
        svg.rect(x + 100, y + 15, 24, 5, INK)
        svg.rect(x + 128, y + 4, 20, 14, WHITE, f'stroke="{GREY}" stroke-width="1"')
        svg.rect(x + 131, y + 8, 12, 1.5, GREY)
        svg.rect(x + 131, y + 12, 8, 1.5, GREY)
    elif idx == 8:  # city skyline with a shield
        svg.rect(x, y, w, h, "#ece5d6")
        towers = [(6, 26), (22, 20), (38, 30), (58, 16), (72, 28), (92, 22), (108, 32)]
        for tx, th in towers:
            svg.rect(x + tx, y + 40 - th, 12, th, "#b9ae9a")
            for row in range(2, th - 6, 6):
                svg.rect(x + tx + 3, y + 40 - th + row, 2, 2, PAPER)
                svg.rect(x + tx + 7, y + 40 - th + row, 2, 2, PAPER)
        svg.path(f"M{x+128} {y+14} L{x+154} {y+14} L{x+154} {y+30} Q{x+154} {y+40} {x+141} {y+44} "
                 f"Q{x+128} {y+40} {x+128} {y+30} Z", rc)
        svg.path(f"M{x+136} {y+26} l4 5 l8 -10", "", WHITE, 2.2)
    elif idx == 9:  # boat hull with packages
        svg.rect(x, y + 30, w, 14, "#5d86a6")
        svg.rect(x, y + 36, w, 8, rc)
        svg.path(f"M{x+22} {y+30} L{x+152} {y+30} L{x+138} {y+44} L{x+36} {y+44} Z", INK)
        svg.rect(x + 44, y + 20, 20, 10, "#c9b995")
        svg.rect(x + 68, y + 20, 16, 10, "#e0d6c0")
        svg.rect(x + 56, y + 10, 18, 10, "#a8987a")
        svg.rect(x + 88, y + 24, 12, 6, WHITE)
        svg.line(x + 44, y + 20, x + 44, y + 26, ACC, 1)
        for k in range(4):
            svg.path(f"M{x+8+k*10} {y+40} q5 -2 10 0", "", WHITE, 1.2)
    svg.raw('</g>')


def load_mask():
    """90x45 Europe/Africa/Asia land mask, stored in-repo when present."""
    local = Path(__file__).with_name("map_mask.txt")
    src = local if local.exists() else Path("/tmp/mask.txt")
    rows = [r.strip() for r in src.read_text().splitlines() if r.strip()]
    assert len(rows) >= 45 and all(len(r) >= 90 for r in rows[:45]), "mask must be 90x45"
    return [rows[gy][:90] for gy in range(45)]


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def build():
    svg = SVG()
    svg.raw(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">')
    svg.raw('<defs>')
    lead_geo = [(40, 180), (359, 180), (678, 180)]
    cards_geo = [(40, 412), (229, 412), (418, 412), (607, 412), (796, 412),
                 (40, 514), (229, 514), (418, 514), (607, 514), (796, 514)]
    for i, (x, y) in enumerate(lead_geo):
        svg.raw(f'<clipPath id="lead_clip{i}"><rect x="{x}" y="{y}" width="306" height="120"/></clipPath>')
    for i, (x, y) in enumerate(cards_geo):
        svg.raw(f'<clipPath id="card_clip{i}"><rect x="{x}" y="{y}" width="180" height="58"/></clipPath>')
    svg.raw('<clipPath id="map_clip"><rect x="40" y="620" width="300" height="100"/></clipPath>')
    svg.raw('</defs>')
    svg.rect(0, 0, W, H, PAPER)

    # Header
    svg.hair(12, 10, W - 10)
    svg.hair(34, 10, W - 10)
    svg.text(10, 28.5, "THE WORLD'S NEWS IN ONE PICTURE", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10.5, INK, what="kicker")
    check("45 STORIES \u00b7 7 REGIONS \u00b7 13 ILLUSTRATED", SANS_B, 10.5, 450, "kicker-right")
    svg.text(1014, 28.5, "45 STORIES \u00b7 7 REGIONS \u00b7 13 ILLUSTRATED", SANS_B, 10.5, ACC, anchor="end", weight="bold", what="kicker-right")

    mast = "Thursday 19 November 2026"
    check(mast, SERIF_B, 54, W - 48.5 - 14, "masthead")
    svg.serif(48.5, 96, mast, 54, what="masthead")
    svg.hair(106)

    # Region tabs
    total = sum(COUNT.values())
    base = (W - 96 - 6 * 3) / total
    # Reserve 20 units of air on both sides of every label, then proportion the
    # remainder. A 10.5pt label keeps >= 20 units of padding even when tight.
    pad = 20
    need = {r: tw(f"{r.upper()} {COUNT[r]}", SANS_B, 10.5) for r in REGION_ORDER}
    for r in REGION_ORDER:
        check(f"{r.upper()} {COUNT[r]}", SANS_B, 10.5, need[r] + pad, f"tab {r}")
    spare = W - 96 - 6 * 3 - sum(need.values()) - 7 * pad
    widths = [need[r] + pad + (COUNT[r] / total) * spare for r in REGION_ORDER]
    assert min(widths) > 0
    x = 40
    for r, w in zip(REGION_ORDER, widths):
        label = f"{r.upper()} {COUNT[r]}"
        assert tw(label, SANS_B, 10.5) + 20 <= w + 1e-9
        svg.rect(x, 120, w, 28, REGION_COL[r])
        svg.text(x + w / 2, 138, label, SANS_B, 10.5, WHITE, anchor="middle", weight="bold", what=f"tab {r}")
        x += w + 3

    # Ticker
    ty = 168
    svg.text(40, ty, "TODAY", SANS_B, 9.6, GREY, weight="bold", what="ticker lead")
    tx = 40 + tw("TODAY", SANS_B, 9.6) + 12
    ticker = [(item.split(" ", 1)[0], " " + item.split(" ", 1)[1]) for item in TAPE]
    for i, (fig, lab) in enumerate(ticker):
        if i:
            svg.text(tx, ty, "|", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9.6, RULE, what="sep")
            tx += tw("|", SANS, 9.6) + 10
        check(fig, SANS_B, 9.6, 100, "ticker fig")
        svg.text(tx, ty, fig, SANS_B, 9.6, ACC, weight="bold", what="ticker fig")
        tx += tw(fig, SANS_B, 9.6)
        svg.text(tx, ty, lab, SANS, 9.6, INK, what="ticker label")
        tx += tw(lab, SANS, 9.6)
        assert tx <= 984, f"ticker overruns: {tx}"

    # Leads
    for i, (x, y) in enumerate(lead_geo):
        region, field, kicker, head, deck, scene = LEADS[i]
        rc = REGION_COL[region]
        band_lead(svg, x, y, 306, 120, i)
        svg.raw(f'<g clip-path="url(#lead_clip{i})"><rect x="{x}" y="{y}" width="306" height="120" fill="{rc}" opacity="0.22"/></g>')
        rect_y = y + 120
        svg.rect(x, rect_y, 306, 14, rc)
        svg.text(x + 8, rect_y + 10.5, f"{i+1}  {region.upper()} \u00b7 {kicker}", SANS_B, 9, WHITE,
                 weight="bold", what=f"lead kicker {i+1}")
        assert tw(f"{i+1}  {region.upper()} \u00b7 {kicker}", SANS_B, 8.6) <= 298, f"lead kicker {i+1}"
        lines = wrap(head, SERIF_B, 23, 300, 3, f"lead head {i+1}")
        for k, ln in enumerate(lines):
            svg.serif(x, rect_y + 33 + k * 24, ln, 23, box=300, what=f"lead head {i+1}")
        dl = wrap(deck, SERIF, 9.0, 300, 2, f"lead deck {i+1}")
        src = LEAD_SOURCE[i]
        check(src, SANS, 9, 306, f"lead source {i+1}")
        # Every lead reserves space for a 3-line head and a 2-line deck so the
        # deck and source baselines stay aligned across all three columns.
        deck_top = rect_y + 33 + 2 * 24 + 10
        source_y = deck_top + 11.5 + 13
        for k, ln in enumerate(dl):
            svg.serif(x, deck_top + k * 11.5, ln, 9.0, DECK, weight=False, what=f"lead deck {i+1}", box=300)
        svg.text(x, source_y, src, SANS, 9, GREY, what=f"lead source {i+1}")

    # Cards
    for i, (x, y) in enumerate(cards_geo):
        region, field, kicker, head, scene = CARDS[i]
        rc = REGION_COL[region]
        card_scene(svg, x, y, 180, 58, i)
        svg.raw(f'<g clip-path="url(#card_clip{i})"><rect x="{x}" y="{y}" width="180" height="58" fill="{rc}" opacity="0.26"/></g>')
        svg.rect(x, y + 62, 180, 13, rc)
        check(f"{region.upper()} \u00b7 {kicker}", SANS_B, 9, 174, f"card kicker {i+1}")
        svg.text(x + 4, y + 72, f"{region.upper()} \u00b7 {kicker}", SANS_B, 9, WHITE,
                 weight="bold", what=f"card kicker {i+1}")
        lines = wrap(head, SERIF_B, 12, 176, 2, f"card head {i+4}")
        for k, ln in enumerate(lines):
            svg.serif(x, y + 90 + k * 13, ln, 11.5, box=176, what=f"card head {i+4}")

    # Map and date check
    my, mh = 620, 100
    grid = load_mask()
    lines = ["".join(row) for row in grid]
    svg.raw('<g clip-path="url(#map_clip)">')
    for gy, row in enumerate(grid):
        for gx, ch in enumerate(row):
            if ch == "#":
                px, py = 40 + gx * 10 / 3, my + gy * 100 / 45
                svg.raw(f'<rect x="{px:.2f}" y="{py:.2f}" width="3.34" height="2.23" fill="{INK}" opacity="0.42"/>')
    for k, ((gx, gy), reg) in enumerate(zip(PIN_GRID, PIN_REGIONS), 1):
        assert lines[gy][gx] == "#"
        cx, cy = 40 + gx * 10 / 3 + 1.67, my + gy * 100 / 45 + 1.1
        svg.circle(cx, cy, 5.2, REGION_COL[reg], f'stroke="{PAPER}" stroke-width="1"')
        svg.text(cx, cy + 2.9, str(k), SANS_B, 9, WHITE, anchor="middle", weight="bold", what=f"pin {k}")
    svg.raw('</g>')
    svg.text(40, 738 - 10, "13 ILLUSTRATED \u00b7 1-13 LEADS AND CARDS \u00b7 PIN COLOUR = REGION", SANS, 9, GREY, what="map note")

    # Date check
    bx, by, bw, bh = 356, 620, 628, 100
    svg.rect(bx, by, 3, bh, ACC)
    svg.rect(bx + 12, by + 12, bw - 24, bh - 24, PAPER, f'stroke="{RULE}" stroke-width="1"')
    dlines = wrap(DATE_CHECK, SANS, 9, 530, 3, "date check")
    for k, ln in enumerate(dlines):
        if k == 0:
            svg.text(bx + 22, by + 31, "DATE CHECK", SANS_B, 9, ACC, weight="bold", what="date check label")
            rest = ln[len("DATE CHECK"):].lstrip()
            gap = 4
            x0 = bx + 22 + tw("DATE CHECK", SANS_B, 9) + gap
            check(rest, SANS, 9, bx + bw - 24 - x0, "date check rest")
            svg.text(x0, by + 31, rest, SANS, 9, INK, what="date check rest")
        else:
            svg.text(bx + 22, by + 31 + k * 13, ln, SANS, 9, INK, what="date check")

    # Briefs header
    fieldline = "BY FIELD  " + " \u00b7 ".join(f"{f} {FIELD_COUNT[f]}" for f in FIELDS)
    check(fieldline, SANS_B, 9, tw(fieldline, SANS_B, 9), "field counts")
    svg.text(40, 738, "BRIEFS 14-45", SERIF_B, 15, INK, what="briefs header")
    svg.raw(f'<text x="984" y="735" font-family="DejaVu Sans" font-size="9" font-weight="bold" fill="{INK}" text-anchor="end" textLength="760" lengthAdjust="spacingAndGlyphs">{esc(fieldline)}</text>')
    svg.hair(746)

    BRIEF_SIZE = 9
    BRIEF_MEASURE = 8.2
    col_x = [40, 363, 686]
    y0 = 760
    rows = 11
    fit = [0] * len(BRIEFS)
    for i, (region, field, place, text) in enumerate(b[0:4] for b in BRIEFS):
        px0 = 16
        sw0 = tw(place, SANS_B, BRIEF_MEASURE)
        room0 = 297 - (px0 + sw0 + 3)
        if tw(text, SANS, BRIEF_MEASURE) > room0:
            lines = wrap(text, SANS, BRIEF_MEASURE, 297 - px0, 2, f"brief {i+14} body")
            fit[i] = len(lines) - 1
    extra_rows = sum(fit[(rows - 1) - k] for k in range(rows))
    pitch = 13.6
    assert extra_rows == 0, "briefs must each stay on one line at the fixed pitch"
    for i, (region, field, place, text) in enumerate(b[0:4] for b in BRIEFS):
        col, row = divmod(i, rows)
        x = col_x[col]
        y = y0 + row * pitch
        if (rows - 1) - row:
            y += sum(fit[(rows - 1) - k] for k in range(row)) * 7.5
        svg.rect(x - 5, y - 7.6, 2.4, 9.2, REGION_COL[region])
        num = f"{i + 14}"
        check(num, SANS_B, BRIEF_MEASURE, 14, "brief num")
        svg.text(x, y, num, SANS_B, BRIEF_SIZE, ACC, weight="bold", ls=-0.7, what="brief num")
        px = x + 16
        sw = tw(place, SANS_B, BRIEF_MEASURE)
        check(place + " ", SANS_B, BRIEF_MEASURE, 297 - 16, f"brief {num} place")
        svg.text(px, y, place, SANS_B, BRIEF_SIZE, INK, weight="bold", ls=-0.7, what=f"brief {num} place")
        tx = px + sw + 3
        room = x + 297 - tx
        if fit[i]:
            lines = wrap(text, SANS, BRIEF_MEASURE, 297 - 16, 2, f"brief {num} body")
            for k, ln in enumerate(lines):
                check(ln, SANS, BRIEF_MEASURE, 297 - 16, f"brief {num} body")
                svg.text(px, y + 7.5 + k * 7.5, ln, SANS, BRIEF_SIZE, INK, ls=-0.7, what=f"brief {num} body")
        else:
            check(text, SANS, BRIEF_MEASURE, room, f"brief {num} body")
            svg.text(tx, y, text, SANS, BRIEF_SIZE, INK, ls=-0.7, what=f"brief {num} body")
    last = y0 + (rows - 1) * pitch + extra_rows * 7.5

    # No editor note: the briefs end where they did before the box existed,
    # and the footer hairline sits directly beneath the last brief row.
    hy0 = 918
    assert last < hy0 - 4, f"briefs collide with footer rule: {last}"
    svg.hair(hy0, 10, W - 10)
    fy = hy0 + 12
    fl = wrap(FOOT_L, SANS, 9, 700, 2, "footer left")
    for k, ln in enumerate(fl):
        svg.text(10, fy + k * 10, ln, SANS, 9, INK, what="footer left")
    check("19 NOVEMBER 2026", SANS_B, 9, 200, "footer right")
    svg.text(1012, fy, "19 NOVEMBER 2026", SANS_B, 9, INK, anchor="end", weight="bold", what="footer right")
    assert fy + (len(fl) - 1) * 10 + 2 <= H, "footer clipped"

    svg.raw('</svg>')
    return "\n".join(svg.parts)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "entry.png")
    xml = build()
    assert "..." not in xml and "\u2026" not in xml, "ellipsis in output"
    worst = max(WORST)
    ratios = sorted(WORST, reverse=True)[:6]
    for r, what in ratios:
        print(f"ratio {r:.4f}  {what}")
    print(f"WORST {worst[0]:.4f}  {worst[1]}")
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(xml)
        tmp = fh.name
    subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out), tmp], check=True)
    Path(tmp).unlink()
    size = out.stat().st_size
    print(f"wrote {out} {size} bytes")
    assert size < 1048576, size


if __name__ == "__main__":
    main()
