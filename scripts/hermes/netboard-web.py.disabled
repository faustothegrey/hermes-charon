#!/usr/bin/env python3
"""netboard-web.py — HTTP server per lo stato del cluster peer.
Serve una dashboard web su :8191 leggendo ~/.hermes/peer-network/status.json.
"""

import http.server
import os
import json
from datetime import datetime
from pathlib import Path

import fritzbox_data
import backup_data
from collections import deque
import sqlite3
import threading
import time as time_module  # avoid conflict with variable name

# Cache FritzBox data for 10 min (web endpoint, on-demand fetch)
_FB_CACHE = {"data": None, "at": 0}
_FB_TTL = 600

# ── HMP Live Pulse ─────────────────────────────────────────────────
# Background thread che polla il DB HMP ogni 3 secondi.
# Mantiene un buffer circolare degli ultimi 30 eventi.
_HMP_DB = Path.home() / ".hermes/data/hmp_gateway_plugin/messages.db"
_PULSE_BUFFER: deque = deque(maxlen=30)
_PULSE_LOCK = threading.Lock()
_PULSE_LAST_TS: float = 0.0

def _pulse_collector():
    global _PULSE_LAST_TS
    while True:
        try:
            if _HMP_DB.exists():
                conn = sqlite3.connect(str(_HMP_DB))
                cur = conn.execute(
                    "SELECT message_id, from_peer, to_peer, text, accepted_at "
                    "FROM hmp_gateway_messages "
                    "WHERE accepted_at > ? ORDER BY accepted_at ASC",
                    (_PULSE_LAST_TS,)
                )
                rows = cur.fetchall()
                conn.close()
                if rows:
                    with _PULSE_LOCK:
                        for row in rows:
                            _PULSE_BUFFER.append({
                                "mid": row[0],
                                "from": row[1],
                                "to": row[2],
                                "text": (row[3] or "")[:80],
                                "at": row[4],
                            })
                            if row[4] > _PULSE_LAST_TS:
                                _PULSE_LAST_TS = row[4]
        except Exception:
            pass
        time_module.sleep(3)

# Avvia collector in background
_pulse_thread = threading.Thread(target=_pulse_collector, daemon=True)
_pulse_thread.start()

STATUS_FILE = Path.home() / ".hermes/peer-network/status.json"
PORT = 8191

