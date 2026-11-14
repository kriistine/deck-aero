#!/usr/bin/env python3
"""deck-aero bridge: KWin window/desktop state -> waybar workspaces + taskbar.

KWin has no wlr-foreign-toplevel, so waybar's own taskbar/workspaces modules can't
work there. bridge.js (loaded into KWin) calls Update(json) on every change; we
render each window as a glossy button PNG matching the waybar taskbar CSS, write
one small file per waybar slot, and poke waybar with a realtime signal.
"""
import hashlib, json, math, os, signal, sys, tempfile, threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio, GLib, Gtk, Gdk, GdkPixbuf
import cairo

HOME = os.path.expanduser("~")
RUN = os.path.join(os.environ.get("XDG_RUNTIME_DIR", tempfile.gettempdir()), "deckaero")
CACHE = os.path.join(RUN, "icons")
SHARE = os.path.join(HOME, ".local/share/deckaero")
KWIN_JS = os.path.join(SHARE, "kwin/bridge.js")
SLOTS, WS_SLOTS = 12, 9
SIG_TASKBAR, SIG_WS = 8, 9
PX = 64          # rendered size; waybar scales to "size": 32 -> crisp on HiDPI too
def _kde_icon_theme():
    """The icon pack Plasma is using (kdeglobals [Icons] Theme), so the taskbar matches it."""
    try:
        kf = GLib.KeyFile()
        kf.load_from_file(os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "kdeglobals"),
                          GLib.KeyFileFlags.NONE)
        return kf.get_string("Icons", "Theme")
    except GLib.Error:
        return "breeze"


ICON_THEME = _kde_icon_theme()
PLUGIN = "deckaero-bridge"

# Host paths are visible under /run/host when we run inside distrobox.
HOSTS = ["", "/run/host"]
DATA_DIRS = [os.path.join(HOME, ".local/share"), os.path.join(HOME, ".local/share/flatpak/exports/share")]
for h in HOSTS:
    DATA_DIRS += [h + "/var/lib/flatpak/exports/share", h + "/usr/local/share", h + "/usr/share"]
DATA_DIRS = [d for d in dict.fromkeys(DATA_DIRS) if os.path.isdir(d)]

INTROSPECTION = """
<node><interface name="org.deckaero.Bridge">
  <method name="Update"><arg type="s" name="state" direction="in"/></method>
  <method name="Activate"><arg type="i" name="slot" direction="in"/></method>
  <method name="Close"><arg type="i" name="slot" direction="in"/></method>
  <method name="Desktop"><arg type="i" name="n" direction="in"/></method>
  <method name="Refresh"/>
</interface></node>
"""


