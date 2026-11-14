#!/usr/bin/env python3
"""Generate the 'Classic-Black' aurorae window decoration.

Geometry is measured 1:1 from the light classic frame on the Deck (thin outline,
gradient title bar, 22px square outlined buttons, 4px frame); colours are a black version.
"""
import os, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "Classic-Black"
os.makedirs(OUT, exist_ok=True)

# ---- palette (black version of the reference) ----
OUTER = "#000000"      # 1px outer outline        (ref #81878d)
HI    = "#3a3a3a"      # 1px inner highlight      (ref #f3f4f5)
MID   = "#1b1b1b"      # frame body               (ref #e3e5e7)
INNER = "#000000"      # line against the content (ref #bbc0c6)
T_TOP, T_DIP, T_BOT = "#2a2a2a", "#161616", "#232323"   # title gradient (ref d9dcdf -> c5c9cd -> e0e2e4)

TITLE_EDGE_TOP, TITLE_H, TITLE_EDGE_BOTTOM = 2, 25, 1
TOP = TITLE_EDGE_TOP + TITLE_H + TITLE_EDGE_BOTTOM      # 28
B = 4                                                    # side/bottom border
W = 12                                                   # width of stretchable pieces

def rect(x, y, w, h, fill):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>'

def title_rows(x, w, y0):
    # rows: outer, highlight, gradient(25), separator
    return "".join([
        rect(x, y0, w, 1, OUTER),
        rect(x, y0 + 1, w, 1, HI),
        rect(x, y0 + 2, w, TITLE_H, "url(#tg)"),
        rect(x, y0 + 2 + TITLE_H, w, 1, INNER),
    ])

def side_cols(x0, y, h, mirror):
    cols = [OUTER, HI, MID, INNER]
    if mirror:
        cols = cols[::-1]
    return "".join(rect(x0 + i, y, 1, h, c) for i, c in enumerate(cols))

def bottom_rows(x, y0, w):
    return "".join(rect(x, y0 + i, w, 1, c) for i, c in enumerate([INNER, MID, MID, OUTER]))

def frame(prefix, ox, oy):
    """One full set of frame elements at offset (ox, oy)."""
    g = []
    def el(name, x, y, w, h, body):
        g.append(f'<g id="{prefix}-{name}" transform="translate({ox + x},{oy + y})">'
                 f'<rect x="0" y="0" width="{w}" height="{h}" fill="none"/>{body}</g>')
    # top row
    tl = title_rows(0, B, 0) + rect(0, 0, 1, TOP, OUTER) + rect(1, 1, 1, TOP - 1, HI)
    el("topleft", 0, 0, B, TOP, tl)
    el("top", B, 0, W, TOP, title_rows(0, W, 0))
    tr = title_rows(0, B, 0) + rect(B - 1, 0, 1, TOP, OUTER)
    el("topright", B + W, 0, B, TOP, tr)
    # middle row
    el("left", 0, TOP, B, W, side_cols(0, 0, W, False))
    el("center", B, TOP, W, W, rect(0, 0, W, W, "#101010"))
    el("right", B + W, TOP, B, W, side_cols(0, 0, W, True))
    # bottom row
    bl = bottom_rows(0, 0, B) + rect(0, 0, 1, B, OUTER) + rect(1, 0, 1, B - 1, HI)
    el("bottomleft", 0, TOP + W, B, B, bl)
    el("bottom", B, TOP + W, W, B, bottom_rows(0, 0, W))
    br = bottom_rows(0, 0, B) + rect(B - 1, 0, 1, B, OUTER)
    el("bottomright", B + W, TOP + W, B, B, br)
    return "".join(g)

defs = (f'<defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{T_TOP}"/><stop offset="0.16" stop-color="{T_DIP}"/>'
        f'<stop offset="1" stop-color="{T_BOT}"/></linearGradient></defs>')
size = B + W + B
body = (frame("decoration", 0, 0) + frame("decoration-inactive", 30, 0) +
        frame("decoration-opaque", 60, 0) + frame("decoration-opaque-inactive", 90, 0) +
        '<rect id="hint-stretch-borders" x="0" y="80" width="2" height="2" fill="none"/>')
