#!/usr/bin/env python3
"""
Mini registry-publish per peer remoti.
Scansiona skills/ + plugins/ e pubblica su peer70 via HMP.

Uso: python3 registry-publish.py
"""
import json, os, time, socket
from pathlib import Path
from urllib.request import Request, urlopen

HERMES=Path.home()/'.hermes'
PEER=os.environ.get('HMP_NODE_ID','peer70')
REG=70

def ip():
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 try:s.connect(('8.8.8.8',80));return s.getsockname()[0]
 except:return'0.0.0.0'
 finally:s.close()

skills=[]
sd=HERMES/'skills'
if sd.exists():
 for c in sorted(sd.iterdir()):
  if not c.is_dir():continue
  for s in sorted(c.iterdir()):
   m=s/'SKILL.md'
   if m.exists():
    v='0.0.0'
    for l in m.read_text().split('\n'):
     if l.startswith('version:'):v=l.split(':',1)[1].strip().strip("'\"")
    skills.append({'name':s.name,'version':v,'category':c.name})

plugins=[]
pd=HERMES/'plugins'
if pd.exists():
 for p in sorted(pd.iterdir()):
  if p.is_dir() and not p.name.startswith('__'):
   plugins.append({'name':p.name,'version':'1.0.0','enabled':True})

manifest={'peer':PEER,'host':ip(),'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'skills':skills,'plugins':plugins}
print(f'Skills: {len(skills)}, Plugins: {len(plugins)}', flush=True)

mid=f'reg_{PEER}_{int(time.time()*1000000)}'
payload={'hmp_version':'1.0','message_id':mid,'idempotency_key':mid,'from':PEER,'to':'peer70','type':'request','timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'timeout':30,'payload':{'text':'REGISTRY_PUBLISH '+json.dumps(manifest)}}
data=json.dumps(payload).encode()
req=Request(f'http://192.168.178.{REG}:18643/hmp/send',data=data,headers={'Content-Type':'application/json'})
with urlopen(req,timeout=10)as r:result=json.loads(r.read())
if result.get('accepted'):print(f'✅ Pubblicato su peer{REG}')
else:print(f'❌ {result.get("error","?")}')
