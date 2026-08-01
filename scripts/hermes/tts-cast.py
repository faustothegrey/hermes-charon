#!/usr/bin/env python3
"""
tts-cast.py - Text-to-Speech + Google Cast per Google Home/Nest.

Questo script:
  1. Genera audio dal testo (OpenAI TTS o edge-tts)
  2. Avvia un server HTTP temporaneo sulla LAN
  3. Scopre il Google Home sulla rete e gli fa riprodurre l'audio

Uso:
  python3 tts-cast.py "Ciao, sono Hermes!"
  python3 tts-cast.py --engine openai "Test con OpenAI"
  python3 tts-cast.py --device "Cucina" "Solo su quel device"
  python3 tts-cast.py --device Pallino --quick "Veloce!"
  python3 tts-cast.py --list-devices

Dipendenze: pychromecast, edge-tts (o openai)
"""
import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# ── costanti ───────────────────────────────────────────────────────

CACHE_DIR = Path.home() / ".hermes" / "cache"
CACHE_FILE = CACHE_DIR / "tts-cast-device.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── dipendenze opzionali ──────────────────────────────────────────

try:
    import pychromecast
    HAS_CHROMECAST = True
except ImportError:
    HAS_CHROMECAST = False

try:
    from zeroconf import Zeroconf
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

HAS_EDGETTS = False
try:
    import edge_tts
    HAS_EDGETTS = True
except ImportError:
    pass

HAS_OPENAI = False
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    pass


# ── cache ──────────────────────────────────────────────────────────

