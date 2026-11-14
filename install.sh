#!/bin/bash
# deck-aero installer — run on the Steam Deck in Desktop Mode (Konsole), as the normal user.
#   ./install.sh            theme + bar + notifications + launcher + apps
#   ./install.sh --spotify  also patch Spotify (flatpak) with Spicetify DarkAero
# Everything lives in $HOME, so SteamOS updates don't touch it. Undo with ./uninstall.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DA="$HOME/.local/share/deckaero"
BACKUP="$DA/backup"
WANT_SPOTIFY=0
for a in "$@"; do [ "$a" = --spotify ] && WANT_SPOTIFY=1; done

c_ok()   { printf '\e[1;36m==>\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m!!\e[0m  %s\n' "$*"; }
need()   { command -v "$1" >/dev/null 2>&1; }

kw()  { kwriteconfig6 "$@" 2>/dev/null || kwriteconfig5 "$@"; }
dbus_call() { gdbus call --session "$@" >/dev/null; }

# ---------------------------------------------------------------- preflight
[ "$(id -u)" -ne 0 ] || { echo "Run as your normal user (deck), not root."; exit 1; }
if ! pgrep -x plasmashell >/dev/null; then
  c_warn "Run this from Desktop Mode (Plasma). Plasma isn't running here."
  exit 1
fi
if [ "${XDG_SESSION_TYPE:-}" != wayland ] || [ -z "${WAYLAND_DISPLAY:-}" ]; then
  c_warn "Desktop Mode is running on X11 here. waybar/swaync need the Wayland desktop."
  echo "    Log out of this session to the Wayland one: in Konsole run"
  echo "      steamos-session-select plasma-wayland"
  echo "    (or plasma-wayland-persistent if your SteamOS version only has that one),"
  echo "    then run ./install.sh again from that session."
  exit 1
fi
need distrobox || {
  c_warn "distrobox not found (SteamOS 3.5+ ships it). Installing it into ~/.local ..."
  curl -fsSL https://raw.githubusercontent.com/89luca89/distrobox/main/install | sh -s -- --prefix "$HOME/.local"
  export PATH="$HOME/.local/bin:$PATH"
}

# ---------------------------------------------------------------- backup (first run only)
if [ ! -d "$BACKUP" ]; then
  c_ok "Backing up current desktop config to $BACKUP"
  mkdir -p "$BACKUP"
  for f in kdeglobals kwinrc kcminputrc plasmarc plasmashellrc plasma-org.kde.plasma.desktop-appletsrc \
           gtk-3.0 gtk-4.0 waybar swaync wofi kitty; do
    [ -e "$HOME/.config/$f" ] && cp -a "$HOME/.config/$f" "$BACKUP/" || true
  done
fi

# ---------------------------------------------------------------- files
c_ok "Copying theme files into your home folder"
cp -a "$REPO/files/." "$HOME/"
chmod +x "$DA/bin/"* "$HOME/.config/waybar/scripts/"*.sh

# ---------------------------------------------------------------- container with waybar & friends
PKGS="waybar swaync wofi kitty nemo xarchiver pavucontrol libnotify python python-gobject python-cairo gtk3 librsvg noto-fonts otf-font-awesome"
if ! distrobox list 2>/dev/null | grep -qw deckaero; then
  c_ok "Creating the 'deckaero' container (Arch Linux) — first time takes a few minutes"
  distrobox create --yes --name deckaero --image docker.io/library/archlinux:latest
fi
c_ok "Installing waybar, swaync, wofi, kitty, nemo inside the container"
distrobox enter deckaero -- sudo pacman -Syu --noconfirm --needed $PKGS
c_ok "Adding kitty and Nemo to the app menu"
distrobox enter deckaero -- distrobox-export --app kitty >/dev/null || true
distrobox enter deckaero -- distrobox-export --app nemo  >/dev/null || true

