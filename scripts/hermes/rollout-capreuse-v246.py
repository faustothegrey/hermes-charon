#!/usr/bin/env python3
"""capability-reuse v2.4.6 rollout: backup, install, verify, smoke."""
import json, os, sys, time, zipfile, shutil, hashlib, subprocess
from pathlib import Path

ARTIFACT = "/tmp/capability-reuse-v2.4.6.zip"
EXPECTED_SHA = "95191c79eb6818af4b51f2c0ed2676967e382010b9e5547a89cc26cdfd63fdf4"
REPORT = Path.home() / ".hermes" / "capreuse-v246-rollout.json"
ZIP_DIR = "capability-reuse"  # top dir inside zip

results = {}

def log(msg):
    print(msg, flush=True)
    return msg

def sha256_of(p):
    with open(p, 'rb') as f: return hashlib.sha256(f.read()).hexdigest()

# 0. Verify artifact
if not os.path.exists(ARTIFACT):
    log("FATAL: artifact missing"); sys.exit(1)
art_sha = sha256_of(ARTIFACT)
sha_ok = art_sha == EXPECTED_SHA
log(f"ARTIFACT sha256={'OK' if sha_ok else 'MISMATCH'} ({art_sha[:16]}...)")

# ── local peer70 ──
def deploy_local():
    SKILL = Path.home() / ".hermes" / "skills" / "hermes" / "capability-reuse"
    PLUGIN = Path.home() / ".hermes" / "plugins" / "capability-reuse"
    BK = Path.home() / ".hermes" / "backups" / f"capreuse-2.4.6-backup-{int(time.time())}"
    # backup
    if SKILL.exists(): shutil.copytree(SKILL, BK / "skill")
    if PLUGIN.exists(): shutil.copytree(PLUGIN, BK / "plugin")
    log(f"peer70 backup -> {BK}")
    # install
    with zipfile.ZipFile(ARTIFACT) as z: z.extractall("/tmp/capreuse-246-extract")
    src = Path("/tmp/capreuse-246-extract") / ZIP_DIR
    if SKILL.exists(): shutil.rmtree(SKILL)
    shutil.copytree(src, SKILL)
    shutil.rmtree(PLUGIN / "__pycache__", ignore_errors=True)
    psrc = src / "plugin"
    for fn in os.listdir(psrc):
        if fn == "__pycache__": continue
        sf = psrc / fn
        if sf.is_file(): shutil.copy2(sf, PLUGIN / fn)
    (PLUGIN / "plugin.yaml").touch()
    # verify
    v = verify_versions(SKILL / "SKILL.md", PLUGIN / "plugin.yaml", PLUGIN / "protocol.py", PLUGIN / "v244_metadata.py")
    smoke = smoke_test(PLUGIN)
    results["peer70"] = {"status": "OK" if v["all_246"] and smoke["ok"] else "PARTIAL",
                          "versions": v, "smoke": smoke["msg"]}
    log(f"peer70: {results['peer70']['status']} versions={v['all_246']} smoke={smoke['msg']}")

def verify_versions(skill_md, plugin_yaml, protocol_py, v244_py):
    def getv(p, pat):
        try:
            for line in p.read_text().splitlines():
                if pat in line and "=" in line: return line.split("=",1)[1].strip().strip('"').strip("'")
                if pat in line and ":" in line: return line.split(":",1)[1].strip()
        except Exception: return None
        return None
    sv = None
    try:
        for line in skill_md.read_text().splitlines():
            if line.startswith("version:"): sv = line.split(":",1)[1].strip(); break
    except Exception: pass
    pv = None
    try:
        for line in plugin_yaml.read_text().splitlines():
            if line.startswith("version:"): pv = line.split(":",1)[1].strip(); break
    except Exception: pass
    protov = None
    try:
        for line in protocol_py.read_text().splitlines():
            if line.startswith("VERSION ="): protov = line.split("=",1)[1].strip().strip('"').strip("'"); break
    except Exception: pass
    v244v = None
    try:
        for line in v244_py.read_text().splitlines():
            if line.startswith("PLUGIN_VERSION ="): v244v = line.split("=",1)[1].strip().strip('"').strip("'"); break
    except Exception: pass
    return {"skill": sv, "plugin_yaml": pv, "protocol": protov, "v244": v244v,
            "all_246": sv == "2.4.6" and pv == "2.4.6" and protov == "2.4.6" and v244v == "2.4.6"}

def smoke_test(plugin_dir):
    try:
        r = subprocess.run([sys.executable, "-c",
            "import sys; sys.path.insert(0, %r); import event_store, protocol, retriever, registry, v244_metadata; print('IMPORT_OK')" % str(plugin_dir)],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and "IMPORT_OK" in r.stdout:
            return {"ok": True, "msg": "import ok"}
        return {"ok": False, "msg": r.stderr[:120]}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:120]}

deploy_local()

