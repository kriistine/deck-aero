#!/usr/bin/env python3
"""Deckboard: a smaller on-screen keyboard for Steam Deck desktop mode.

Typing works like Steam's keyboard: each trackpad moves its own cursor
(left pad -> left side of the keyboard, right pad -> right side), and
clicking a trackpad down types the key under that cursor.

Controls while open:
  X             show / hide the keyboard
  pad click     type the key under that pad's cursor
  B             backspace
  Y             reset position to bottom centre
  L2            shift (hold)
  D-pad         move the keyboard (position is remembered)
  R2            enter
  ... (QAM)     open / close the wofi app launcher (works even while hidden)

Ctrl / Alt / Super are "sticky": tap one, then tap the next key to send the
combo (e.g. Super then Left). Tap a lit modifier again to send it on its own
(Super tapped twice opens the app launcher).
"""

import json
import subprocess
import os
import struct
import sys
import threading
import time
import tkinter as tk

import base64
import fcntl
import zlib

import evdev
from evdev import UInput, ecodes as e

CONFIG_PATH = os.path.expanduser("~/.config/deckboard.json")
DEFAULT_CONFIG = {
    "scale": 0.6,          # 1.0 = roughly Steam's keyboard size
    "bottom_margin": 0,    # pixels between keyboard and bottom of screen
    "toggle_combos": [["X"]],  # any of these shows / hides (ignored while STEAM is held)
    "pad_overlap": 0.10,   # how far each pad's half reaches past the middle
    "press_threshold": 10000,  # pad pressure (0-32767) that counts as a click
    "release_threshold": 6000, # pressure must drop below this before the next click
    "aim_threshold": 2000,     # key is chosen where the thumb was before pressure rose past this
    "haptics": True,
    "haptic_press": [5000, 2000, 5],   # on_us, off_us, repeats when a key types
    "haptic_hover": [2500, 0, 1],      # light tap when the thumb moves onto a new key
}

# ---------------------------------------------------------------- layout --
# (label, shifted label, keycode, width in key units)
K = e
ROWS = [
    [("`", "~", K.KEY_GRAVE, 1), ("1", "!", K.KEY_1, 1), ("2", "@", K.KEY_2, 1),
     ("3", "#", K.KEY_3, 1), ("4", "$", K.KEY_4, 1), ("5", "%", K.KEY_5, 1),
     ("6", "^", K.KEY_6, 1), ("7", "&", K.KEY_7, 1), ("8", "*", K.KEY_8, 1),
     ("9", "(", K.KEY_9, 1), ("0", ")", K.KEY_0, 1), ("-", "_", K.KEY_MINUS, 1),
     ("=", "+", K.KEY_EQUAL, 1), ("⌫", "⌫", K.KEY_BACKSPACE, 1.5)],
    [("Tab", "Tab", K.KEY_TAB, 1.5)] +
    [(c, c.upper(), getattr(K, "KEY_" + c.upper()), 1) for c in "qwertyuiop"] +
    [("[", "{", K.KEY_LEFTBRACE, 1), ("]", "}", K.KEY_RIGHTBRACE, 1),
     ("\\", "|", K.KEY_BACKSLASH, 1)],
    [("Caps", "Caps", K.KEY_CAPSLOCK, 1.75)] +
    [(c, c.upper(), getattr(K, "KEY_" + c.upper()), 1) for c in "asdfghjkl"] +
    [(";", ":", K.KEY_SEMICOLON, 1), ("'", '"', K.KEY_APOSTROPHE, 1),
     ("Enter", "Enter", K.KEY_ENTER, 1.75)],
    [("Shift", "Shift", K.KEY_LEFTSHIFT, 2.25)] +
    [(c, c.upper(), getattr(K, "KEY_" + c.upper()), 1) for c in "zxcvbnm"] +
    [(",", "<", K.KEY_COMMA, 1), (".", ">", K.KEY_DOT, 1), ("/", "?", K.KEY_SLASH, 1),
     ("Shift", "Shift", K.KEY_RIGHTSHIFT, 2.25)],
    [("Ctrl", "Ctrl", K.KEY_LEFTCTRL, 1.25), ("Super", "Super", K.KEY_LEFTMETA, 1.25),
     ("Alt", "Alt", K.KEY_LEFTALT, 1.25), ("", "", K.KEY_SPACE, 5.5),
     ("Esc", "Esc", K.KEY_ESC, 1.25), ("←", "←", K.KEY_LEFT, 1), ("↓", "↓", K.KEY_DOWN, 1),
     ("↑", "↑", K.KEY_UP, 1), ("→", "→", K.KEY_RIGHT, 1)],
]
ROW_UNITS = 14.5
STICKY = {K.KEY_LEFTCTRL, K.KEY_LEFTMETA, K.KEY_LEFTALT}
SHIFTS = {K.KEY_LEFTSHIFT, K.KEY_RIGHTSHIFT}

