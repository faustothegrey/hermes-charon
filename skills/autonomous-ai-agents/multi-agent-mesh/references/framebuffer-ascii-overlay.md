# Framebuffer ASCII Art Overlay (NetBoard Pattern)

When running a PIL-based framebuffer dashboard (e.g., NetBoard on `/dev/fb0`), you can layer secondary content — ASCII art messages, quotes, system status — that appears **only during screensaver/idle periods**, without disrupting the primary dashboard view.

## Architecture

```
netboard.py (main loop)
  ├── Normal state → draw_dashboard()       # peer cards, FritzBox, backups
  ├── Screensaver state → draw_screensaver() # clock, Lissajous orbit
  │     └── Every N min → netboard_ascii.draw_ascii_message()  # 2 sec burst
  └── Activity detected → back to dashboard
```

## Key Design Decisions

### 1. Gated by screensaver, not by timer
The ASCII art only fires when the screensaver is active (no peer state changes for N minutes). This guarantees the dashboard is never interrupted during active use:
```python
# In screensaver block:
if now - last_ascii >= ASCII_INTERVAL and not ascii_active:
    ascii_active = True
    ascii_start = now

if ascii_active:
    # Show ASCII art
    netboard_ascii.draw_ascii_message(...)
    if now - ascii_start >= ASCII_DURATION:
        ascii_active = False
        last_ascii = now
else:
    # Normal screensaver (clock)
    draw_screensaver(...)
```

### 2. Short burst duration (2 seconds)
Messages should flash briefly — long enough to be noticed, short enough not to feel disruptive. The user specified 2 seconds.

### 3. Random selection from a pool
Keep a pool of 15-20 messages. Vary shapes: boxes, animals, ASCII faces. Rotate randomly.

### 4. Pure ASCII only (no Unicode/emoji)
The framebuffer's Pillow version may not support Unicode rendering. Stick to `+-|/\` box drawing, basic ASCII punctuation, and Latin characters.

## NetBoard Integration Constants

```python
# In netboard.py config section:
ASCII_INTERVAL  = 300   # 5 min between messages
ASCII_DURATION  = 2     # display duration in seconds
```

## Module Structure (netboard_ascii.py)

```
netboard_ascii.py
├── MESSAGES[] — pool of ~20 ASCII art strings (raw triple-quoted)
├── load_font_mono() — loads DejaVuSansMono or LiberationMono
├── draw_ascii_message(img, font_mono, font_small) — renders to PIL Image
└── Footer line: "netboard - ascii break"
```

Font fallback path (for `load_font_mono()`):
1. `/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf`
2. `/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf`
3. `/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf`
4. Fallback: `ImageFont.load_default()`

## Pitfalls

- **Pillow version compatibility:** Debian 11 ships Pillow without `textbbox()`. Use `draw.textsize()` instead (with `AttributeError` fallback to `len(line) * 9` for width estimation).
- **UnicodeEncodeError in textsize:** Old Pillow's `ImageFont.getsize()` converts through `latin-1`. Emoji, fancy Unicode (•, ★, etc.) crash. Use only ASCII printable characters.
- **Framebuffer save/restore:** When testing ASCII art without restarting netboard, save the current framebuffer state to a bytearray and restore after the test. Otherwise you wipe the running dashboard.
- **Process management:** netboard.py runs as a long-lived background process. Kill by PID (`kill <pid>`), then restart. The web server (netboard-web.py) is a separate process and doesn't need restarting.

## Source File

The implementation lives at `~/.hermes/scripts/netboard_ascii.py` alongside `netboard.py`.
