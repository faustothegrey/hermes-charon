#!/usr/bin/env python3
"""netboard.py — mini network dashboard su framebuffer.
Scrive direttamente su /dev/fb0 via Pillow — nessun SDL, nessun TTY, nessun X11.
Include pixel orbit e screensaver anti burn-in."""

import os
import sys
import time
import subprocess
import numpy
import signal
import threading
import math
import fcntl
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import fritzbox_data
import backup_data
import netboard_ascii
import netboard_queue
import netboard_overlay
import hmp_health_data
import load_data
import ports_data

from PIL import Image, ImageDraw, ImageFont

# ─── Config ───────────────────────────────────────────────────────────────────
PEERS = [
    ("FRITZ!Box",  "192.168.178.1",  "Router"),
    ("peer70",     "192.168.178.70",  "Orchestratore (questo)"),
    ("peer84",     "192.168.178.84",  "N56VV"),
    ("peer105",    "192.168.178.105", "Fedora30"),
    ("peer106",    "192.168.178.106", "Fedora30 ARM"),
    ("peer128",    "192.168.178.112", "MacBook"),
    ("peer58",     "192.168.178.58",  "HMP peer"),
]
REFRESH_SEC     = 8
SCREENSAVER_MIN = 5
ORBIT_STEP_SEC  = 30
ORBIT_RADIUS    = 2
ASCII_INTERVAL  = 300   # 5 minuti tra messaggi ASCII
ASCII_DURATION  = 30    # durata messaggio in secondi

# ─── Colors (RGB) ─────────────────────────────────────────────────────────────
BG       = (15, 15, 25)
CARD_BG  = (25, 28, 40)
ACCENT   = (70, 130, 200)
GREEN    = (60, 200, 100)
RED      = (220, 60, 60)
YELLOW   = (220, 200, 40)
GREY     = (80, 80, 90)
WHITE    = (210, 210, 220)
DIM      = (120, 120, 140)
SAVER_BG = (0, 0, 0)
SAVER_CL = (30, 50, 70)

# ─── Framebuffer ──────────────────────────────────────────────────────────────
FB_DEV = "/dev/fb0"

def fb_open():
    try:
        return os.open(FB_DEV, os.O_RDWR)
    except OSError as e:
        print(f"ERRORE: non posso aprire {FB_DEV}: {e}", file=sys.stderr)
        sys.exit(1)

def fb_write_rgb565(fd, img):
    """Convert PIL Image (RGB, 800x480) to RGB565 and write to fb — vettorizzato con numpy."""
    w, h = img.size
    # Vettorizzazione completa con numpy: ~200x più veloce del loop Python
    arr = numpy.array(img, dtype=numpy.uint8)
    r = arr[:, :, 0].astype(numpy.uint16) >> 3
    g = arr[:, :, 1].astype(numpy.uint16) >> 2
    b = arr[:, :, 2].astype(numpy.uint16) >> 3
    rgb565 = (r << 11) | (g << 5) | b
    buf = rgb565.astype('<u2').tobytes()
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, buf)

# ─── Peer state ───────────────────────────────────────────────────────────────
class PeerStatus:
    def __init__(self, name, ip, desc):
        self.name = name
        self.ip = ip
        self.desc = desc
        self.online = None
        self.ms = None
        self.changed = time.monotonic()

statuses = [PeerStatus(*p) for p in PEERS]
lock = threading.Lock()

def ping(ip):
    try:
        start = time.monotonic()
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True, text=True, timeout=3
        )
        elapsed = (time.monotonic() - start) * 1000
        return r.returncode == 0, round(elapsed, 1)
    except Exception:
        return False, None

PING_POOL = ThreadPoolExecutor(max_workers=5)

def pinger_loop():
    futures = {}
    while True:
        # Lancia tutti i ping in parallelo
        for s in statuses:
            future = PING_POOL.submit(ping, s.ip)
            futures[future] = s
        for future in as_completed(futures, timeout=5):
            s = futures[future]
            try:
                ok, ms = future.result()
            except Exception:
                ok, ms = False, None
            with lock:
                old_online = s.online
                s.online = ok
                s.ms = ms
                if old_online != ok or (ok and ms is not None and
                    abs(ms - (s.ms or 0)) > 10):
                    s.changed = time.monotonic()
        futures.clear()
        time.sleep(REFRESH_SEC)

def any_peer_changed_since(t):
    with lock:
        return any(s.changed > t for s in statuses)


# ─── FritzBox poller (relaxed: every 60s) ──────────────────────────────────────
FB_REFRESH = 600  # 10 minuti — polling rilassato
fb_status = {"reachable": False, "error": "in attesa…"}
fb_lock = threading.Lock()

