#!/bin/bash
# CPU temperature for waybar (Deck/AMD APU). No lm_sensors/bc needed: reads hwmon directly.
TEMP=""
for h in /sys/class/hwmon/hwmon*; do
  n=$(cat "$h/name" 2>/dev/null)
  case "$n" in k10temp|zenpower) TEMP=$(cat "$h/temp1_input"); break;; esac
done
if [ -z "$TEMP" ]; then
  for h in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$h/name" 2>/dev/null)" = amdgpu ] && TEMP=$(cat "$h/temp1_input") && break
  done
fi
[ -z "$TEMP" ] && TEMP=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
T=$((TEMP / 100)); TXT="$((T / 10)).$((T % 10))"
if   [ "$T" -ge 800 ]; then ICON=""; CLASS="critical"
elif [ "$T" -ge 700 ]; then ICON=""; CLASS="warning"
else ICON=""; CLASS="normal"; fi
echo "{\"text\": \"$ICON $TXT°C\", \"class\": \"$CLASS\"}"