# ------------------------------------------------------------------ theme --
# Same look as the rest of deck-aero:
#  * title strip = the Classic-Black window title bar (split gloss: grey top half,
#    hard cut to black, 1px highlight line), same as the Firefox tab strip / Nemo toolbar
#  * body = plain black, like the window frame
#  * keys = Nemo's toolbar buttons / the window buttons: 4px rounded, black outline,
#    1px highlight, grey gloss top half cut to black, white bold labels
#  * hover = the taskbar's cyan active-button gloss; lit (Shift/Caps/sticky) = cyan label + edge
THEME = {
    "opacity": 1.0,
    "accent": "#20d0fc",
    "body": "#0a0a0a",
    "title_gloss": [(0, "#373737"), (0.5, "#262626"), (0.5, "#030303"), (1, "#0f0f0f")],
    "title_highlight": "#535353", "frame_outer": "#000000", "frame_inner": "#262626",
    "title_text": "#ffffff", "help_text": "#a0a0a0",
    "text": "#ffffff", "text_lit": "#20d0fc",
    # key states: (gloss top, gloss mid, lower top, lower bottom, highlight line, outline)
    "normal": ("#474747", "#383838", "#050505", "#121212", "#777777", "#000000"),
    "hover":  ("#2fc8d8", "#1a9aa8", "#06535c", "#032e35", "#a6f3ff", "#20d0fc"),
    "lit":    ("#474747", "#383838", "#050505", "#121212", "#777777", "#20d0fc"),
    "cursor": "#e8eef3",
}


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a, b, t):
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def make_cursor_png(size, ring_w, centre_d, color, opacity=1.0):
    """Anti-aliased ring + centre dot as a transparent PNG (base64)."""
    r, g, b = _hex(color)
    R = size / 2
    ss = 4                                     # supersampling per axis
    raw = bytearray()
    for y in range(size):
        raw.append(0)                          # PNG filter: none
        for x in range(size):
            cover = 0
            for sy in range(ss):
                for sx in range(ss):
                    dx = x + (sx + 0.5) / ss - R
                    dy = y + (sy + 0.5) / ss - R
                    d = (dx * dx + dy * dy) ** 0.5
                    if (R - ring_w <= d <= R) or d <= centre_d / 2:
                        cover += 1
            raw += bytes((r, g, b, int(255 * opacity * cover / (ss * ss))))

    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        return c + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    return base64.b64encode(png)