def log(*a):
    print("[deckaero-bridge]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- icon lookup
theme = Gtk.IconTheme.new()
theme.set_search_path([os.path.join(HOME, ".local/share/icons"), os.path.join(HOME, ".icons")]
                      + [d + "/icons" for d in DATA_DIRS] + [d + "/pixmaps" for d in DATA_DIRS])
theme.set_custom_theme(ICON_THEME)

_desktop_index = None


def desktop_index():
    """Map lowercase keys (file id, StartupWMClass, Exec basename, Name) -> Icon."""
    global _desktop_index
    if _desktop_index is not None:
        return _desktop_index
    idx = {}
    for d in DATA_DIRS:
        app = os.path.join(d, "applications")
        if not os.path.isdir(app):
            continue
        for root, _, files in os.walk(app):
            for f in files:
                if not f.endswith(".desktop"):
                    continue
                kf = GLib.KeyFile()
                try:
                    kf.load_from_file(os.path.join(root, f), GLib.KeyFileFlags.NONE)
                    icon = kf.get_string("Desktop Entry", "Icon")
                except GLib.Error:
                    continue
                keys = [f[:-8]]
                for k in ("StartupWMClass", "Name", "Exec"):
                    try:
                        v = kf.get_string("Desktop Entry", k)
                    except GLib.Error:
                        continue
                    if k == "Exec":
                        parts = v.split()
                        v = os.path.basename(parts[0]) if parts else ""
                        # flatpak run ... <app.id>
                        for p in parts:
                            if p.count(".") >= 2 and not p.startswith("-"):
                                keys.append(p)
                    keys.append(v)
                for k in keys:
                    idx.setdefault(k.lower(), icon)
    _desktop_index = idx
    return idx


def icon_name_for(w):
    idx = desktop_index()
    cands = [w.get("desktopFile", ""), w.get("cls", ""), w.get("name", "")]
    for c in cands:
        if not c:
            continue
        c = c.lower()
        for k in (c, c.split(".")[-1], c.replace(" ", "-")):
            if k in idx:
                return idx[k]
    # icon named like the class itself (common for native apps)
    for c in cands:
        if c and theme.has_icon(c.lower()):
            return c.lower()
    return "application-x-executable"


def icon_file(name):
    if os.path.isabs(name) and os.path.exists(name):
        return name
    for n in (name, name.lower(), "application-x-executable", "applications-other"):
        info = theme.lookup_icon(n, 48, Gtk.IconLookupFlags.FORCE_SIZE)
        if info:
            return info.get_filename()
    return None


# ---------------------------------------------------------------- rendering
def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def render_button(path, state):
    """Mirror waybar's `#taskbar button` CSS: 4px radius, gloss top/bottom borders,
    soft shadow, cyan gradient when active."""
    key = hashlib.sha1(f"{path}|{state}".encode()).hexdigest()[:16]
    out = os.path.join(CACHE, key + ".png")
    if os.path.exists(out):
        return out
    s = PX / 32.0
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, PX, PX)
    cr = cairo.Context(surf)
    x, y, w, h, r = 2 * s, 1 * s, 28 * s, 30 * s, 4 * s
    # shadow: box-shadow 0 0 4px rgba(0,0,0,.2) (hover-ish .5 when active)
    for i in range(4, 0, -1):
        rrect(cr, x - i * s * .5, y - i * s * .5, w + i * s, h + i * s, r + i * s * .5)
        cr.set_source_rgba(0, 0, 0, (0.10 if state == "active" else 0.05))
        cr.fill()
    rrect(cr, x, y, w, h, r)
    if state == "active":
        g = cairo.LinearGradient(0, y, 0, y + h)
        g.add_color_stop_rgba(0, 0, 1, 1, 0.6)
        g.add_color_stop_rgba(1, 0, 100 / 255, 100 / 255, 0.1)
        cr.set_source(g)
    elif state == "attention":
        g = cairo.LinearGradient(0, y, 0, y + h)
        g.add_color_stop_rgba(0, 0.91, 0.54, 0.31, 0.6)
        g.add_color_stop_rgba(1, 0.4, 0.2, 0.1, 0.1)
        cr.set_source(g)
    else:
        cr.set_source_rgba(0, 0, 0, 0.0)
    cr.fill()
    # border-top rgba(255,255,255,.3), border-bottom rgba(255,255,255,.15)
    cr.set_line_width(1 * s)
    cr.set_source_rgba(1, 1, 1, 0.3)
    cr.move_to(x + r, y + .5 * s); cr.line_to(x + w - r, y + .5 * s); cr.stroke()
    cr.set_source_rgba(1, 1, 1, 0.15)
    cr.move_to(x + r, y + h - .5 * s); cr.line_to(x + w - r, y + h - .5 * s); cr.stroke()
    # icon (icon-size 28 in a 32 box -> 26 inside our 28x30 button)
    if path:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, int(24 * s), int(24 * s))
            ix = x + (w - pb.get_width()) / 2
            iy = y + (h - pb.get_height()) / 2
            Gdk.cairo_set_source_pixbuf(cr, pb, ix, iy)
            cr.paint_with_alpha(0.55 if state == "minimized" else 1.0)
        except GLib.Error as e:
            log("icon load failed", path, e)
    tmp = out + ".tmp"
    surf.write_to_png(tmp)
    os.replace(tmp, out)
    return out


# ---------------------------------------------------------------- state
state = {"current": 1, "count": 1, "windows": []}
order = {}       # window id -> first-seen sequence (stable taskbar order)
seq = [0]
slots = [None] * SLOTS
lock = threading.Lock()


def write(name, text):
    p = os.path.join(RUN, name)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, p)


def poke(sig):
    """Signal only the waybar started by our session script (pidfile)."""
    try:
        pid = int(open(os.path.join(RUN, "waybar.pid")).read().strip())
        with open(f"/proc/{pid}/comm") as f:
            if f.read().strip() == "waybar":
                os.kill(pid, signal.SIGRTMIN + sig)
    except (OSError, ValueError):
        pass


