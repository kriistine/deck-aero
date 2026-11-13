#!/bin/bash

# Get detailed temperature information
TEMP_DETAILS=$(for h in /sys/class/hwmon/hwmon*; do n=$(cat $h/name); for t in $h/temp*_input; do [ -f "$t" ] && echo "$n $(basename $t _input): $(( $(cat $t) / 1000 ))°C"; done; done)

# Show popup with temperature details
notify-send -t 5000 "Temperatures" "$TEMP_DETAILS"