def make_key_image(w, h, state, radius=4):
    """Glossy rounded key (Nemo / window-button style) as a PhotoImage.

    Corners are anti-aliased against the keyboard body colour, so no transparency is needed."""
    t1, t2, b1, b2, hl, ol = (_hex(c) for c in THEME[state])
    bg = _hex(THEME["body"])

    def mix(a, b, t):
        return tuple(x + (y - x) * t for x, y in zip(a, b))

    def cover(x, y, inset):
        """Fraction of pixel (x, y) inside the rounded rect shrunk by `inset` (3x3 supersampled)."""
        r = max(0.5, radius - inset)
        x0, y0, x1, y1 = inset, inset, w - inset, h - inset
        n = 0
        for sy in (0.17, 0.5, 0.83):
            for sx in (0.17, 0.5, 0.83):
                px, py = x + sx, y + sy
                if not (x0 <= px <= x1 and y0 <= py <= y1):
                    continue
                cx = min(max(px, x0 + r), x1 - r)
                cy = min(max(py, y0 + r), y1 - r)
                if (px - cx) ** 2 + (py - cy) ** 2 <= r * r:
                    n += 1
        return n / 9

    half = h / 2
    rows = []
    for y in range(h):
        if y == 1:
            fill = hl                                   # 1px highlight line
        elif y < half:
            fill = mix(t1, t2, y / max(1, half - 1))     # grey gloss
        else:
            fill = mix(b1, b2, (y - half) / max(1, h - half - 1))   # hard cut to black
        row = []
        for x in range(w):
            if x <= radius or x >= w - radius - 1 or y <= radius or y >= h - radius - 1:
                co, ci = cover(x, y, 0), cover(x, y, 1)
            else:
                co = ci = 1.0
            c = mix(mix(bg, ol, co), fill, ci)
            row.append("#%02x%02x%02x" % tuple(int(round(v)) for v in c))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(width=w, height=h)
    img.put(" ".join(rows))
    return img


# Steam's keyboard at 1.0 is ~1280x360 on the Deck screen.
BASE_KEY = 1280 / ROW_UNITS
BASE_ROW = 360 / 5

# ------------------------------------------------------- controller input --
# Steam Deck HID report (type 0x09), byte/bit positions from the Linux
# hid-steam driver.
BUTTONS = {
    "R2": (8, 0), "L2": (8, 1), "R1": (8, 2), "L1": (8, 3),
    "Y": (8, 4), "B": (8, 5), "X": (8, 6), "A": (8, 7),
    "DUP": (9, 0), "DRIGHT": (9, 1), "DLEFT": (9, 2), "DDOWN": (9, 3),
    "STEAM": (9, 5), "L5": (9, 7), "R5": (10, 0),
    "LPAD_CLICK": (10, 1), "RPAD_CLICK": (10, 2),
    "LPAD_TOUCH": (10, 3), "RPAD_TOUCH": (10, 4),
    "L3": (10, 6), "R3": (11, 2),
    "L4": (13, 1), "R4": (13, 2),
    "QAM": (14, 2),   # the "..." quick access button
}

# "..." button opens the wofi app launcher (the deck-aero container's launcher).
LAUNCHER_CMD = [os.path.expanduser("~/.local/share/deckaero/bin/launcher-host")]


def find_hidraw():
    for name in sorted(os.listdir("/sys/class/hidraw")):
        try:
            with open(f"/sys/class/hidraw/{name}/device/uevent") as f:
                ev = f.read()
        except OSError:
            continue
        if "28DE" not in ev.upper() or "1205" not in ev:
            continue
        path = f"/dev/{name}"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        deadline = time.time() + 0.5
        while time.time() < deadline:
            try:
                d = os.read(fd, 64)
                if len(d) == 64 and d[2] == 0x09:
                    os.close(fd)
                    return path
            except BlockingIOError:
                time.sleep(0.01)
        os.close(fd)
    return None


def HIDIOCSFEATURE(n):
    return (3 << 30) | (n << 16) | (ord("H") << 8) | 0x06


class Haptics:
    """Trackpad haptic pulses (feature report 0x8F), same motors Steam uses."""
    SIDE = {"R": 0, "L": 1}

    def __init__(self, path, enabled):
        self.fd = None
        if enabled:
            try:
                self.fd = os.open(path, os.O_RDWR)
            except OSError as ex:
                print("haptics unavailable:", ex, file=sys.stderr)

    def pulse(self, side, spec):
        if self.fd is None:
            return
        on_us, off_us, count = spec
        buf = bytearray(65)
        buf[1], buf[2] = 0x8F, 7
        struct.pack_into("<BHHH", buf, 3, self.SIDE[side], on_us, off_us, count)
        try:
            fcntl.ioctl(self.fd, HIDIOCSFEATURE(65), bytes(buf))
        except OSError:
            pass