def fritzbox_poller():
    global fb_status
    while True:
        try:
            data = fritzbox_data.get_status()
            with fb_lock:
                fb_status = data
        except Exception:
            pass
        time.sleep(FB_REFRESH)

# ─── Icons ────────────────────────────────────────────────────────────────────
ICONS = {
    "FRITZ!Box":    "🌐",
    "peer70":       "🖥 ",
    "peer84":       "💻",
    "peer105":      "🐧",
    "peer106":      "🐧",
    "peer128":      "🍏",
    "peer58":       "⚙️ ",
}

def status_dot(online, ms):
    if online is None:
        return "⏳", GREY
    elif online:
        if ms and ms < 50:
            return "●", GREEN
        else:
            return "●", YELLOW
    else:
        return "✗", RED

# ─── Drawing ──────────────────────────────────────────────────────────────────
def draw_rounded_rect(draw, xy, color, r=6):
    x0, y0, x1, y1 = xy
    draw.rectangle((x0+r, y0, x1-r, y1), fill=color)
    draw.rectangle((x0, y0+r, x1, y1-r), fill=color)
    draw.ellipse((x0, y0, x0+2*r, y0+2*r), fill=color)
    draw.ellipse((x1-2*r, y0, x1, y0+2*r), fill=color)
    draw.ellipse((x0, y1-2*r, x0+2*r, y1), fill=color)
    draw.ellipse((x1-2*r, y1-2*r, x1, y1), fill=color)

def draw_dashboard(img, W, H, font_bold, font_small, font_tiny, ox, oy, fade=255):
    draw = ImageDraw.Draw(img)

    # Background
    bg = tuple(min(255, max(0, int(c * fade / 255))) for c in BG)
    draw.rectangle((0, 0, W, H), fill=bg)

    # Helper per scalare colore con fade
    def sc(c):
        return tuple(min(255, max(0, int(v * fade / 255))) for v in c)

    # Title
    title = "📡 NetBoard — Rete Locale"
    draw.text((15 + ox, 15 + oy), title, fill=sc(ACCENT), font=font_bold)

    now_str = time.strftime("%H:%M:%S")
    draw.text((W - 80 + ox, 18 + oy), now_str, fill=sc(DIM), font=font_small)

    draw.line((15, 42, W - 15, 42), fill=sc(ACCENT), width=1)

    # ─── HMP health status ─────────────────────────────────────────────────
    hmp_data = hmp_health_data.get_status()
    hmp_age = hmp_data.get("age_sec", 999) if hmp_data else None

    # Cards
    n_rows = (len(statuses) + 1) // 2  # numero di righe in griglia 2 colonne
    card_w = (W - 50) // 2
    card_h = 76
    gap = 10

    for i, s in enumerate(statuses):
        col = i % 2
        row = i // 2
        cx = 15 + col * (card_w + gap) + ox
        cy = 55 + row * (card_h + gap) + oy

        with lock:
            online = s.online
            ms = s.ms

        # Card background
        draw_rounded_rect(draw, (cx, cy, cx + card_w, cy + card_h), sc(CARD_BG), 8)

        dot_char, dot_color = status_dot(online, ms)
        dot_color_sc = sc(dot_color)

        draw.text((cx + 8, cy + 6), dot_char, fill=dot_color_sc, font=font_bold)

        icon = ICONS.get(s.name, " ")
        draw.text((cx + 28, cy + 6), f"{icon} {s.name}", fill=sc(WHITE), font=font_bold)

        # Status line
        if online is None:
            stxt = "⏳ scanning…"
        elif online:
            stxt = f"ping {ms}ms" if ms else "online"
        else:
            stxt = "❌ offline"
        draw.text((cx + 28, cy + 26), stxt, fill=dot_color_sc, font=font_small)

        # HMP status line
        hmp_str = hmp_health_data.hmp_status_for(s.name, hmp_data)
        if hmp_str:
            hmp_color = sc(GREEN) if "●" in hmp_str and "✗" not in hmp_str else sc(RED) if "✗" in hmp_str else sc(YELLOW)
            draw.text((cx + 28, cy + 46), hmp_str, fill=hmp_color, font=font_tiny)

        # IP
        draw.text((cx + card_w - 105, cy + 6), s.ip, fill=sc(DIM), font=font_tiny)

        # Description
        draw.text((cx + 28, cy + 60), s.desc, fill=sc(DIM), font=font_tiny)

    # Bottom bar
    hmp_time = ""
    if hmp_data and not hmp_data.get("stale"):
        iso = hmp_data.get("updated_at_iso", "")
        if iso:
            try:
                t = datetime.fromisoformat(iso)
                hmp_time = t.strftime("%H:%M")
            except Exception:
                pass
    elif hmp_data and hmp_data.get("stale"):
        hmp_time = "⚠ stale"
    bar = f"HMP {hmp_time}  •  agg. {REFRESH_SEC}s  • orbit {ORBIT_STEP_SEC}s  • ss {SCREENSAVER_MIN}m"
    draw.text((15 + ox, H - 20 + oy), bar, fill=sc(DIM), font=font_tiny)

    # ─── FritzBox + port forwarding row ────────────────────────────────────
    y_fb = 55 + n_rows * (card_h + gap) + 12
    with fb_lock:
        fb = fb_status
    fb_color = sc(ACCENT) if fb.get("reachable") else sc(RED)
    fb_line = fritzbox_data.format_short(fb) if fb.get("reachable") else f"🌐 FritzBox: {fb.get('error', '?')}"

    # Port forwarding summary (same line, right-aligned)
    ports = ports_data.get_ports()
    ports_line = ports_data.format_ports_line(ports, max_len=40)
    # Draw FritzBox left, ports right
    draw.text((15 + ox, y_fb + oy), fb_line, fill=fb_color, font=font_small)
    ports_color = sc(DIM)
    ports_w = draw.textlength(ports_line, font=font_tiny)
    draw.text((W - 15 - ports_w + ox, y_fb + oy + 2), ports_line, fill=ports_color, font=font_tiny)
    draw.line((15, y_fb - 4, W - 15, y_fb - 4), fill=sc(CARD_BG), width=1)

    # ─── Backup status row ──────────────────────────────────────────────────
    y_bu = y_fb + 28
    bu = backup_data.get_status()
    bu_line = backup_data.format_short(bu)
    bu_color = sc(GREEN) if (bu and bu.get("available") and not bu.get("stale") and any(b.get("esito") == "success" for b in bu.get("backups", []))) else sc(YELLOW)
    if bu and bu.get("stale"):
        bu_color = sc(RED)
    draw.text((15 + ox, y_bu + oy), bu_line, fill=bu_color, font=font_small)
    draw.line((15, y_bu - 4, W - 15, y_bu - 4), fill=sc(CARD_BG), width=1)

    # ─── System load row ────────────────────────────────────────────────────
    y_ld = y_bu + 26
    ld = load_data.get_status()
    ld_line = load_data.format_short(ld)
    draw.text((15 + ox, y_ld + oy), ld_line, fill=sc(DIM), font=font_tiny)