HTML = """\
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NetBoard — Stato Cluster</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box }}
  body {{
    font-family: -apple-system, 'Segoe UI', 'DejaVu Sans', system-ui, sans-serif;
    background: #0f1119; color: #d0d4dc; padding: 1.5rem; min-height: 100vh;
    display: flex; flex-direction: column; align-items: center;
  }}
  h1 {{ font-size: 1.6rem; margin-bottom: .25rem; letter-spacing: .5px }}
  .sub {{ color: #6b7280; font-size: .85rem; margin-bottom: 1.5rem }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px,1fr));
           gap: 1rem; width: 100%; max-width: 900px }}
  .card {{
    background: #171923; border-radius: 12px; padding: 1.25rem;
    border: 1px solid #252836; position: relative; overflow: hidden
  }}
  .card.online {{ border-color: #22c55e33 }}
  .card.offline {{ border-color: #ef444433 }}
  .card.self {{ border-color: #3b82f633 }}
  .pulse {{ grid-column: 1 / -1; max-height: 160px; overflow-y: auto }}
  .pulse .ev {{ display: flex; gap: .5rem; font-size: .8rem; padding: 3px 0;
                font-family: 'SF Mono','Cascadia Code', monospace; color: #9ca3af }}
  .pulse .ev .from {{ color: #60a5fa; min-width: 60px }}
  .pulse .ev .arrow {{ color: #4ade80 }}
  .pulse .ev .txt {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap }}
  .peer-name {{ font-size: 1.1rem; font-weight: 700; margin-bottom: .4rem }}
  .peer-name .tag {{
    font-size: .65rem; font-weight: 600; padding: 2px 8px; border-radius: 20px;
    vertical-align: middle; margin-left: 6px
  }}
  .tag.online {{ background: #22c55e22; color: #4ade80 }}
  .tag.offline {{ background: #ef444422; color: #f87171 }}
  .tag.self {{ background: #3b82f622; color: #60a5fa }}
  .ip {{ color: #6b7280; font-size: .8rem; font-family: 'SF Mono','Cascadia Code',monospace }}
  .desc {{ color: #9ca3af; font-size: .85rem; margin-top: .25rem }}
  .rtt {{ position: absolute; top: 1rem; right: 1rem; font-size: .8rem; font-weight: 600 }}
  .rtt.ok {{ color: #4ade80 }}
  .rtt.slow {{ color: #fbbf24 }}
  .rtt.none {{ color: #6b7280 }}
  .sys-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: .75rem;
    width: 100%; max-width: 900px; margin-top: 1rem
  }}
  .sys-card {{
    background: #171923; border-radius: 12px; padding: 1rem 1.25rem;
    border: 1px solid #252836
  }}
  .sys-card h3 {{ font-size: .75rem; color: #6b7280; text-transform: uppercase;
                  letter-spacing: 1px; margin-bottom: .5rem }}
  .sys-card .val {{ font-size: 1.3rem; font-weight: 700 }}
  .sys-card .val.hot {{ color: #f87171 }}
  .sys-card .val.warm {{ color: #fbbf24 }}
  .sys-card .val.cool {{ color: #4ade80 }}
  .footer {{ margin-top: 2rem; font-size: .75rem; color: #4b5563; text-align: center }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
             margin-right: 8px; vertical-align: middle }}
    .dot.online {{ background: #22c55e; box-shadow: 0 0 8px #22c55e44 }}
    .fritzbox-card {{
      background: #171923; border-radius: 12px; padding: 1rem 1.25rem;
      border: 1px solid #252836; width: 100%; max-width: 900px;
      margin-top: 1rem; display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: .75rem
    }}
    .fritzbox-card .stat {{ text-align: center }}
    .fritzbox-card .stat .label {{ font-size: .7rem; color: #6b7280;
      text-transform: uppercase; letter-spacing: .5px }}
    .fritzbox-card .stat .value {{ font-size: 1.2rem; font-weight: 700;
      margin-top: .25rem }}
    .fritzbox-card .stat .value.green {{ color: #4ade80 }}
    .fritzbox-card .stat .value.yellow {{ color: #fbbf24 }}
    .fritzbox-card .stat .value.blue {{ color: #60a5fa }}
  .dot.offline {{ background: #ef4444; box-shadow: 0 0 8px #ef444466 }}
  .dot.self {{ background: #3b82f6; box-shadow: 0 0 8px #3b82f666 }}
  .last-seen {{ font-size: .72rem; color: #4b5563; margin-top: .6rem;
                border-top: 1px solid #1f2937; padding-top: .5rem }}
</style>
</head>
<body>
<h1>📡 NetBoard</h1>
<p class="sub" id="ts">caricamento…</p>
<div class="grid" id="peers"></div>
<div class="sys-grid" id="sys"></div>
<div class="fritzbox-card" id="fb"></div>
<div class="backup-card" id="bk" style="margin-top:0.5rem;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));display:none"></div>
<div class="card pulse" id="pulse"><b>🔴 HMP Live Pulse</b><div id="pulse-list"></div></div>
<div class="card pulse" id="lan"><b>🌐 LAN (FritzBox)</b><div id="lan-list"></div></div>
<p class="footer" id="footer">peer70 · orchestratore</p>
<script>
async function load(){{
  try{{
    const r=await fetch('/api/status'); const d=await r.json();
    document.getElementById('ts').textContent='aggiornato: '+d.timestamp;
    let peers=''; for(const [name,p] of Object.entries(d.peers)){{
      const cls=p.status==='ONLINE'?(name==='peer70'?'self':'online'):'offline';
      const rttCls=p.status!=='ONLINE'?'none':(p.rtt_ms<50?'ok':'slow');
      const rttTxt=p.rtt_ms>0?p.rtt_ms+'ms':'—';
      peers+='<div class="card '+cls+'">';
      peers+='<div class="peer-name"><span class="dot '+cls+'"></span>'+name+'<span class="tag '+cls+'">'+p.status+'</span></div>';
      peers+='<div class="ip">'+p.ip+'</div>';
      peers+='<div class="desc">'+p.note+'</div>';
      peers+='<div class="rtt '+rttCls+'">'+rttTxt+'</div>';
      peers+='</div>';
    }}
    document.getElementById('peers').innerHTML=peers;
    const s=d.system; const temp=parseInt(s.temp_c);
    const tempCls=temp>=80?'hot':(temp>=65?'warm':'cool');
    document.getElementById('sys').innerHTML=`\`
          <div class="sys-card"><h3>🌡️ CPU</h3><div class="val ${tempCls}">${s.temp_c}°C</div></div>
          <div class="sys-card"><h3>📊 Load</h3><div class="val">${s.load}</div></div>
          <div class="sys-card"><h3>💾 RAM</h3><div class="val">${s.memory}</div></div>
          <div class="sys-card"><h3>⏱️ Peer</h3><div class="val">${Object.keys(d.peers).length}</div></div>
        `;
        // ── FritzBox ──
        try{
          const fr=await fetch('/api/fritzbox'); const f=await fr.json();
          if(f.reachable){
            const ds=f.dsl_down_kbps, us=f.dsl_up_kbps;
            document.getElementById('fb').innerHTML=
              '<div class="stat"><div class="label">DSL ↓</div><div class="value green">'+(ds/1000).toFixed(1)+'M</div></div>'+
              '<div class="stat"><div class="label">DSL ↑</div><div class="value yellow">'+(us/1000).toFixed(1)+'M</div></div>'+
              '<div class="stat"><div class="label">IPv4</div><div class="value blue">'+f.internet_ip+'</div></div>'+
              '<div class="stat"><div class="label">Provider</div><div class="value" style="font-size:.9rem">'+f.provider+'</div></div>'+
              '<div class="stat"><div class="label">Dispositivi</div><div class="value">'+f.device_count+' ('+f.device_online+' online)</div></div>'+
              '<div class="stat"><div class="label">WiFi</div><div class="value">'+(f.wifi_24?'2.4':'')+(f.wifi_24&&f.wifi_5?'+':'')+(f.wifi_5?'5':'')+' GHz</div></div>';
          } else {
            document.getElementById('fb').innerHTML='<div style="color:#ef4444;grid-column:1/-1;text-align:center">⚠ FritzBox: '+f.error+'</div>';
          }
        } catch(e){
          document.getElementById('fb').innerHTML='<div style="color:#6b7280;grid-column:1/-1;text-align:center">FritzBox: errore</div>';
        }
      }}catch(e){
          document.getElementById('peers').innerHTML='<p style="color:#ef4444">⚠ errore caricamento</p>';
        }}
        // ── Backup ──
        try{
          const br=await fetch('/api/backup'); const bd=await br.json();
          if(bd && bd.available && bd.backups && bd.backups.length>0){
            let html='';
            for(const b of bd.backups){
              const icon={'success':'✅','error':'❌','running':'🔄','offline':'⭕','never-ran':'⚪'}[b.esito]||'❓';
              const color=b.esito==='success'?'green':(b.esito==='error'?'#ef4444':'#fbbf24');
              html+='<div class="stat"><div class="label">'+icon+' '+b.label+'</div>'+
                    '<div class="value" style="color:'+color+';font-size:1rem">'+(b.esito||'?')+'</div>'+
                    '<div style="font-size:.7rem;color:#6b7280">'+(b.run_totali?b.run_totali+' run · ':'')+(b.ultimo_run?b.ultimo_run.slice(0,16):'')+'</div></div>';
            }
            if(bd.stale) html='<div style="color:#fbbf24;grid-column:1/-1;text-align:center">⚠ Dati backup non aggiornati (da >90min)</div>'+html;
            document.getElementById('bk').innerHTML=html;
          } else {
            document.getElementById('bk').innerHTML='<div style="color:#6b7280;grid-column:1/-1;text-align:center">💾 Nessun dato backup</div>';
          }
        } catch(e){
          document.getElementById('bk').innerHTML='<div style="color:#6b7280;grid-column:1/-1;text-align:center">💾 Backup: errore</div>';
        }
      }}
load(); setInterval(load, 10000);

// ── HMP Live Pulse ──
async function loadPulse(){
  try{
    const r=await fetch('/api/pulse'); const evts=await r.json();
    const list=document.getElementById('pulse-list');
    if(!evts||evts.length===0){list.innerHTML='<div style="color:#6b7280;padding:4px">In attesa di eventi HMP...</div>';return;}
    let html='';
    for(const e of evts.slice(-15).reverse()){
      const t=new Date(e.at*1000).toLocaleTimeString();
      const txt=(e.text||'').slice(0,60);
      html+='<div class="ev"><span class="from">'+e.from+'</span><span class="arrow">→</span><span class="from">'+e.to+'</span><span class="txt">'+txt+'</span></div>';
    }
    list.innerHTML=html;
  }catch(e){document.getElementById('pulse-list').innerHTML='<div style="color:#6b7280">pulse err</div>';}
}
loadPulse(); setInterval(loadPulse, 3000);

// ── LAN Monitor ──
async function loadLan(){
  try{
    const r=await fetch('/api/lan'); const devs=await r.json();
    if(!devs||devs.length===0){document.getElementById('lan-list').innerHTML='<div style="color:#6b7280">nessun dato</div>';return;}
    const on=devs.filter(d=>d.online), off=devs.filter(d=>!d.online);
    let html='<div style="font-size:.75rem;color:#6b7280;margin-bottom:4px">'+on.length+' online, '+off.length+' offline</div>';
    for(const d of devs.slice(0,20)){
      html+='<div class="ev"><span class="from">'+(d.online?'🟢':'🔴')+'</span><span class="txt">'+d.name+'</span></div>';
    }
    document.getElementById('lan-list').innerHTML=html;
  }catch(e){document.getElementById('lan-list').innerHTML='<div style="color:#6b7280">lan err</div>';}
}
loadLan(); setInterval(loadLan, 30000);
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._serve_json()
        elif self.path == "/api/fritzbox":
            self._serve_fritzbox_json()
        elif self.path == "/api/backup":
            self._serve_backup_json()
        elif self.path == "/api/pulse":
            self._serve_pulse()
        elif self.path == "/api/lan":
            self._serve_lan()
        elif self.path == "/api/upnp":
            self._serve_upnp()
        elif self.path == "/api/peer-health":
            self._serve_peer_health()
        elif self.path == "/":
            self._serve_html()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404")

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        # Inject current port into the HTML
        html = HTML.replace(":8191", f":{PORT}")
        # Fix: the CSS uses {{ }} but Python doesn't escape braces in raw strings
        # so we need to convert {{ -> { and }} -> } for valid CSS/HTML
        html = html.replace("{{", "{").replace("}}", "}")
        self.wfile.write(html.encode())

    def _serve_json(self):
        try:
            data = json.loads(STATUS_FILE.read_text())
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        except (FileNotFoundError, json.JSONDecodeError):
            body = json.dumps({"error": "status.json not available"}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_fritzbox_json(self):
        global _FB_CACHE
        now = time_module.time()
        if _FB_CACHE["data"] is None or now - _FB_CACHE["at"] > _FB_TTL:
            _FB_CACHE["data"] = fritzbox_data.get_status()
            _FB_CACHE["at"] = now
        data = _FB_CACHE["data"]
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_backup_json(self):
        data = backup_data.get_status()
        body = json.dumps(data).encode() if data else json.dumps({"available": False}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_pulse(self):
        with _PULSE_LOCK:
            events = list(_PULSE_BUFFER)
        body = json.dumps(events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_lan(self):
        data = fritzbox_data.get_lan_devices()
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_upnp(self):
        data = fritzbox_data.get_upnp_status()
        body = json.dumps(data).encode() if data else json.dumps({"error": "unreachable"}).encode()
        self.send_response(200 if data else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_peer_health(self):
        ph_file = Path.home() / ".hermes/peer-network/peer_health.json"
        if ph_file.exists():
            data = json.loads(ph_file.read_text())
        else:
            data = {"error": "not available"}
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Quiet logs — only print to stderr on error
        pass


def main():
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"netboard-web: http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nnetboard-web: arresto")
        server.server_close()


if __name__ == "__main__":
    main()