class Pad:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = None

    def run(self, path):
        fd = os.open(path, os.O_RDONLY)
        while True:
            d = os.read(fd, 64)
            if len(d) < 64 or d[2] != 0x09:
                continue
            lx, ly, rx, ry = struct.unpack_from("<hhhh", d, 16)
            lp, rp = struct.unpack_from("<HH", d, 56)
            btn = {k: bool(d[b] & (1 << bit)) for k, (b, bit) in BUTTONS.items()}
            with self.lock:
                self.state = (lx, ly, rx, ry, lp, rp, btn)

    def get(self):
        with self.lock:
            return self.state


# ------------------------------------------------------------------- UI --
class Deckboard:
    def __init__(self, cfg, pad, haptics):
        self.cfg = cfg
        self.pad = pad
        self.haptics = haptics
        self.hover = {"L": None, "R": None}
        self.ui = UInput({e.EV_KEY: list({k[2] for row in ROWS for k in row})},
                         name="deckboard")
        self.prev = {}
        self.visible = False
        self.shift_held = False     # L2
        self.shift_latch = False    # on-screen Shift
        self.caps = False
        self.sticky = set()
        self.aim = {"L": None, "R": None}       # key under thumb before pressing
        self.pressed = {"L": False, "R": False}

        s = cfg["scale"]
        self.kw = BASE_KEY * s
        self.kh = BASE_ROW * s
        self.W = int(self.kw * ROW_UNITS)
        self.H = int(self.kh * 5)
        # bold labels, like the waybar modules
        self.font = ("Noto Sans", max(10, int(17 * s)), "bold")
        self.font_small = ("Noto Sans", max(8, int(13 * s)), "bold")

        T = THEME
        b, th = 4, max(22, int(30 * s))          # 4px frame like the window borders
        self.ox, self.oy = b, th
        self.WW, self.WH = self.W + 2 * b, self.H + th + b

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)        # no focus steal, no title bar
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", cfg.get("opacity", 1.0))
        except tk.TclError:
            pass
        self.sw, self.sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = (self.sw - self.WW) // 2
        y = self.sh - self.WH - cfg["bottom_margin"]
        if cfg.get("position"):                       # remembered from D-pad moves
            x, y = cfg["position"]
        self.pos = [x, y]
        self.clamp_pos()
        self.move_held = 0.0                          # seconds a D-pad direction is held
        self.root.geometry(f"{self.WW}x{self.WH}+{self.pos[0]}+{self.pos[1]}")
        self.cv = tk.Canvas(self.root, width=self.WW, height=self.WH,
                            bg=T["body"], highlightthickness=0)
        self.cv.pack()

        # title strip: the window title bar's split gloss
        stops = T["title_gloss"]
        for yy in range(1, th):
            f = (yy - 1) / max(1, th - 2)
            c = stops[-1][1]
            for (o0, c0), (o1, c1) in zip(stops, stops[1:]):
                if o0 <= f < o1:
                    c = _mix(_hex(c0), _hex(c1), (f - o0) / (o1 - o0))
                    break
            self.cv.create_line(0, yy, self.WW, yy, fill=c)
        self.cv.create_line(0, 1, self.WW, 1, fill=T["title_highlight"])
        self.cv.create_line(0, th - 1, self.WW, th - 1, fill=T["frame_outer"])
        # frame: black outline + 1px inner line, as on the window borders
        self.cv.create_rectangle(0, 0, self.WW - 1, self.WH - 1, outline=T["frame_outer"])
        self.cv.create_line(1, th, 1, self.WH - 1, fill=T["frame_inner"])
        self.cv.create_line(self.WW - 2, th, self.WW - 2, self.WH - 1, fill=T["frame_inner"])
        self.cv.create_line(1, self.WH - 2, self.WW - 1, self.WH - 2, fill=T["frame_inner"])
        self.cv.create_text(b + 6, th / 2, text="Deckboard", anchor="w",
                            fill=T["title_text"], font=("Noto Sans", max(9, int(14 * s)), "bold"))
        self.cv.create_text(self.WW - b - 6, th / 2, anchor="e",
                            text="X hide   B ⌫   Y reset   R2 enter   L2 shift   D-pad move",
                            fill=T["help_text"], font=("Noto Sans", max(8, int(12 * s)), "bold"))

        # key images, cached per (w, h, state)
        self._img_cache = {}
        self.keys = []   # (x0, y0, x1, y1, keydef, img_id, text_id) in key-area coords
        self.key_state = {}
        gap = max(2, int(4 * s))               # Nemo-style spacing between buttons
        for r, row in enumerate(ROWS):
            xk = 0.0
            for kd in row:
                x0, y0 = xk, r * self.kh
                x1, y1 = xk + kd[3] * self.kw, (r + 1) * self.kh
                kw, kh = int(x1 - x0) - 2 * gap, int(y1 - y0) - 2 * gap
                iid = self.cv.create_image(self.ox + x0 + gap, self.oy + y0 + gap,
                                           anchor="nw", image=self.key_img(kw, kh, "normal"))
                font = self.font if len(kd[0]) <= 1 else self.font_small
                tid = self.cv.create_text(self.ox + (x0 + x1) / 2, self.oy + (y0 + y1) / 2,
                                          text=kd[0], fill=T["text"], font=font)
                self.keys.append((x0, y0, x1, y1, kd, iid, tid))
                self.key_state[iid] = ("normal", kd[0], (kw, kh))
                xk = x1
        # thumb cursors: big rings like Steam's keyboard (size relative to key height)
        dot = max(10, int(self.kh * cfg.get("dot_size", 0.45)))
        ring = max(2.0, dot / 9)
        centre = dot * cfg.get("dot_centre", 0.6)       # solid centre point diameter
        self.cursor_img = tk.PhotoImage(
            data=make_cursor_png(dot, ring, centre, T["cursor"],
                                 cfg.get("cursor_opacity", 0.55)), format="png")
        self.ldot = self.cv.create_image(0, 0, image=self.cursor_img, state="hidden")
        self.rdot = self.cv.create_image(0, 0, image=self.cursor_img, state="hidden")
        self.dot = dot
        self.root.after(8, self.tick)

    # -- helpers
    def clamp_pos(self):
        self.pos[0] = max(0, min(self.sw - self.WW, int(self.pos[0])))
        self.pos[1] = max(0, min(self.sh - self.WH, int(self.pos[1])))

    def reset_position(self):
        self.pos = [(self.sw - self.WW) // 2,
                    self.sh - self.WH - self.cfg["bottom_margin"]]
        self.clamp_pos()
        self.root.geometry(f"+{self.pos[0]}+{self.pos[1]}")
        save_config_value("position", None)
        log("position reset")

    def dpad_move(self, btn):
        dx = (btn["DRIGHT"] - btn["DLEFT"])
        dy = (btn["DDOWN"] - btn["DUP"])
        if dx or dy:
            self.move_held += 0.008
            speed = min(14, 2 + self.move_held * 16)   # px per tick, accelerates
            self.pos[0] += dx * speed
            self.pos[1] += dy * speed
            self.clamp_pos()
            self.root.geometry(f"+{self.pos[0]}+{self.pos[1]}")
        elif self.move_held:
            self.move_held = 0.0
            save_config_value("position", list(self.pos))

    def key_img(self, w, h, state):
        k = (w, h, state)
        if k not in self._img_cache:
            self._img_cache[k] = make_key_image(w, h, state)
        return self._img_cache[k]

    def pad_to_xy(self, px, py, left):
        ov = self.cfg["pad_overlap"]
        lo, hi = (0.0, 0.5 + ov) if left else (0.5 - ov, 1.0)
        fx = lo + (px + 32768) / 65535 * (hi - lo)
        fy = 1 - (py + 32768) / 65535
        return fx * self.W, fy * self.H

    def key_at(self, x, y):
        for k in self.keys:
            if k[0] <= x < k[2] and k[1] <= y < k[3]:
                return k
        return None

    def tap(self, code, mods=()):
        for m in mods:
            self.ui.write(e.EV_KEY, m, 1)
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.syn()
        self.ui.write(e.EV_KEY, code, 0)
        for m in reversed(mods):
            self.ui.write(e.EV_KEY, m, 0)
        self.ui.syn()

    def press_key(self, kd):
        code = kd[2]
        if code in SHIFTS:
            self.shift_latch = not self.shift_latch
        elif code == e.KEY_CAPSLOCK:
            self.caps = not self.caps
        elif code in STICKY:
            if code in self.sticky:
                self.sticky.discard(code)
                self.tap(code, sorted(self.sticky))
                self.sticky.clear()
            else:
                self.sticky.add(code)
        else:
            mods = sorted(self.sticky)
            letter = len(kd[0]) == 1 and kd[0].isalpha()
            shifted = self.shift_held or self.shift_latch
            if letter and self.caps:
                shifted = not shifted
            if shifted:
                mods.append(e.KEY_LEFTSHIFT)
            self.tap(code, mods)
            self.sticky.clear()
            self.shift_latch = False

    def show(self, on):
        log(f"show({on}) was_visible={self.visible}")
        self.visible = on
        if on:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            self.root.after(50, self.apply_opacity)
        else:
            self.root.withdraw()
            self.sticky.clear()
            self.shift_latch = False

    def apply_opacity(self):
        """Tk's -alpha doesn't reach override-redirect windows; set it directly."""
        val = str(int(max(0.1, min(1.0, self.cfg.get("opacity", 0.85))) * 0xFFFFFFFF))
        try:
            inner = self.root.wm_frame()
            tree = subprocess.run(["xwininfo", "-id", inner, "-children"], timeout=2,
                                  capture_output=True, text=True).stdout
            parent = next((ln.split()[3] for ln in tree.splitlines()
                           if "Parent window id" in ln), None)
            ids = {inner} | ({parent} if parent else set())
            for wid in ids:
                r = subprocess.run(["xprop", "-id", wid, "-f", "_NET_WM_WINDOW_OPACITY",
                                    "32c", "-set", "_NET_WM_WINDOW_OPACITY", val],
                                   check=False, timeout=2, capture_output=True, text=True)
                if r.returncode or r.stderr:
                    log(f"opacity on {wid}: rc={r.returncode} {r.stderr.strip()}")
        except (OSError, subprocess.SubprocessError, tk.TclError) as ex:
            log(f"opacity failed: {ex}")

    def combo_pressed(self, btn):
        """True on the tick a toggle combo becomes fully held."""
        if btn["STEAM"]:
            return False   # leave STEAM+X to Steam's own keyboard
        for combo in self.cfg["toggle_combos"]:
            if all(btn[b] for b in combo) and not all(self.prev.get(b, False) for b in combo):
                return True
        return False

    def edge(self, btn, name):
        was = self.prev.get(name, False)
        return btn[name] and not was

    # -- main loop
    def tick(self):
        now = time.monotonic()
        gap = now - getattr(self, "_last_tick", now)
        self._last_tick = now
        if gap > 0.05:
            log(f"slow tick: {gap*1000:.0f} ms")
        st = self.pad.get()
        if st:
            lx, ly, rx, ry, lp, rp, btn = st
            if btn["QAM"] and not self.prev.get("QAM", False):
                log("... pressed: launcher")
                try:
                    subprocess.Popen(LAUNCHER_CMD, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                except OSError as ex:
                    log(f"launcher failed: {ex}")
            if self.combo_pressed(btn):
                log("toggle pressed")
                self.show(not self.visible)
            if self.visible:
                self.dpad_move(btn)
                self.update_view(lx, ly, rx, ry, lp, rp, btn)
            self.prev = btn
        self.root.after(8, self.tick)

    def update_view(self, lx, ly, rx, ry, lp, rp, btn):
        self.shift_held = btn["L2"]
        shifted = self.shift_held or self.shift_latch
        hot = set()
        cfg = self.cfg
        for side, (px, py), touch, pres, dotid in (
                ("L", (lx, ly), "LPAD_TOUCH", lp, self.ldot),
                ("R", (rx, ry), "RPAD_TOUCH", rp, self.rdot)):
            if btn[touch]:
                x, y = self.pad_to_xy(px, py, side == "L")
                dx, dy = self.ox + x, self.oy + y
                self.cv.coords(dotid, dx, dy)
                self.cv.itemconfigure(dotid, state="normal")
                k = self.key_at(x, y)
                if pres < cfg["aim_threshold"] and not self.pressed[side]:
                    self.aim[side] = k
                if not self.pressed[side] and pres >= cfg["press_threshold"]:
                    self.pressed[side] = True
                    target = self.aim[side] or k
                    if target:
                        self.press_key(target[4])
                        self.haptics.pulse(side, cfg["haptic_press"])
                elif self.pressed[side] and pres < cfg["release_threshold"]:
                    self.pressed[side] = False
                shown = self.aim[side] if self.pressed[side] or pres >= cfg["aim_threshold"] else k
                if shown:
                    hot.add(shown[5])
                if k is not self.hover[side] and not self.pressed[side] \
                        and pres < cfg["aim_threshold"]:
                    if k is not None and self.hover[side] is not None:
                        self.haptics.pulse(side, cfg["haptic_hover"])
                    self.hover[side] = k
            else:
                self.cv.itemconfigure(dotid, state="hidden")
                self.pressed[side] = False
                self.aim[side] = None
                self.hover[side] = None
        if self.edge(btn, "B"):
            self.tap(e.KEY_BACKSPACE)
        if self.edge(btn, "Y"):            # Y = reset position
            self.reset_position()
            self.haptics.pulse("L", cfg["haptic_press"])
            self.haptics.pulse("R", cfg["haptic_press"])
        if self.edge(btn, "R2"):
            self.tap(e.KEY_ENTER)

        for (x0, y0, x1, y1, kd, iid, tid) in self.keys:
            code = kd[2]
            lit = (code in self.sticky or (code in SHIFTS and shifted)
                   or (code == e.KEY_CAPSLOCK and self.caps))
            state = "hover" if iid in hot else ("lit" if lit else "normal")
            letter = len(kd[0]) == 1 and kd[0].isalpha()
            up = shifted != (self.caps and letter)
            label = kd[1] if up else kd[0]
            old_state, old_label, size = self.key_state[iid]
            if state != old_state:
                self.cv.itemconfigure(iid, image=self.key_img(size[0], size[1], state))
                self.cv.itemconfigure(tid, fill=THEME["text_lit"] if state == "lit" else THEME["text"])
            if label != old_label:
                self.cv.itemconfigure(tid, text=label)
            self.key_state[iid] = (state, label, size)

    def run(self):
        self.root.mainloop()


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def save_config_value(key, value):
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data[key] = value
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    except (OSError, ValueError) as ex:
        print("config error, using defaults:", ex, file=sys.stderr)
    return cfg


def single_instance():
    """Exit if another copy is already running (lock held for process lifetime)."""
    lock_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "deckboard.lock")
    f = open(lock_path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("deckboard is already running")
    return f


def main():
    import signal
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)   # until the UI is ready
    _lock = single_instance()
    cfg = load_config()
    path = None
    for _ in range(120):          # at login Steam/controller may not be up yet
        path = find_hidraw()
        if path:
            break
        time.sleep(1)
    if not path:
        sys.exit("Steam Deck controller not found (is Steam running?)")
    pad = Pad()
    threading.Thread(target=pad.run, args=(path,), daemon=True).start()
    kb = Deckboard(cfg, pad, Haptics(path, cfg["haptics"]))
    if "--show" in sys.argv:
        kb.show(True)
    import signal
    signal.signal(signal.SIGUSR1, lambda *_: kb.root.after(0, lambda: kb.show(not kb.visible)))
    kb.run()


if __name__ == "__main__":
    main()
