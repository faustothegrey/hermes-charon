"""netboard_ascii.py — Mini ASCII art per il display fisico NetBoard.
Mostra un messaggio simpatico per ~30s ogni 20 minuti. Basso impatto."""

import os
import random
import time
from PIL import Image, ImageDraw, ImageFont

# ─── Colori tenui per non affaticare ──────────────────────────────────────────
BG_ASCII   = (10, 10, 18)
TEXT_COLOR = (80, 180, 220)   # azzurrino soft
ACCENT     = (60, 130, 200)
DIM        = (100, 100, 120)

# ─── Messaggi ASCII art ───────────────────────────────────────────────────────
MESSAGES = [
    r"""
    +------------------------+
    |  I pinguini non        |
    |  sudano, loro          |
    |  raffreddano il        |
    |  server.               |
    +------------------------+
    """,
    r"""
       .--.
      |o_o |
      |:_/ |
     //   \ \
    (|     | )
    /'\_   _/`\
    \___)=(___/
    Ciao, sono il
    tuo server!
    """,
    r"""
    +------------------------+
    |  Tutto ok, capo!      |
    |  Nessun dramma        |
    |  in corso.            |
    +------------------------+
    """,
    r"""
    +------------------------+
    |  24/7 online senza    |
    |  caffe ne pausa       |
    |  pranzo.              |
    +------------------------+
    """,
    r"""
        ______
       /     /\
      /     /  \
     /_____/   /
     |    |   /
     |    |  /
     |____| /
     (____)/
    Il tuo RPi
    non dorme mai.
    """,
    r"""
    +------------------------+
    |  Notte tranquilla,    |
    |  rete sorvegliata.   |
    +------------------------+
    """,
    r"""
    +------------------------+
    |  Sono sveglio anche   |
    |  se tu dormi.         |
    |  (Non ho pigiama.)    |
    +------------------------+
    """,
    r"""
       ___
      / _ \
     | (_) |
      \___/
    Resisto anche
    allo spam.
    """,
    r"""
    +------------------------+
    |  Niente panico, e'   |
    |  solo la rete che    |
    |  fa il suo turno     |
    |  di notte.           |
    +------------------------+
    """,
    r"""
      .-""-.
     /      \
    |        |
    |        |
     \      /
      `-..-'
    Sto solo
    guardando
    i bit passare.
    """,
    r"""
    +------------------------+
    |  Segnale ricevuto.   |
    |  Nessuna emergenza.  |
    |  Tornate ai vostri   |
    |  affari.             |
    +------------------------+
    """,
    r"""
       /\_/\
      ( o.o )
       > ^ <
    Il gatto del
    server approva.
    """,
    r"""
    +------------------------+
    |  Tutti i sistemi     |
    |  vanno bene.         |
    |  Nessun allarme.     |
    +------------------------+
    """,
    r"""
    +------------------------+
    |  Ancora una tazza    |
    |  di bit. La rete     |
    |  non chiede mai      |
    |  pause.              |
    +------------------------+
    """,
    r"""
     +---+
     | o |
     | o |
     | o |
     +---+
    LED verde: tutto
    a posto da questa
    parte.
    """,
    r"""
    +------------------------+
    |  Firewall al suo     |
    |  posto. Nessun       |
    |  intruso. (Oggi.)   |
    +------------------------+
    """,
    r"""
      .--.
     /    \
    ## o  ##
    |      |
    \######/
    Pacchetti
    in transito.
    Nessun
    problema.
    """,
    r"""
    +------------------------+
    |  Tick tock, tick     |
    |  tock... Il cron     |
    |  job e' passato,    |
    |  tutto ok.           |
    +------------------------+
    """,
    r"""
    +------------------------+
    |  Tutti i colori      |
    |  della rete sono    |
    |  nel range giusto.  |
    |  Arcobaleno ok.     |
    +------------------------+
    """,
    r"""
        ___
     __/_  `.  .-""-.
    \_,` | \-'  /   )`-')
     "") `"`    \  (
    ___Y  ,    .'7 /|
    (_,)_/...-` (_/_/
    Nessuna tempesta
    in vista.
    """,
]


# ─── Carica font monospazio per ASCII art ──────────────────────────────────────
_font_mono = None

def load_font_mono():
    global _font_mono
    if _font_mono:
        return _font_mono
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            _font_mono = ImageFont.truetype(p, 16)
            return _font_mono
    _font_mono = ImageFont.load_default()
    return _font_mono


# ─── Draw ASCII art su immagine ───────────────────────────────────────────────
def draw_ascii_message(img, font_mono, font_small):
    """Disegna un messaggio ASCII art random sull'immagine."""
    W, H = img.size
    draw = ImageDraw.Draw(img)

    # Sfondo scuro
    draw.rectangle((0, 0, W, H), fill=BG_ASCII)

    # Messaggio random
    msg = random.choice(MESSAGES)

    # Divide in righe
    lines = msg.strip('\n').split('\n')
    line_height = 18  # font_mono size approssimato

    # Calcola centratura verticale
    total_h = len(lines) * line_height
    y_start = max(10, (H - total_h) // 2)

    # Disegna ogni riga
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            lw, _ = draw.textsize(line, font=font_mono)
        except AttributeError:
            lw = len(line) * 9
        x = max(10, (W - lw) // 2)
        draw.text((x, y_start + i * line_height), line, fill=TEXT_COLOR, font=font_mono)

    # Footer con timer
    footer = "netboard - ascii break"
    try:
        fw, _ = draw.textsize(footer, font=font_small)
    except AttributeError:
        fw = len(footer) * 8
    draw.text(((W - fw) // 2, H - 20), footer, fill=DIM, font=font_small)