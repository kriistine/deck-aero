// deck-aero KWin bridge: pushes window/desktop state to org.deckaero.Bridge on every change.
// Loaded at runtime by bridge.py through org.kde.kwin.Scripting (no kwinrc changes needed).

function listed(w) {
    return w.normalWindow && !w.skipTaskbar && !w.deleted;
}

function desktopIndex(d) {
    var ds = workspace.desktops;
    for (var i = 0; i < ds.length; i++) if (ds[i] === d || ds[i].id === d.id) return i + 1;
    return 0;
}

function snapshot() {
    var wins = [];
    var all = workspace.windowList();
    var act = workspace.activeWindow;
    for (var i = 0; i < all.length; i++) {
        var w = all[i];
        if (!listed(w)) continue;
        var desks = [];
        if (w.onAllDesktops) desks = [0];
        else for (var j = 0; j < w.desktops.length; j++) desks.push(desktopIndex(w.desktops[j]));
        wins.push({
            id: w.internalId.toString(),
            caption: w.caption,
            cls: String(w.resourceClass),
            name: String(w.resourceName),
            desktopFile: w.desktopFileName || "",
            pid: w.pid,
            active: act === w,
            minimized: w.minimized,
            attention: w.demandsAttention,
            desktops: desks
        });
    }
    return JSON.stringify({
        current: desktopIndex(workspace.currentDesktop),
        count: workspace.desktops.length,
        windows: wins
    });
}

function push() {
    callDBus("org.deckaero.Bridge", "/", "org.deckaero.Bridge", "Update", snapshot());
}

function hook(w) {
    w.captionChanged.connect(push);
    w.minimizedChanged.connect(push);
    w.desktopsChanged.connect(push);
    w.demandsAttentionChanged.connect(push);
}

workspace.windowList().forEach(hook);
workspace.windowAdded.connect(function (w) { hook(w); push(); });
workspace.windowRemoved.connect(push);
workspace.windowActivated.connect(push);
workspace.currentDesktopChanged.connect(push);
workspace.desktopsChanged.connect(push);
push();
