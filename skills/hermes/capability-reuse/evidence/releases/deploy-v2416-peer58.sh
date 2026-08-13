#!/usr/bin/env bash
set -euo pipefail
mkdir -p /tmp/capreuse-v2416-deploy ~/.hermes/plugins ~/.hermes/data/reuse-observer
cd /tmp/capreuse-v2416-deploy
curl -fsS -o capability-reuse-v2.4.16.tar.gz http://192.168.178.106:18080/capability-reuse-v2.4.16.tar.gz
printf '%s  capability-reuse-v2.4.16.tar.gz\n' 2195dc748f5aab743125ec2658a3e66ef582e99d3959fd5c4a34b42fa6c4894b | sha256sum -c -
rm -rf capability-reuse
mkdir capability-reuse
tar -xzf capability-reuse-v2.4.16.tar.gz -C capability-reuse --strip-components=1
python3 - <<'PY2'
from pathlib import Path
import hashlib, json, shutil
cohort={
  "cohort_label":"v2.4.16_peer58_peer106",
  "deployment_id":"dep-v2416-peer58-peer106-clean-20260802T114235Z",
  "deployment_timestamp":"2026-08-02T11:42:35Z",
  "legacy_boundary":"events before this deployment_id are legacy and excluded from current-release metrics; peer58 v2.4.6 rows are legacy",
  "loaded_plugin_path":"/home/fausto/.hermes/plugins/capability-reuse",
  "plugin_version":"2.4.16",
  "protocol_version":"2.4.16",
  "event_schema_version":"1.2",
  "schema_version":"1.2",
  "plugin_artifact_hash":"sha256:f9b875a6396afdf1aece6fa69b1ef4b3c19e75a4253facecb979be789ce074f1",
  "plugin_tree_hash":"sha256:f9b875a6396afdf1aece6fa69b1ef4b3c19e75a4253facecb979be789ce074f1",
  "source_archive":"http://192.168.178.106:18080/capability-reuse-v2.4.16.tar.gz",
  "source_archive_sha256":"2195dc748f5aab743125ec2658a3e66ef582e99d3959fd5c4a34b42fa6c4894b",
  "scope":"peer58_peer106_only"}
src=Path('/tmp/capreuse-v2416-deploy/capability-reuse/plugin')
dst=Path.home()/'.hermes/plugins/capability-reuse'
if dst.exists(): shutil.rmtree(dst)
shutil.copytree(src,dst)
out=Path.home()/'.hermes/data/reuse-observer'; out.mkdir(parents=True,exist_ok=True)
(out/'cohort.json').write_text(json.dumps(cohort,indent=2)+'\n')
(out/'deployment.json').write_text(json.dumps(cohort,indent=2)+'\n')
files=[]
for p in sorted(dst.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc'):
        files.append(p)
h=hashlib.sha256()
for p in files:
    h.update(str(p.relative_to(dst)).encode()+b'\0'); h.update(p.read_bytes()+b'\0')
assert '2.4.16' in (dst/'plugin.yaml').read_text()
assert 'VERSION = "2.4.16"' in (dst/'protocol.py').read_text()
assert 'sha256:'+h.hexdigest()==cohort['plugin_tree_hash'], h.hexdigest()
print(json.dumps({'installed':str(dst),'files':len(files),'tree_hash':'sha256:'+h.hexdigest(),'cohort':cohort['deployment_id']}))
PY2
( sleep 3; /home/fausto/.local/bin/hermes gateway restart > /tmp/capreuse-v2416-restart.log 2>&1 || hermes gateway restart >> /tmp/capreuse-v2416-restart.log 2>&1 ) >/dev/null 2>&1 &
echo DEPLOYED_V2416_RESTART_SCHEDULED