open(f"{OUT}/decoration.svg", "w").write(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="130" height="90" viewBox="0 0 130 90">{defs}{body}</svg>')

# ---- buttons: 22x22, 1px outline, 2px radius, bold glyph ----
BTN = 22
STATES = {   # state: (fill top, fill bottom, outline, glyph)
    "active":               ("#2c2c2c", "#202020", "#5a5a5a", "#ececec"),
    "hover":                ("#3e3e3e", "#2f2f2f", "#7a7a7a", "#ffffff"),
    "pressed":              ("#121212", "#181818", "#5a5a5a", "#d0d0d0"),
    "deactivated":          ("#2c2c2c", "#202020", "#3e3e3e", "#5a5a5a"),
    "inactive":             ("#262626", "#1d1d1d", "#4a4a4a", "#a8a8a8"),
    "hover-inactive":       ("#3e3e3e", "#2f2f2f", "#7a7a7a", "#ffffff"),
    "pressed-inactive":     ("#121212", "#181818", "#5a5a5a", "#d0d0d0"),
    "deactivated-inactive": ("#262626", "#1d1d1d", "#363636", "#4a4a4a"),
}

def glyph(kind, c):
    if kind == "minimize":
        return f'<rect x="6" y="13.5" width="10" height="3" fill="{c}"/>'
    if kind == "maximize":
        return (f'<rect x="6.75" y="6.75" width="8.5" height="8.5" fill="none" stroke="{c}" stroke-width="1.8"/>'
                f'<rect x="6" y="6" width="10" height="3" fill="{c}"/>')
    if kind == "restore":
        return (f'<rect x="8.5" y="5.5" width="7" height="7" fill="none" stroke="{c}" stroke-width="1.3"/>'
                f'<rect x="8" y="5" width="8" height="1.6" fill="{c}"/>'
                f'<rect x="5.5" y="9.5" width="7" height="7" fill="#00000000" stroke="{c}" stroke-width="1.3"/>'
                f'<rect x="5" y="9" width="8" height="1.6" fill="{c}"/>')
    if kind == "close":
        return (f'<path d="M6.5 6.5 L15.5 15.5 M15.5 6.5 L6.5 15.5" stroke="{c}" stroke-width="2.8" '
                f'stroke-linecap="square"/>')
    if kind == "alldesktops":
        return f'<circle cx="11" cy="11" r="3.4" fill="none" stroke="{c}" stroke-width="2.6"/>'
    if kind == "alldesktops-on":
        return f'<circle cx="11" cy="11" r="3.6" fill="{c}" stroke="{c}" stroke-width="2"/>'
    if kind == "keepabove":
        return f'<path d="M6 13 L11 8 L16 13" fill="none" stroke="{c}" stroke-width="2"/>'
    if kind == "keepbelow":
        return f'<path d="M6 9 L11 14 L16 9" fill="none" stroke="{c}" stroke-width="2"/>'
    if kind == "shade":
        return f'<rect x="6" y="7" width="10" height="2" fill="{c}"/>'
    if kind == "help":
        return (f'<path d="M8.5 8.5 Q8.5 6 11 6 Q13.5 6 13.5 8.3 Q13.5 10 11 11 L11 12.5" fill="none" '
                f'stroke="{c}" stroke-width="1.8"/><rect x="10" y="14.5" width="2" height="2" fill="{c}"/>')
    return ""

def button(kind, extra_on=None):
    parts, x = [], 0
    for st, (f1, f2, o, gc) in STATES.items():
        k = kind
        if extra_on and st.startswith("pressed"):
            k = extra_on
        parts.append(
            f'<linearGradient id="g{x}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{f1}"/>'
            f'<stop offset="1" stop-color="{f2}"/></linearGradient>'
            f'<g id="{st}-center" transform="translate({x},0)">'
            f'<rect x="0" y="0" width="{BTN}" height="{BTN}" fill="none"/>'
            f'<rect x="0.5" y="0.5" width="{BTN-1}" height="{BTN-1}" rx="2" fill="url(#g{x})" stroke="{o}"/>'
            f'{glyph(k, gc)}</g>')
        x += BTN + 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{x}" height="{BTN}" '
            f'viewBox="0 0 {x} {BTN}">{"".join(parts)}</svg>')

for kind in ("minimize", "maximize", "restore", "close", "keepabove", "keepbelow", "shade", "help"):
    open(f"{OUT}/{kind}.svg", "w").write(button(kind))
open(f"{OUT}/alldesktops.svg", "w").write(button("alldesktops", extra_on="alldesktops-on"))

name = os.path.basename(os.path.abspath(OUT))
open(f"{OUT}/metadata.desktop", "w").write(f"""[Desktop Entry]
Name={name}
Comment=Classic flat frame with square buttons, in black
X-KDE-PluginInfo-Author=deck-aero
X-KDE-PluginInfo-Name={name}
X-KDE-PluginInfo-Version=1.0
X-KDE-PluginInfo-License=GPL_V2
X-KDE-PluginInfo-EnabledByDefault=true
""")
open(f"{OUT}/{name}rc", "w").write(f"""[General]
ActiveTextColor=235,235,235,255
InactiveTextColor=150,150,150,255
UseTextShadow=false
Animation=120
TitleAlignment=Left
TitleVerticalAlignment=Center
LeftButtons=MS
RightButtons=IAX
Shadow=false
HaloActive=false
HaloInactive=false
DecorationPosition=0

[Layout]
BorderLeft={B}
BorderRight={B}
BorderBottom={B}
BorderTop={B}
TitleEdgeTop={TITLE_EDGE_TOP}
TitleEdgeBottom={TITLE_EDGE_BOTTOM}
TitleEdgeLeft=5
TitleEdgeRight=4
TitleEdgeTopMaximized=0
TitleEdgeBottomMaximized=0
TitleEdgeLeftMaximized=1
TitleEdgeRightMaximized=1
TitleBorderLeft=4
TitleBorderRight=4
TitleHeight={TITLE_H}
ButtonWidth=22
ButtonWidthMinimize=22
ButtonWidthMaximizeRestore=22
ButtonWidthClose=22
ButtonWidthAlldesktops=22
ButtonWidthKeepabove=22
ButtonWidthKeepbelow=22
ButtonWidthShade=22
ButtonWidthHelp=22
ButtonWidthMenu=20
ButtonHeight=22
ButtonSpacing=1
ButtonMarginTop=1
ExplicitButtonSpacer=4
PaddingTop=0
PaddingBottom=0
PaddingLeft=0
PaddingRight=0
""")
print("wrote", OUT)
