// deck-aero: remove Plasma panels (waybar replaces them) and set the wallpaper.
// Run via org.kde.PlasmaShell.evaluateScript. WALLPAPER is substituted by install.sh.
panels().forEach(function (p) { p.remove(); });
desktops().forEach(function (d) {
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file://WALLPAPER");
    d.writeConfig("FillMode", 2); // scaled & cropped (= hyprpaper cover)
});
