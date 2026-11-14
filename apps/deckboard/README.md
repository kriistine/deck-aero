# Deckboard

A smaller on-screen keyboard for Steam Deck Desktop Mode, styled to match the deck-aero taskbar. It replaces Steam's oversized desktop keyboard.

It's one Python file (`deckboard.py`) that:

- reads the Deck's controller directly (hidraw), so it works alongside Steam Input
- types through a virtual keyboard (evdev / uinput), into whatever window has focus
- draws itself with Tk as an always-on-top window that never steals focus
- gives trackpad haptics on key hover and press, using the same motors Steam does

Everything it needs ships with SteamOS (Python 3, Tk, python-evdev, and access to the controller and uinput), so there's nothing to install.

## Controls

| Input | Action |
|---|---|
| **X** | show / hide the keyboard |
| left / right **trackpad** | each pad moves its own cursor over its half of the keyboard |
| trackpad **press** | type the key under that pad's cursor |
| **B** | backspace |
| **R2** | enter |
| **L2** (hold) | shift |
| **Y** | reset position to bottom centre |
| **D-pad** | move the keyboard (position is remembered) |
| **⋯** (Quick Access button) | open / close the wofi app launcher, even while the keyboard is hidden |

Ctrl, Alt and Super are sticky: tap one, then the next key, to send the combo (for example Super then Left). Tap a lit modifier again to send it on its own.

## Install

```sh
mkdir -p ~/deckboard ~/.config/autostart
cp deckboard.py ~/deckboard/
cp deckboard.json ~/.config/deckboard.json        # optional: tuned settings below
cp deckboard.desktop ~/.config/autostart/         # start with the KDE desktop
python3 ~/deckboard/deckboard.py &                # or just log out and back in
```

Only one copy runs at a time (it holds a lock in `$XDG_RUNTIME_DIR/deckboard.lock`).

The **⋯** button runs `~/.local/share/deckaero/bin/launcher-host`, which comes with the rest of deck-aero. Without it, the button does nothing.

## Settings (`~/.config/deckboard.json`)

Any key left out uses the default in `deckboard.py`. The included file holds the values tuned on my Deck:

| Key | Meaning |
|---|---|
| `scale` | size; 1.0 is about the size of Steam's keyboard (tuned: 0.6) |
| `opacity` | 0.1 to 1.0 (tuned: 1.0, fully opaque) |
| `press_threshold` / `release_threshold` | trackpad pressure (0 to 32767) that counts as a press / release |
| `aim_threshold` | the key is chosen where your thumb was before pressure passed this |
| `haptic_press` / `haptic_hover` | `[on µs, off µs, repeats]` for the buzz on press / hover |
| `pad_overlap` | how far each pad's half reaches past the middle |
| `bottom_margin` | gap between the keyboard and the bottom of the screen |
| `position` | saved automatically when you move it with the D-pad |

## Look

The colours live in the `THEME` dict near the top of `deckboard.py`: an Aero glass frame (grey gloss on the top half, black below), glossy grey keys, and the taskbar's cyan (`#20d0fc`) for hover and press.

## Notes

- The Deck's trackpads have no click switch; a "click" is pad pressure crossing `press_threshold`.
- Tk's `-alpha` doesn't reach this kind of window, so opacity is set on the X window with `xprop`.
- The mouse still moves while the keyboard is open, because Steam moves the cursor itself. To stop that, set up a Steam Input action layer.
