"""
netboard_overlay.py — Disegna messaggi della coda prioritaria su NetBoard.
"""
import os, sys, textwrap
from PIL import Image, ImageDraw, ImageFont

# Colori
BG       = (15, 15, 25)
TEXT_CL  = (200, 220, 255)
SUB_CL   = (130, 180, 220)
ACCENT   = (70, 130, 200)
SHADOW   = (40, 80, 120)
DIM      = (100, 100, 120)

MARGIN = 40  # px di margine orizzontale

_font_big   = None
_font_sub   = None
_font_small = None

def _load_fonts():
    global _font_big, _font_sub, _font_small
    if _font_big:
        return
    try:
        _font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
    except:
        _font_big = ImageFont.load_default()
    try:
        _font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        _font_sub = ImageFont.load_default()
    try:
        _font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        _font_small = ImageFont.load_default()

def _get_textsize(draw, text, font):
    """Compat: usa textlength/textbbox (PIL 10+) o textsize (PIL <10)."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)

def _wrap_lines(draw, text, font, max_width):
    """Dividi il testo in righe che stanno in max_width px."""
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        tw, _ = _get_textsize(draw, test, font)
        if tw <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines if lines else [text]

def draw_overlay(img, msg):
    """Disegna un messaggio della coda sull'immagine del framebuffer.
    msg: dict con text, subtitle (opzionale), priority.
    Supporta automaticamente testo su più righe.
    """
    _load_fonts()
    W, H = img.size
    draw = ImageDraw.Draw(img)
    max_w = W - MARGIN * 2
    
    # Sfondo sfumato
    for y in range(H):
        r = int(15 + (y / H) * 20)
        g = int(15 + (y / H) * 10)
        b = int(25 + (y / H) * 30)
        draw.line((0, y, W, y), fill=(r, g, b))
    
    # Banda decorativa in alto
    draw.rectangle((0, 0, W, 4), fill=ACCENT)
    
    # Testo principale — wrap automatico su più righe
    text = msg.get("text", "")
    subtitle = msg.get("subtitle")
    
    # Calcola quante righe servono
    lines = _wrap_lines(draw, text, _font_big, max_w)
    n_lines = len(lines)
    
    # Altezza totale del blocco testo
    _, lh = _get_textsize(draw, "Ag", _font_big)
    line_gap = 8
    text_block_h = n_lines * lh + (n_lines - 1) * line_gap
    
    if subtitle:
        _, sh = _get_textsize(draw, subtitle, _font_sub)
        total_h = text_block_h + 15 + sh
    else:
        total_h = text_block_h
    
    y_start = (H - total_h) // 2 - 10
    
    # Disegna ogni riga con ombra
    for i, line in enumerate(lines):
        tw, th = _get_textsize(draw, line, _font_big)
        x_text = (W - tw) // 2
        y_text = y_start + i * (lh + line_gap)
        draw.text((x_text + 3, y_text + 3), line, fill=SHADOW, font=_font_big)
        draw.text((x_text, y_text), line, fill=TEXT_CL, font=_font_big)
    
    if subtitle:
        y_sub = y_start + text_block_h + 15
        sw, _ = _get_textsize(draw, subtitle, _font_sub)
        x_sub = (W - sw) // 2
        # Ombra subtitle
        draw.text((x_sub + 2, y_sub + 2), subtitle, fill=SHADOW, font=_font_sub)
        draw.text((x_sub, y_sub), subtitle, fill=SUB_CL, font=_font_sub)
    
    # Footer timer e priorità
    footer = f"priorità {msg.get('priority', '?')}  ·  netboard overlay"
    fw, _ = _get_textsize(draw, footer, _font_small)
    draw.text(((W - fw) // 2, H - 25), footer, fill=DIM, font=_font_small)