# ---------------------------------------------------------------- KDE look
c_ok "Applying colours, icons, cursors, window borders"
plasma-apply-colorscheme DarkAeroDeck >/dev/null || c_warn "colour scheme not applied"
kw --file kdeglobals --group KDE   --key widgetStyle Fusion
# Icons: keep whatever pack the Deck already uses;
# GTK apps, the launcher and the taskbar follow it.
# (if an older deck-aero run changed it, use the pack from before that run)
KG="$HOME/.config/kdeglobals"; [ -f "$BACKUP/kdeglobals" ] && KG="$BACKUP/kdeglobals"
ICONS="$( (kreadconfig6 --file "$KG" --group Icons --key Theme || kreadconfig5 --file "$KG" --group Icons --key Theme) 2>/dev/null)"
[ "$ICONS" = crystal-remix-icon-theme-diinki-version ] && ICONS=""
[ -n "$ICONS" ] || ICONS=breeze
kw --file kdeglobals --group Icons --key Theme "$ICONS"
echo "    keeping your icon pack: $ICONS"
plasma-apply-cursortheme WoWCursors >/dev/null 2>&1 || kw --file kcminputrc --group Mouse --key cursorTheme WoWCursors
kw --file kcminputrc --group Mouse --key cursorSize 24
kw --file kdeglobals --group General --key font "Noto Sans,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1"
kw --file kwinrc --group org.kde.kdecoration2 --key library org.kde.kwin.aurorae.v2
kw --file kwinrc --group org.kde.kdecoration2 --key theme __aurorae__svg__Classic-Black
kw --file kwinrc --group Plugins --key blurEnabled true
kw --file kwinrc --group Desktops --key Number 4
kw --file kwinrc --group Desktops --key Rows 1
dbus_call -d org.kde.KWin -o /KWin -m org.kde.KWin.reconfigure || true

c_ok "GTK theme (diinki-aero) for normal + Flatpak apps"
if need gsettings; then
  gsettings set org.gnome.desktop.interface gtk-theme diinki-aero || true
  gsettings set org.gnome.desktop.interface icon-theme "$ICONS" || true
  gsettings set org.gnome.desktop.interface cursor-theme WoWCursors || true
  gsettings set org.gnome.desktop.interface color-scheme prefer-dark || true
fi
sed -i "s/^gtk-icon-theme-name=.*/gtk-icon-theme-name=$ICONS/" "$HOME/.config/gtk-3.0/settings.ini" "$HOME/.config/gtk-4.0/settings.ini" 2>/dev/null || true
sed -i 's/^gtk-theme-name=.*/gtk-theme-name=diinki-aero/' "$HOME/.config/gtk-3.0/settings.ini" "$HOME/.config/gtk-4.0/settings.ini" 2>/dev/null || true
grep -q '^gtk-theme-name' "$HOME/.config/gtk-3.0/settings.ini" || sed -i '/^\[Settings\]/a gtk-theme-name=diinki-aero' "$HOME/.config/gtk-3.0/settings.ini"
if need flatpak; then
  flatpak override --user --filesystem=xdg-config/gtk-3.0:ro --filesystem=xdg-config/gtk-4.0:ro \
    --filesystem="$HOME/.themes:ro" --filesystem="$HOME/.local/share/icons:ro" \
    --env=GTK_THEME=diinki-aero --env=XCURSOR_THEME=WoWCursors --env=XCURSOR_PATH="$HOME/.local/share/icons:/usr/share/icons" || true
fi

# ---------------------------------------------------------------- Plasma: drop panel, set wallpaper
c_ok "Removing Plasma's panel (waybar replaces it) and setting the wallpaper"
JS="$(sed "s|WALLPAPER|$DA/wallpaper.jpg|" "$DA/plasma/apply.js")"
dbus_call -d org.kde.plasmashell -o /PlasmaShell -m org.kde.PlasmaShell.evaluateScript "$JS"
# Plasma only lets go of notifications (so swaync can have them) after a restart without the panel.
c_ok "Restarting Plasma"
if systemctl --user is-active -q plasma-plasmashell.service; then
  systemctl --user restart plasma-plasmashell.service
else
  (kquitapp6 plasmashell || pkill -x plasmashell) >/dev/null 2>&1 || true
  sleep 2; setsid plasmashell >/dev/null 2>&1 &