def draw_screensaver(img, W, H, ox, oy, ss_time):
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W, H), fill=(0, 0, 0))

    clock_str = time.strftime("%H:%M:%S")
    date_str  = time.strftime("%a %d %b %Y")

    # Lissajous motion
    cx = W // 2 + int(40 * math.sin(ss_time * 0.02))
    cy = H // 2 + int(20 * math.cos(ss_time * 0.015))

    draw.text((cx - 70 + ox, cy - 15 + oy), clock_str, fill=SAVER_CL, font=font_huge)
    draw.text((cx - 60 + ox, cy + 20 + oy), date_str, fill=SAVER_CL, font=font_small)

    info = f"netboard — in attesa…  {clock_str}"
    draw.text((W // 2 - 100 + ox, H - 30 + oy), info, fill=(20, 30, 40), font=font_tiny)

# ─── Font setup ───────────────────────────────────────────────────────────────
def load_font(name, size):
    """Try to load a TTF font, fallback to default."""
    paths = [
        f"/usr/share/fonts/truetype/{name}",
        f"/usr/share/fonts/truetype/dejavu/{name}",
        f"/usr/share/fonts/truetype/liberation/{name}",
        f"/usr/share/fonts/{name}",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    global font_huge, font_bold, font_small, font_tiny

    print("=== netboard: avvio su framebuffer direct ===")
    sys.stdout.flush()

    # Spegne il cursore lampeggiante del VT
    os.system("setterm -cursor off > /dev/tty1 2>/dev/null")
    try:
        with open("/sys/class/graphics/fbcon/cursor_blink", "w") as f:
            f.write("0")
    except Exception:
        pass
    # Riaccende il backlight (a volte consoleblank lo spegne)
    try:
        for d in os.listdir("/sys/class/backlight"):
            with open(f"/sys/class/backlight/{d}/bl_power", "w") as f:
                f.write("0")
    except Exception:
        pass
    # Sblocca DPMS del display DSI (vc4-kms-v3d spegne via DRM)
    try:
        fb_d = os.open("/dev/fb0", os.O_RDWR)
        fcntl.ioctl(fb_d, 0x4611, 0)  # FBIOBLANK, FB_BLANK_UNBLANK
        os.close(fb_d)
    except Exception:
        pass

    W, H = 800, 480

    # Fonts
    font_huge  = load_font("DejaVuSans-Bold.ttf", 64)
    font_bold  = load_font("DejaVuSans-Bold.ttf", 22)
    font_small = load_font("DejaVuSans.ttf", 18)
    font_tiny  = load_font("DejaVuSans.ttf", 14)

    # Open framebuffer
    fb_fd = fb_open()

    # Start pinger
    t = threading.Thread(target=pinger_loop, daemon=True)
    t.start()

    # Start FritzBox poller (relaxed)
    tf = threading.Thread(target=fritzbox_poller, daemon=True)
    tf.start()

    # State
    screensaver   = False
    last_change   = time.monotonic()
    orbit_idx     = 0
    last_orbit    = time.monotonic()
    orbit_offsets = [(0, 0), (ORBIT_RADIUS, 0), (ORBIT_RADIUS, ORBIT_RADIUS),
                     (0, ORBIT_RADIUS), (0, 0), (0, -ORBIT_RADIUS),
                     (-ORBIT_RADIUS, -ORBIT_RADIUS), (-ORBIT_RADIUS, 0)]
    fade_alpha    = 255
    ss_time       = 0.0

    # ASCII art state
    last_ascii    = time.monotonic()
    ascii_active  = False
    ascii_start   = 0.0

    # DPMS keepalive — ogni 120 secondi sblocca il display
    last_unblank  = time.monotonic()

    img           = Image.new("RGB", (W, H))

    running = True

    # Signal handler for clean exit
    def handle_signal(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Clear fb on exit
    def cleanup():
        os.lseek(fb_fd, 0, os.SEEK_SET)
        os.write(fb_fd, b'\x00' * W * H * 2)
        os.close(fb_fd)
        print("=== netboard: terminato ===")
        sys.stdout.flush()

    try:
        while running:
            try:
                now = time.monotonic()

                # DPMS keepalive — ogni 120 secondi sblocca il display
                if now - last_unblank > 120:
                    last_unblank = now
                    try:
                        fb_d = os.open("/dev/fb0", os.O_RDWR)
                        fcntl.ioctl(fb_d, 0x4611, 0)  # FBIOBLANK UNBLANK
                        os.close(fb_d)
                    except Exception:
                        pass

                # Check message queue (prioritario su tutto)
                active_msg = netboard_queue.cmd_active()
                if active_msg:
                    img = Image.new("RGB", (W, H))
                    netboard_overlay.draw_overlay(img, active_msg)
                    fb_write_rgb565(fb_fd, img)
                    time.sleep(1.0)
                    continue

                # Check screensaver
                if not screensaver:
                    with lock:
                        for s in statuses:
                            if s.changed > last_change:
                                last_change = s.changed
                    if now - last_change > SCREENSAVER_MIN * 60:
                        screensaver = True
                        ss_time = 0.0
                else:
                    if any_peer_changed_since(last_change):
                        screensaver = False
                        last_change = now
                        fade_alpha = 255
                        ss_time = 0.0

                # Pixel orbit
                if now - last_orbit > ORBIT_STEP_SEC:
                    orbit_idx = (orbit_idx + 1) % len(orbit_offsets)
                    last_orbit = now

                ox, oy = orbit_offsets[orbit_idx]

                # ASCII art display — solo durante screensaver
                if ascii_active:
                    if now - ascii_start >= ASCII_DURATION:
                        ascii_active = False
                        last_ascii = now
                    else:
                        img = Image.new("RGB", (W, H))
                        font_mono = netboard_ascii.load_font_mono()
                        netboard_ascii.draw_ascii_message(img, font_mono, font_small)
                        fb_write_rgb565(fb_fd, img)
                        time.sleep(0.5)
                        continue

                # Draw
                if screensaver:
                    if now - last_ascii >= ASCII_INTERVAL and not ascii_active:
                        ascii_active = True
                        ascii_start = now
                    if ascii_active:
                        img = Image.new("RGB", (W, H))
                        font_mono = netboard_ascii.load_font_mono()
                        netboard_ascii.draw_ascii_message(img, font_mono, font_small)
                        fb_write_rgb565(fb_fd, img)
                        time.sleep(0.5)
                    else:
                        ss_time += 1.0 / 4
                        img = Image.new("RGB", (W, H))
                        draw_screensaver(img, W, H, ox, oy, ss_time)
                        fb_write_rgb565(fb_fd, img)
                        time.sleep(0.25)
                    continue

                # Dashboard
                img = Image.new("RGB", (W, H))
                draw_dashboard(img, W, H, font_bold, font_small, font_tiny, ox, oy, fade_alpha)

                # Fade in
                if fade_alpha < 255:
                    fade_alpha = min(255, fade_alpha + 8)

                fb_write_rgb565(fb_fd, img)
                time.sleep(1.0)

            except Exception:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] ERRORE ciclo:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
                time.sleep(2)

    except Exception:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] ERRORE FATALE:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
    finally:
        cleanup()

if __name__ == "__main__":
    main()
