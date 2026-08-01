#!/usr/bin/env python3
from __future__ import annotations
import csv
import html
import json
from pathlib import Path
from datetime import datetime, timezone

HOME = Path.home()
BASE = HOME / '.hermes' / 'data' / 'reuse-aggregati'
OUT = BASE / 'dashboard.html'

def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def rows_from_csv(path, limit=25):
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))[:limit]

def esc(v):
    return html.escape(str(v if v is not None else ''))

def table(rows, cols):
    if not rows:
        return '<p class="muted">No rows.</p>'
    head = ''.join('<th>%s</th>' % esc(c) for c in cols)
    body = []
    for r in rows:
        body.append('<tr>' + ''.join('<td>%s</td>' % esc(r.get(c, '')) for c in cols) + '</tr>')
    return '<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (head, ''.join(body))

def metric(label, value):
    return '<div class="metric"><div class="label">%s</div><div class="value">%s</div></div>' % (esc(label), esc(value))

def render():
    latest = load_json(BASE / 'latest.json', {})
    rollups = load_json(BASE / 'rollups' / 'latest.json', {})
    qrows = rows_from_csv(BASE / 'review' / 'queue-latest.csv')
    r24 = rollups.get('24h', {}) if isinstance(rollups, dict) else {}
    r7d = rollups.get('7d', {}) if isinstance(rollups, dict) else {}
    t24 = r24.get('totals', {}) if isinstance(r24, dict) else {}
    t7d = r7d.get('totals', {}) if isinstance(r7d, dict) else {}
    prov24 = r24.get('retrieval', {}).get('by_provenance', {}) if isinstance(r24.get('retrieval'), dict) else {}
    cand24 = r24.get('retrieval', {}).get('review_candidates', []) if isinstance(r24.get('retrieval'), dict) else []
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    review_cols = ['timestamp','peer_id','provenance','capability','score','effect_class','label','review_notes','user_message_preview']
    cand_cols = ['candidate', 'count']
    html_doc = '''<!doctype html>
<html><head><meta charset="utf-8"><title>Capability Reuse Dashboard</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#101513;color:#e6f4ea;margin:24px}h1,h2{color:#9be28f}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.metric{background:#18231d;border:1px solid #2f4f38;border-radius:10px;padding:12px}.label{color:#a8b8ad;font-size:12px}.value{font-size:24px;font-weight:700}table{border-collapse:collapse;width:100%%;font-size:13px}th,td{border-bottom:1px solid #2a3a2f;padding:6px;text-align:left;vertical-align:top}th{color:#9be28f;background:#162019}.muted{color:#a8b8ad}.warn{color:#ffd166}.section{margin-top:28px}code{background:#18231d;padding:2px 4px;border-radius:4px}
</style></head><body>
<h1>Capability Reuse Human Dashboard</h1>
<p class="muted">Generated %s from <code>%s</code></p>
<div class="grid">%s</div>
<div class="section"><h2>24h provenance</h2><pre>%s</pre></div>
<div class="section"><h2>24h review candidates</h2>%s</div>
<div class="section"><h2>Human review queue</h2><p class="muted">Edit labels in CSV: <code>%s</code></p>%s</div>
<div class="section"><h2>Anomalies</h2><pre class="warn">%s</pre></div>
</body></html>''' % (
        esc(generated), esc(BASE),
        metric('latest peer', latest.get('peer_id','')) + metric('latest delta events', latest.get('events_processed',0)) + metric('24h retrievals', t24.get('retrieval_total',0)) + metric('7d retrievals', t7d.get('retrieval_total',0)) + metric('CSV review rows shown', len(qrows)) + metric('24h runs', t24.get('runs',0)),
        esc(json.dumps(prov24, ensure_ascii=False, indent=2, sort_keys=True)),
        table(cand24, cand_cols),
        esc(BASE / 'review' / 'queue-latest.csv'), table(qrows, review_cols),
        esc(json.dumps({'latest': latest.get('anomalies', []), '24h': r24.get('anomalies', {})}, ensure_ascii=False, indent=2, sort_keys=True))
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_doc, encoding='utf-8')
    return OUT

if __name__ == '__main__':
    print(render())