fi
sleep 4

# ---------------------------------------------------------------- apps
c_ok "Firefox userChrome + prefs"
ff_done=0
for base in "$HOME/.var/app/org.mozilla.firefox/.mozilla/firefox" "$HOME/.var/app/org.mozilla.firefox/config/mozilla/firefox" "$HOME/.mozilla/firefox"; do
  [ -f "$base/profiles.ini" ] || continue
  while IFS= read -r rel; do
    p="$base/$rel"; [ -d "$p" ] || p="$rel"; [ -d "$p" ] || continue
    mkdir -p "$p/chrome"; cp "$REPO/apps/firefox/userChrome.css" "$p/chrome/userChrome.css"
    touch "$p/user.js"
    while IFS= read -r pref; do grep -qF "$pref" "$p/user.js" || echo "$pref" >> "$p/user.js"; done < "$REPO/apps/firefox/user.js"
    ff_done=1; echo "    -> $p"
  done < <(sed -n 's/^Path=//p' "$base/profiles.ini")
done
[ $ff_done = 1 ] || c_warn "No Firefox profile yet — open Firefox once, then re-run ./install.sh"

c_ok "Discord Dark Aero CSS"
dc_done=0
for s in "$HOME/.var/app/dev.vencord.Vesktop/config/vesktop/settings" "$HOME/.var/app/com.discordapp.Discord/config/Vencord/settings" "$HOME/.config/vesktop/settings" "$HOME/.config/Vencord/settings"; do
  [ -d "$(dirname "$s")" ] || continue
  mkdir -p "$s"; cp "$REPO/apps/discord/quickCss.css" "$s/quickCss.css"
  python3 - "$s/settings.json" <<'PY'
import json, os, sys
p = sys.argv[1]
try: d = json.load(open(p))
except Exception: d = {}
d["useQuickCss"] = True
json.dump(d, open(p, "w"), indent=4)
PY
  dc_done=1; echo "    -> $s"
done
[ $dc_done = 1 ] || c_warn "No Vesktop/Vencord found — install Vesktop from Discover, open it once, re-run ./install.sh"

if [ $WANT_SPOTIFY = 1 ]; then
  c_ok "Spicetify DarkAero for Spotify (flatpak)"
  SP=/var/lib/flatpak/app/com.spotify.Client/x86_64/stable/active/files/extra/share/spotify
  if [ -d "$SP" ]; then
    need spicetify || [ -x "$HOME/.spicetify/spicetify" ] || curl -fsSL https://raw.githubusercontent.com/spicetify/cli/main/install.sh | sh
    export PATH="$HOME/.spicetify:$PATH"
    mkdir -p "$HOME/.config/spicetify/Themes"; cp -a "$REPO/apps/spicetify/DarkAero" "$HOME/.config/spicetify/Themes/"
    c_warn "Spicetify needs write access to Spotify's files — sudo will ask for your Deck password:"
    sudo chmod a+wr "$SP" && sudo chmod a+wr -R "$SP/Apps"
    spicetify config spotify_path "$SP" prefs_path "$HOME/.var/app/com.spotify.Client/config/spotify/prefs" \
      current_theme DarkAero color_scheme DarkAero >/dev/null
    spicetify backup apply || c_warn "Open Spotify once, log in, close it, then: spicetify backup apply"
  else
    c_warn "Spotify flatpak not installed — skipping"
  fi
fi

# ---------------------------------------------------------------- go
c_ok "Starting the bar"
setsid "$DA/bin/start" >/dev/null 2>&1 &
cat <<EOF

  Done. The bar starts automatically every time you enter Desktop Mode.
  * Steam button on the bar = app launcher (wofi). Right-click it / click the clock = notifications.
  * 'Return to Gaming Mode' is in the launcher.
  * Stylus site themes: install Stylus in Firefox, then open the files in
      $REPO/apps/firefox/stylus/
  * Instagram Discord-style chat: install Tampermonkey, then open
      $REPO/apps/firefox/userscripts/instagram-discord-chat.user.js
  * Undo everything: $REPO/uninstall.sh
EOF
