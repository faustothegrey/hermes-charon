#!/usr/bin/env python3
"""
register-capability.py — Phase 0.2: Register a capability in the registry.
Usage: python3 register-capability.py [--list | --add <json_file>]
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

REGISTRY_DIR = Path.home() / ".hermes" / "data" / "capability-registry"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"
CONTRACTS_DIR = REGISTRY_DIR / "contracts"

def load_registry():
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {"registry_version": "1.0", "capabilities": []}

def save_registry(registry):
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

def register(cap):
    registry = load_registry()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for idx, existing in enumerate(registry["capabilities"]):
        if existing["retrieval_metadata"]["capability_id"] == cap["retrieval_metadata"]["capability_id"] and \
           existing["retrieval_metadata"]["version"] == cap["retrieval_metadata"]["version"]:
            cap["registered_at"] = existing.get("registered_at", now)
            cap["updated_at"] = now
            registry["capabilities"][idx] = cap
            save_registry(registry)
            contract = cap["invocation_contract"]
            cpath = CONTRACTS_DIR / f"{cap['retrieval_metadata']['capability_id']}.json"
            CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(contract, indent=2))
            print(f"  ✅ Updated: {cap['retrieval_metadata']['capability_id']} v{cap['retrieval_metadata']['version']}")
            return
    cap["registered_at"] = now
    cap["updated_at"] = now
    registry["capabilities"].append(cap)
    save_registry(registry)
    contract = cap["invocation_contract"]
    cpath = CONTRACTS_DIR / f"{cap['retrieval_metadata']['capability_id']}.json"
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(contract, indent=2))
    print(f"  ✅ {cap['retrieval_metadata']['capability_id']} v{cap['retrieval_metadata']['version']} — {cap['retrieval_metadata']['name']}")

def list_capabilities():
    registry = load_registry()
    for cap in registry.get("capabilities", []):
        m = cap["retrieval_metadata"]
        st = cap["invocation_contract"]["trust_state"]
        print(f"  {m['capability_id']:<25} v{m['version']:<8} [{st:<10}] {m['name']}")

CAPABILITIES = {
    "hmp-healthcheck": {"retrieval_metadata":{"capability_id":"hmp-healthcheck","version":"1.0.0","name":"HMP Healthcheck","description":"Checks health/latency across HMP peers","examples":["check all HMP peers","peer status with partial failures","check HMP health for peer128","check HMP health for peer70","HMP health status for a peer","are HMP peers healthy?"],"supports_text":["multiple peers","partial failures","configurable timeout","HMP health endpoint","single peer health","peer128 health","peer health status"],"excludes_text":["mutating endpoints","interactive auth","streaming"],"assumptions_text":["peer addresses known","port 18643 accessible"],"feature_ids":{"supported":["targets.multiple","failure.partial","timeout.configurable"],"excluded":["endpoint.mutating","authentication.interactive","protocol.streaming"]},"contract_owner":"fausto"},"invocation_contract":{"capability_id":"hmp-healthcheck","version":"1.0.0","executor":{"kind":"python_callable","entrypoint":"hermes_harnesses.hmp:healthcheck","timeout_seconds":30},"public_invocation_tool":"invoke_capability","input_schema":{"type":"object","required":["peer_list"],"properties":{"peer_list":{"type":"array","items":{"type":"string"},"minItems":1},"timeout_seconds":{"type":"integer","minimum":1,"maximum":120,"default":10}}},"output_schema":{"type":"array","items":{"type":"object","required":["peer","status"],"properties":{"peer":{"type":"string"},"status":{"type":"string"},"latency_ms":{"type":["number","null"]},"error":{"type":["string","null"]}}}},"error_schema":{"clean_failure_codes":["invalid_input","unavailable","timeout"],"partial_effect_possible":False},"effect_class":"read_only","declared_effects":["network_read"],"idempotency":"safe","required_permissions":["hmp.network.read"],"availability_constraints":["hmp_client_installed"],"fallback_policy":"allow_execute_code_after_clean_failure","trust_state":"trusted","trust_basis":"phase1b_read_only_canary_reviewed_local_harness","trust_owner":"fausto","trust_review_due":"2026-09-01","equivalence_policy_ref":"read_only_hmp_health_json_equivalence_v1"}},
    "hmp-send": {"retrieval_metadata":{"capability_id":"hmp-send","version":"1.0.0","name":"HMP Message Send","description":"Sends a message to a peer via HMP :18643","examples":["send to peer106","tell peer84 to healthcheck","broadcast"],"supports_text":["single peer","multiple peers","text payload"],"excludes_text":["file transfer","streaming","binary"],"assumptions_text":["peer online on :18643","text <2KB"],"feature_ids":{"supported":["target.single","target.multiple","payload.text"],"excluded":["payload.file","payload.binary","protocol.streaming"]},"contract_owner":"fausto"},"invocation_contract":{"capability_id":"hmp-send","version":"1.0.0","executor":{"kind":"python_callable","entrypoint":"hmp_dual_plane.send_to_peer","timeout_seconds":30},"public_invocation_tool":"invoke_capability","input_schema":{"type":"object","required":["peer","text"],"properties":{"peer":{"type":"string"},"text":{"type":"string","maxLength":2000},"session_id":{"type":"string"}}},"output_schema":{"type":"object","properties":{"status":{"type":"string"},"channel":{"type":"string"},"response":{"type":"string"}}},"error_schema":{"clean_failure_codes":["invalid_input","peer_offline_before_send"],"partial_effect_possible":True},"effect_class":"mutating","declared_effects":["network_write","remote_message_delivery"],"idempotency":"unsafe","required_permissions":["hmp.network.write"],"availability_constraints":["hmp_client_installed"],"fallback_policy":"block_escalate","trust_state":"observed","trust_basis":"phase0_onboarding","trust_owner":"fausto","trust_review_due":"2026-09-01","equivalence_policy_ref":""}},
    "peer-heartbeat": {"retrieval_metadata":{"capability_id":"peer-heartbeat","version":"1.0.0","name":"Peer Heartbeat Monitor","description":"Pings a single peer HTTP /health","examples":["check peer84","ping peer106","connectivity test"],"supports_text":["single peer","repeated pings","interval","timeout"],"excludes_text":["bulk scan","latency trend","service discovery"],"assumptions_text":["peer responds :18643/:8642","network reachable"],"feature_ids":{"supported":["target.single","ping.repeated","timeout.configurable"],"excluded":["scan.bulk","metric.latency_trend","discovery.service"]},"contract_owner":"fausto"},"invocation_contract":{"capability_id":"peer-heartbeat","version":"1.0.0","executor":{"kind":"python_callable","entrypoint":"hermes_harnesses.hmp:heartbeat","timeout_seconds":15},"public_invocation_tool":"invoke_capability","input_schema":{"type":"object","required":["peer"],"properties":{"peer":{"type":"string"},"port":{"type":"integer","default":18643},"timeout_seconds":{"type":"integer","minimum":1,"maximum":30,"default":5}}},"output_schema":{"type":"object","required":["peer","online"],"properties":{"peer":{"type":"string"},"online":{"type":"boolean"},"latency_ms":{"type":["number","null"]},"error":{"type":["string","null"]}}},"error_schema":{"clean_failure_codes":["invalid_input","unavailable","timeout"],"partial_effect_possible":False},"effect_class":"read_only","declared_effects":["network_read"],"idempotency":"safe","required_permissions":["network.read"],"availability_constraints":[],"fallback_policy":"allow_execute_code_after_clean_failure","trust_state":"observed","trust_basis":"phase0_onboarding","trust_owner":"fausto","trust_review_due":"2026-09-01","equivalence_policy_ref":""}}
}

def main():
    if "--list" in sys.argv:
        list_capabilities(); return
    print("Registering Phase 0.2 capabilities...")
    for name in ["hmp-healthcheck", "hmp-send", "peer-heartbeat"]:
        register(CAPABILITIES[name])
    print("\nRegistry:")
    list_capabilities()

if __name__ == "__main__": main()