# ── remote peers via SSH ──
def deploy_ssh(name, host, user, pw, home):
    try:
        r = subprocess.run(["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no",
            f"{user}@{host}", f"mkdir -p {home}/.hermes/backups {home}/.hermes/plugins/capability-reuse"],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            results[name] = {"status": "FAIL", "reason": f"ssh mkdir: {r.stderr[:80]}"}
            log(f"{name}: FAIL {r.stderr[:80]}"); return
        r = subprocess.run(["sshpass", "-p", pw, "scp", "-o", "StrictHostKeyChecking=no",
            ARTIFACT, f"{user}@{host}:/tmp/"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            results[name] = {"status": "FAIL", "reason": f"scp: {r.stderr[:80]}"}
            log(f"{name}: FAIL scp {r.stderr[:80]}"); return
        r = subprocess.run(["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{host}",
            f"set -e; "
            f"BK={home}/.hermes/backups/capreuse-246-$(date +%s); "
            f"mkdir -p $BK; "
            f"[ -d {home}/.hermes/skills/hermes/capability-reuse ] && cp -r {home}/.hermes/skills/hermes/capability-reuse $BK/skill; "
            f"[ -d {home}/.hermes/plugins/capability-reuse ] && cp -r {home}/.hermes/plugins/capability-reuse $BK/plugin; "
            f"rm -rf /tmp/capreuse-246-extract; mkdir -p /tmp/capreuse-246-extract; "
            f"cd /tmp && unzip -oq /tmp/capability-reuse-v2.4.6.zip -d /tmp/capreuse-246-extract/; "
            f"rm -rf {home}/.hermes/skills/hermes/capability-reuse; "
            f"cp -r /tmp/capreuse-246-extract/capability-reuse {home}/.hermes/skills/hermes/capability-reuse; "
            f"rm -rf {home}/.hermes/plugins/capability-reuse/__pycache__; "
            f"cp -r /tmp/capreuse-246-extract/capability-reuse/plugin/. {home}/.hermes/plugins/capability-reuse/; "
            f"touch {home}/.hermes/plugins/capability-reuse/plugin.yaml; "
            f"echo BACKUP_OK"],
            capture_output=True, text=True, timeout=90)
        if r.returncode != 0:
            results[name] = {"status": "FAIL", "reason": f"install: {r.stderr[:120]}"}
            log(f"{name}: FAIL install {r.stderr[:120]}"); return
        # verify versions
        r = subprocess.run(["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{host}",
            f"grep '^version:' {home}/.hermes/skills/hermes/capability-reuse/SKILL.md | head -1; "
            f"grep '^version:' {home}/.hermes/plugins/capability-reuse/plugin.yaml | head -1; "
            f"grep '^VERSION =' {home}/.hermes/plugins/capability-reuse/protocol.py | head -1; "
            f"grep '^PLUGIN_VERSION =' {home}/.hermes/plugins/capability-reuse/v244_metadata.py | head -1; "
            f"curl -s --connect-timeout 3 http://127.0.0.1:18643/hmp/health"],
            capture_output=True, text=True, timeout=30)
        out = r.stdout
        versions = {"skill": "?", "plugin_yaml": "?", "protocol": "?", "v244": "?"}
        lines = out.strip().splitlines()
        for i, ln in enumerate(lines[:4]):
            if ":" in ln:
                key = "skill" if i==0 else "plugin_yaml" if i==1 else "protocol" if i==2 else "v244"
                versions[key] = ln.split(":",1)[1].strip().strip('"').strip("'")
        all_ok = all(v == "2.4.6" for v in versions.values())
        hmp = out.strip().splitlines()[-1] if out.strip() else ""
        health_ok = "ok" in hmp
        # smoke: python import
        r = subprocess.run(["sshpass", "-p", pw, "ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{host}",
            f"cd {home}/.hermes/plugins/capability-reuse && python3 -c 'import event_store, protocol, retriever, registry, v244_metadata; print(\"IMPORT_OK\")' 2>&1 | tail -1"],
            capture_output=True, text=True, timeout=30)
        smoke_ok = "IMPORT_OK" in r.stdout
        results[name] = {"status": "OK" if (all_ok and health_ok and smoke_ok) else "PARTIAL",
                          "versions": versions, "hmp": health_ok, "smoke_import": smoke_ok}
        log(f"{name}: {results[name]['status']} versions={versions} hmp={health_ok} smoke={smoke_ok}")
    except Exception as e:
        results[name] = {"status": "FAIL", "reason": str(e)[:100]}
        log(f"{name}: FAIL {str(e)[:100]}")

deploy_ssh("peer106", "192.168.178.106", "root", "ccll4372", "/root")
deploy_ssh("peer138", "192.168.178.138", "root", "ccll4372", "/root")
deploy_ssh("peer58", "192.168.178.58", "root", "ccll4372", "/root")

# offline peers
for name in ("peer84", "peer105", "peer128"):
    results[name] = {"status": "OFFLINE"}
    log(f"{name}: OFFLINE")

REPORT.write_text(json.dumps(results, indent=2))
log(f"REPORT: {REPORT}")