def cache_save(cast_info):
    """Salva le info del device in cache per uso --quick."""
    data = {
        "friendly_name": cast_info.friendly_name,
        "host": cast_info.host,
        "port": cast_info.port,
        "uuid": str(cast_info.uuid),
        "model_name": cast_info.model_name,
        "cast_type": cast_info.cast_type,
        "manufacturer": cast_info.manufacturer,
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def cache_load():
    """Carica device dalla cache. None se assente."""
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ── utility ────────────────────────────────────────────────────────

def get_local_ip() -> str:
    """Scopre l'IP locale della macchina."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# ── TTS engines ────────────────────────────────────────────────────

def tts_edge(text: str, voice: str = "it-IT-ElsaNeural", rate: str = "+0%") -> str:
    """Genera audio con edge-tts (locale, gratuito)."""
    if not HAS_EDGETTS:
        print("ERRORE: edge-tts non installato. pip install edge-tts")
        sys.exit(1)
    out = tempfile.mktemp(suffix=".mp3")
    print(f"🎤 edge-tts: voice={voice}, rate={rate}")
    subprocess.run(
        [sys.executable, "-m", "edge_tts",
         "--voice", voice,
         "--rate", rate,
         "--text", text,
         "--write-media", out],
        check=True, capture_output=True, text=True
    )
    return out


def tts_openai(text: str, voice: str = "nova", api_key: str = "") -> str:
    """Genera audio con OpenAI TTS."""
    if not HAS_OPENAI:
        print("ERRORE: openai non installato. pip install openai")
        sys.exit(1)

    key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("VOICE_TOOLS_OPENAI_KEY")
    if not key:
        print("ERRORE: serve una OPENAI_API_KEY per usare --engine openai.")
        print("       export OPENAI_API_KEY=sk-... oppure passala con --api-key")
        sys.exit(1)

    client = OpenAI(api_key=key)
    out = tempfile.mktemp(suffix=".mp3")
    print(f"🎤 OpenAI TTS: voice={voice}")
    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
    )
    response.stream_to_file(out)
    return out


# ── HTTP server temporaneo ────────────────────────────────────────

def serve_file(file_path: str, port: int = 8888) -> tuple:
    """
    Avvia un server HTTP in background che serve un singolo file.
    Restituisce (url, server_instance, thread).
    """
    base_dir = os.path.dirname(os.path.abspath(file_path))
    filename = os.path.basename(file_path)

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=base_dir, **kwargs)
        def log_message(self, fmt, *args):
            pass

    server = http.server.HTTPServer(("0.0.0.0", port), _Handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    local_ip = get_local_ip()
    url = f"http://{local_ip}:{port}/{filename}"
    print(f"🌐 Server HTTP su http://{local_ip}:{port}/ → {filename}")
    return url, server, thread


# ── Cast ──────────────────────────────────────────────────────────

def _discover_device(device_name: str) -> "CastInfo":
    """
    Scopre i dispositivi e restituisce il CastInfo del primo match.
    Salva in cache.
    """
    from zeroconf import Zeroconf
    z = Zeroconf()
    try:
        casts, browser = pychromecast.discovery.discover_chromecasts(
            timeout=8, zeroconf_instance=z
        )
        matches = [c for c in casts
                   if device_name.lower() in c.friendly_name.lower()
                   or c.friendly_name.lower() in device_name.lower()]

        if not matches:
            print(f"❌ Nessun dispositivo trovato contenente '{device_name}'.")
            print("   Dispositivi trovati:")
            for c in casts:
                print(f"     - {c.friendly_name} ({c.host})")
            sys.exit(1)

        target = matches[0]
        cache_save(target)
        return target
    finally:
        browser.stop_discovery()
        z.close()


def _connect_and_play(cast_info, audio_url: str, content_type: str = "audio/mpeg"):
    """Connette a un CastInfo e avvia la riproduzione."""
    from zeroconf import Zeroconf
    z = Zeroconf()
    try:
        print(f"📡 Connessione a '{cast_info.friendly_name}' ({cast_info.host})...")
        cast = pychromecast.Chromecast(cast_info, timeout=15, zconf=z)
        cast.wait(timeout=15)
        print(f"✅ Connesso a '{cast_info.friendly_name}'")

        mc = cast.media_controller
        mc.play_media(audio_url, content_type)

        print("⏳ Avvio riproduzione...", end=" ", flush=True)
        start = time.time()
        while time.time() - start < 15:
            mc.block_until_active(timeout=5)
            state = mc.status.player_state if mc.status else "unknown"
            print(f"[{state}]", end=" ", flush=True)
            if state == "PLAYING":
                print()
                break
            time.sleep(1)

        print(f"🔊 Stato finale: {mc.status}")
        cast.disconnect()
        print(f"🔊 Riproduzione avviata su '{cast_info.friendly_name}'")
    finally:
        z.close()


def cast_audio(device_name: str, audio_url: str, content_type: str = "audio/mpeg", quick: bool = False):
    """
    Trova un Google Home per nome e gli fa riprodurre l'URL.
    Con quick=True salta la discovery e usa la cache.
    """
    if not HAS_CHROMECAST:
        print("ERRORE: pychromecast non installato.")
        sys.exit(1)

    if quick:
        cached = cache_load()
        if cached and (device_name.lower() in cached["friendly_name"].lower()
                       or cached["friendly_name"].lower() in device_name.lower()):
            print(f"⚡ Quick mode: {cached['friendly_name']} ({cached['host']})")
            from zeroconf import Zeroconf
            z = Zeroconf()
            try:
                # Discovery rapidissimo con known_hosts — aggira mDNS
                casts, browser = pychromecast.discovery.discover_chromecasts(
                    timeout=2, zeroconf_instance=z,
                    known_hosts=[cached["host"]]
                )
                browser.stop_discovery()

                if casts and (device_name.lower() in casts[0].friendly_name.lower()
                              or casts[0].friendly_name.lower() in device_name.lower()):
                    _connect_and_play(casts[0], audio_url, content_type)
                    return
                else:
                    print("   known_hosts fallito, faccio discovery completa...")
                    z2 = Zeroconf()
                    try:
                        casts2, browser2 = pychromecast.discovery.discover_chromecasts(
                            timeout=3, zeroconf_instance=z2
                        )
                        browser2.stop_discovery()
                        matches = [c for c in casts2
                                   if device_name.lower() in c.friendly_name.lower()
                                   or c.friendly_name.lower() in device_name.lower()]
                        if matches:
                            cache_save(matches[0])
                            _connect_and_play(matches[0], audio_url, content_type)
                            return
                    finally:
                        z2.close()
            finally:
                z.close()
        else:
            print("📡 Cache non trovata o device diverso, faccio discovery...")

    # Discovery normale
    cast_info = _discover_device(device_name)
    _connect_and_play(cast_info, audio_url, content_type)


# ── main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Testo → Google Home via TTS + Cast",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python3 tts-cast.py "Ciao mondo"
  python3 tts-cast.py --engine openai "Test vocale"
  python3 tts-cast.py --device Cucina "Accendi le luci"
  python3 tts-cast.py --device Pallino --quick "Veloce!"
  python3 tts-cast.py --list-devices
        """
    )
    parser.add_argument("text", nargs="?", help="Testo da pronunciare")
    parser.add_argument("--engine", choices=["edge", "openai"], default="edge",
                        help="Motore TTS (default: edge)")
    parser.add_argument("--voice", default="",
                        help="Voce TTS (edge: it-IT-ElsaNeural, openai: nova/alloy/echo/shimmer)")
    parser.add_argument("--device", default=None,
                        help="Nome del Google Home (default: primo trovato)")
    parser.add_argument("--port", type=int, default=8888,
                        help="Porta per server HTTP locale (default: 8888)")
    parser.add_argument("--api-key", default="",
                        help="API key OpenAI (altrimenti da env OPENAI_API_KEY)")
    parser.add_argument("--list-devices", action="store_true",
                        help="Scopri e elenca i dispositivi Google Cast sulla rete")
    parser.add_argument("--rate", default="+0%",
                        help="Velocità voce edge-tts (default: +0%)")
    parser.add_argument("--quick", action="store_true",
                        help="Salta discovery, riusa device in cache (più veloce)")

    args = parser.parse_args()

    # ── list devices ───────────────────────────────────────────
    if args.list_devices:
        from zeroconf import Zeroconf
        z = Zeroconf()
        casts, browser = pychromecast.discovery.discover_chromecasts(
            timeout=6, zeroconf_instance=z
        )
        browser.stop_discovery()
        z.close()
        if not casts:
            print("❌ Nessun dispositivo Google Cast trovato sulla rete.")
            sys.exit(1)
        print(f"\n📡 Trovati {len(casts)} dispositivi:")
        for i, c in enumerate(casts, 1):
            print(f"  {i}. {c.friendly_name}  ({c.host}:{c.port})")
        print()
        return

    if not args.text:
        parser.print_help()
        sys.exit(1)

    # ── genera audio ───────────────────────────────────────────
    if args.engine == "edge":
        voice = args.voice or "it-IT-ElsaNeural"
        audio_file = tts_edge(args.text, voice=voice, rate=args.rate)
    else:
        voice = args.voice or "nova"
        audio_file = tts_openai(args.text, voice=voice, api_key=args.api_key)

    print(f"💾 Audio salvato: {audio_file} ({os.path.getsize(audio_file)} bytes)")

    # ── server HTTP ────────────────────────────────────────────
    url, server, srv_thread = serve_file(audio_file, port=args.port)

    try:
        # ── cast ────────────────────────────────────────────────
        if args.device:
            cast_audio(args.device, url, quick=args.quick)
        else:
            # Primo dispositivo trovato
            from zeroconf import Zeroconf
            z = Zeroconf()
            casts, browser = pychromecast.discovery.discover_chromecasts(
                timeout=8, zeroconf_instance=z
            )
            browser.stop_discovery()
            z.close()
            if not casts:
                print("❌ Nessun Google Home trovato. Verifica che sia nella stessa rete.")
                sys.exit(1)
            print(f"📡 Connessione a '{casts[0].friendly_name}' ({casts[0].host})...")
            z2 = Zeroconf()
            try:
                cast = pychromecast.Chromecast(casts[0], timeout=15, zconf=z2)
                cast.wait(timeout=15)
                print(f"✅ Connesso a '{casts[0].friendly_name}'")
                mc = cast.media_controller
                mc.play_media(url, "audio/mpeg")
                time.sleep(3)
                cast.disconnect()
                print(f"🔊 Riproduzione avviata su '{casts[0].friendly_name}'")
            finally:
                z2.close()

        # Aspetta che la riproduzione finisca
        print("⏳ Attesa riproduzione...")
        time.sleep(5)

    finally:
        server.shutdown()
        try:
            os.unlink(audio_file)
        except OSError:
            pass
        print("🧹 Pulito. Bye!")


if __name__ == "__main__":
    main()
