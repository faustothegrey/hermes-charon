#!/usr/bin/env node
/**
 * fritzbox — CLI FritzBox API unificato (usa fetch nativo Node 22)
 *
 * Uso: node ~/.hermes/scripts/fritzbox.js <comando> [args]
 *
 * Rete: info, devices, wlan, channels
 * Tel:  calls [N], phonebook, active, tam, dial <numero>
 */

const https = require('https');
const { URL } = require('url');
const MODULES = '/home/fausto/.hermes/tests/fritzbox-test/node_modules';
const fritz = require(MODULES + '/fritzbox.js');

const FB = { username: 'fausto', password: 'ccll4372', server: '192.168.178.1' };

let gSid = null;
async function sid() {
  if (gSid) return gSid;
  gSid = await fritz.getSessionId({ ...FB, protocol: 'https', rejectUnauthorized: false });
  return gSid;
}

// POST a form to the FritzBox via https.request (handles self-signed certs)
function postForm(urlStr, formBody) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const body = new URLSearchParams(formBody).toString();
    const opts = {
      hostname: u.hostname, port: 443, path: u.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(body)
      },
      rejectUnauthorized: false
    };
    const req = https.request(opts, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(new Error('JSON parse failed: ' + data.substring(0,200))); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function post(page) {
  return postForm('https://192.168.178.1/data.lua', { page, sid: await sid() });
}

// Decode FritzBox airtime scan data
// Format: timestamp,slotCount,slotDuration,ch1:val1,ch2:val2,...
// Each ch:val where val how many slots that channel was seen busy
function decodeAirtime(data) {
  if (!data || typeof data !== 'string') return null;
  const parts = data.split(',');
  if (parts.length < 3) return null;
  const ts = parseInt(parts[0]), nslots = parseInt(parts[1]), dur = parseInt(parts[2]);
  const chs = {};
  for (let i = 3; i < parts.length; i++) {
    const [ch, val] = parts[i].split(':');
    const c = parseInt(ch), v = parseInt(val);
    if (v > 0) chs[c] = (chs[c] || 0) + v;
  }
  return { ts, nslots, dur, channels: chs };
}

const CH5_FREQ = {36:5180,40:5200,44:5220,48:5240,52:5260,56:5280,60:5300,64:5320,
  100:5500,104:5520,108:5540,112:5560,116:5580,120:5600,124:5620,128:5640,
  132:5660,136:5680,140:5700,149:5745,153:5765,157:5785,161:5805,165:5825};

// 2.4 GHz channel -> frequency
const CH24_FREQ = {1:2412,2:2417,3:2422,4:2427,5:2432,6:2437,7:2442,8:2447,9:2452,10:2457,11:2462,12:2467,13:2472};

const cmd = process.argv[2], arg = process.argv[3];

async function main() {
  switch (cmd) {

    case 'info': {
      const ver = await fritz.getVersion({ ...FB, protocol: 'https', rejectUnauthorized: false });
      const ov = await post('overview');
      const d = ov?.data || {};
      const dsl = d.dsl || {};
      const inet = d.internet?.connections?.[0] || {};
      const fw = d.fritzos || {};
      console.log(`Fritz!OS:    ${ver} (${fw.nspver})`);
      console.log(`Prodotto:    ${fw.Productname}`);
      console.log(`Data:        ${fw.boxDate}`);
      console.log(`Energia:     ${fw.energy} W`);
      console.log(`Agg.:        ${fw.isUpdateAvail ? 'DISPONIBILE' : 'Nessuno'}`);
      console.log('');
      console.log(`DSL:         ${dsl.txt}  ↓ ${dsl.down} kbps  ↑ ${dsl.up} kbps`);
      console.log('');
      console.log(`Internet:    ${inet.state}  (${inet.provider})`);
      console.log(`  IPv4:      ${inet.ipv4?.ip || '-'}`);
      console.log(`  DNS:       ${(inet.ipv4?.dns || []).map(d => d.ip).join(', ')}`);
      console.log(`  Vel reale: ${inet.downstream} / ${inet.upstream} kbps`);
      console.log(`  Vel nom:   ${inet.medium_downstream} / ${inet.medium_upstream} kbps`);
      console.log('');
      for (const f of (d.comfort?.func || [])) {
        console.log(`  ${f.linktxt}: ${f.details}`);
      }
      break;
    }

    case 'devices': {
      const ov = await post('overview');
      const devs = ov?.data?.net?.devices || [];
      console.log(`Dispositivi (${devs.length}):\n`);
      for (const d of devs) {
        const on = d.stateinfo?.active ? '●' : '○';
        const st = d.stateinfo?.online ? 'online' : d.stateinfo?.nexustrust ? 'trust' : d.stateinfo?.active ? 'att' : 'off';
        console.log(`${on} ${(d.name||'?').padEnd(30)} ${(d.type||'').padEnd(6)} ${(d.ip||'').padEnd(16)} ${st}`);
      }
      break;
    }

    case 'wlan': {
      const ov = await post('overview');
      for (const w of (ov?.data?.wlan || [])) {
        console.log(`${w.title}: ${w.led?.includes('green') ? 'attivo' : 'spento'} — ${w.txt}`);
      }
      break;
    }

    case 'channels': {
      const r = await post('chan');
      const g5 = r?.data?.['5ghz'];
      if (!g5?.airtimedata) { console.log('Dati canali non disponibili.'); break; }
      const dec = decodeAirtime(g5.airtimedata);
      if (!dec) { console.log('Decodifica fallita.'); break; }
      console.log(`Ultimo scan: ${g5.lastScantime}  |  Slot: ${dec.nslots} x ${dec.dur}ms\n`);
      const sorted = Object.entries(dec.channels).sort((a, b) => a[0] - b[0]);
      if (sorted.length === 0) { console.log('Nessun canale occupato.'); break; }
      console.log(`Canali 5 GHz occupati (${sorted.length}):`);
      for (const [ch, val] of sorted) {
        const freq = CH5_FREQ[ch] ? `${CH5_FREQ[ch]} MHz` : '';
        const pct = Math.round(val / dec.nslots * 100);
        const bar = '█'.repeat(Math.min(Math.round(pct/10), 10));
        console.log(`  CH${String(ch).padStart(3)} ${(freq||'').padEnd(10)} ${String(pct).padStart(3)}% ${bar}${pct > 0 ? ' occupato' : ''}`);
      }
      break;
    }

    case 'calls': {
      const limit = parseInt(arg) || 10;
      const all = await fritz.getCalls({ ...FB, protocol: 'https', rejectUnauthorized: false });
      if (all?.error) { console.log('Errore:', all.error.message); break; }
      const sel = all.slice(-limit).reverse();
      for (const c of sel) {
        const icon = {incoming:'<-',missed:'XX',unknown:'??',outgoing:'->'}[c.type]||'??';
        console.log(`${c.date} ${icon} ${c.type.padEnd(8)} ${(c.name||'?').padEnd(20)} ${c.number||''} [${c.duration}]`);
      }
      console.log(`\n${all.length} totale, ultime ${limit}`);
      break;
    }

    case 'phonebook': {
      const pb = await fritz.getPhonebook(0, { ...FB, protocol: 'https', rejectUnauthorized: false });
      if (pb?.error) { console.log('Errore:', pb.error.message); break; }
      for (const c of pb) {
        const n = c.numbers.map(n => `${n.number} (${n.type})`).join(', ');
        console.log(`${c.name}: ${n}`);
      }
      console.log(`\n${pb.length} contatti`);
      break;
    }

    case 'active': {
      const a = await fritz.getActiveCalls({ ...FB, protocol: 'https', rejectUnauthorized: false });
      console.log(a?.length ? JSON.stringify(a, null, 2) : 'Nessuna chiamata attiva');
      break;
    }

    case 'tam': {
      const m = await fritz.getTamMessages({ ...FB, protocol: 'https', rejectUnauthorized: false });
      if (m?.error) { console.log('Errore:', m.error.message); break; }
      for (const msg of (m||[])) {
        console.log(`${msg.date} | ${msg.name||'?'} | ${msg.number} | ${msg.duration}${msg.isNewMessage ? ' NUOVO' : ''}`);
      }
      if (!m?.length) console.log('Nessun messaggio');
      break;
    }

    case 'dial': {
      if (!arg) { console.log('Uso: fritzbox.js dial <numero>'); break; }
      const r = await fritz.dialNumber(arg, { ...FB, protocol: 'https', rejectUnauthorized: false });
      console.log(r?.error ? 'Errore: '+r.error.message : r.message);
      break;
    }

    default:
      console.log(`
Uso: node ~/.hermes/scripts/fritzbox.js <comando> [args]

Rete:
  info                Info sistema, DSL, Internet, comfort
  devices             Dispositivi di rete connessi
  wlan                Stato WiFi 2.4/5 GHz
  channels            Canali radio 5 GHz occupati

Telefono:
  calls [N]           Ultime N chiamate (default 10)
  phonebook           Rubrica
  active              Chiamate in corso
  tam                 Segreteria telefonica
  dial <numero>       Click-to-dial
`);
  }
}

main().catch(e => {
  console.error('Errore:', e.message);
  process.exit(1);
});