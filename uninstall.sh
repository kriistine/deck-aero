#!/bin/bash
# Put the Deck's desktop back the way it was before deck-aero.
set -uo pipefail
DA="$HOME/.local/share/deckaero"; B="$DA/backup"
pkill -f "deckaero/bin/session"; distrobox enter deckaero -- pkill -x waybar 2>/dev/null; distrobox enter deckaero -- pkill -x swaync 2>/dev/null
rm -f "$HOME/.config/autostart/deckaero.desktop" "$HOME/.local/share/applications/deckaero-"*.desktop
# stop Plasma first so it can't write its panel-less layout over the restored one
if systemctl --user is-active -q plasma-plasmashell.service; then SYSD=1; systemctl --user stop plasma-plasmashell.service
else SYSD=0; kquitapp6 plasmashell 2>/dev/null || pkill -x plasmashell; sleep 2; fi
if [ -d "$B" ]; then
  for f in "$B"/*; do rm -rf "$HOME/.config/$(basename "$f")"; cp -a "$f" "$HOME/.config/"; done
fi
flatpak override --user --reset 2>/dev/null || true
distrobox rm --force deckaero 2>/dev/null || true
if [ $SYSD = 1 ]; then systemctl --user start plasma-plasmashell.service; else setsid plasmashell >/dev/null 2>&1 & fi
gdbus call --session -d org.kde.KWin -o /KWin -m org.kde.KWin.reconfigure >/dev/null 2>&1
echo "Restored. Log out and back in for colours/cursors to fully reset."
echo "(Themes/icons stay in ~/.themes and ~/.local/share/icons — harmless; delete if you want.)"