def publish():
    with lock:
        wins = state["windows"]
        for w in wins:
            if w["id"] not in order:
                seq[0] += 1
                order[w["id"]] = seq[0]
        live = {w["id"] for w in wins}
        for k in list(order):
            if k not in live:
                del order[k]
        wins = sorted(wins, key=lambda w: order[w["id"]])
        for i in range(SLOTS):
            if i < len(wins):
                w = wins[i]
                st = "active" if w["active"] else "attention" if w.get("attention") else \
                     "minimized" if w["minimized"] else "normal"
                png = render_button(icon_file(icon_name_for(w)), st)
                tip = (w["caption"] or w["cls"]).replace("\n", " ")
                write(f"t{i + 1}", f"{png}\n{tip}\n")
                slots[i] = w["id"]
            else:
                write(f"t{i + 1}", "")
                slots[i] = None
        cur = state["current"]
        used = set()
        for w in state["windows"]:
            used.update(w["desktops"])
        urgent = set()
        for w in state["windows"]:
            if w.get("attention"):
                urgent.update(w["desktops"])
        for n in range(1, WS_SLOTS + 1):
            if n <= state["count"] and (n == cur or n in used):
                cls = "active" if n == cur else "urgent" if n in urgent else ""
                write(f"ws{n}", json.dumps({"text": str(n), "class": cls}) + "\n")
            else:
                write(f"ws{n}", "")
    poke(SIG_TASKBAR)
    poke(SIG_WS)


# ---------------------------------------------------------------- KWin calls
bus = None
_oneshot = [0]


def kwin(method, *args, path="/Scripting", iface="org.kde.kwin.Scripting", sig=None):
    return bus.call_sync("org.kde.KWin", path, iface, method,
                         GLib.Variant(sig, args) if sig else None, None,
                         Gio.DBusCallFlags.NONE, 3000, None)


def run_script(path, plugin):
    try:
        kwin("unloadScript", plugin, sig="(s)")
    except GLib.Error:
        pass
    sid = kwin("loadScript", path, plugin, sig="(ss)").unpack()[0]
    if sid < 0:
        raise RuntimeError(f"KWin refused script {path}")
    kwin("run", path=f"/Scripting/Script{sid}", iface="org.kde.kwin.Script")
    return sid


def oneshot(js):
    """Run a snippet inside KWin (there is no D-Bus API to activate/close windows)."""
    _oneshot[0] += 1
    plugin = f"deckaero-cmd{_oneshot[0] % 4}"
    p = os.path.join(RUN, plugin + ".js")
    with open(p, "w") as f:
        f.write(js)
    try:
        run_script(p, plugin)
    except Exception as e:
        log("oneshot failed:", e)
    GLib.timeout_add(1500, lambda: (kwin_quiet_unload(plugin), False)[1])


def kwin_quiet_unload(plugin):
    try:
        kwin("unloadScript", plugin, sig="(s)")
    except GLib.Error:
        pass


FIND = "var w=null,l=workspace.windowList();for(var i=0;i<l.length;i++)if(l[i].internalId.toString()==%s)w=l[i];"


def on_call(conn, sender, path, iface, method, params, inv):
    try:
        if method == "Update":
            st = json.loads(params.unpack()[0])
            state.update(st)
            publish()
        elif method in ("Activate", "Close"):
            n = params.unpack()[0]
            wid = slots[n - 1] if 1 <= n <= SLOTS else None
            if wid:
                q = json.dumps(wid)
                if method == "Activate":
                    oneshot(FIND % q + "if(w){if(workspace.activeWindow===w&&!w.minimized)w.minimized=true;"
                            "else{w.minimized=false;workspace.activeWindow=w;}}")
                else:
                    oneshot(FIND % q + "if(w)w.closeWindow();")
        elif method == "Desktop":
            n = params.unpack()[0]
            oneshot(f"var d=workspace.desktops[{n - 1}];if(d)workspace.currentDesktop=d;")
        elif method == "Refresh":
            start_kwin_side()
        inv.return_value(None)
    except Exception as e:
        log("call failed", method, e)
        inv.return_dbus_error("org.deckaero.Error", str(e))


def start_kwin_side():
    try:
        run_script(KWIN_JS, PLUGIN)
        log("KWin bridge script loaded")
    except Exception as e:
        log("could not load KWin script (retrying):", e)
        GLib.timeout_add_seconds(2, lambda: (start_kwin_side(), False)[1])


def main():
    global bus
    os.makedirs(CACHE, exist_ok=True)
    publish()  # empty slots so waybar shows nothing instead of errors
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
    bus.register_object("/", node.interfaces[0], on_call, None, None)
    loop = GLib.MainLoop()

    def acquired(*_):
        log("bus name acquired")
        start_kwin_side()

    def lost(*_):
        log("bus name lost / taken, exiting")
        loop.quit()

    Gio.bus_own_name_on_connection(bus, "org.deckaero.Bridge", Gio.BusNameOwnerFlags.REPLACE
                                   | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT, acquired, lost)
    for s in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, s, lambda *_: (loop.quit(), False)[1])
    loop.run()
    kwin_quiet_unload(PLUGIN)


if __name__ == "__main__":
    main()
