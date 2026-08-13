#!/usr/bin/env python3
"""
init-registry.py — Phase 0.1: Create capability registry schema + storage.
Standalone. Run once per peer. Creates directory structure.
"""
import json, os
from pathlib import Path

REGISTRY_BASE = Path.home() / ".hermes" / "data" / "capability-registry"
SCHEMA_PATH = REGISTRY_BASE / "schema.json"
REGISTRY_PATH = REGISTRY_BASE / "registry.json"
CONTRACTS_DIR = REGISTRY_BASE / "contracts"

SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Capability Registry Schema v1.0",
    "version": "1.0",
    "definitions": {
        "retrieval_metadata": {
            "type": "object",
            "required": ["capability_id","version","name","description","examples","supports_text","excludes_text","contract_owner"],
            "properties": {
                "capability_id": {"type":"string","pattern":"^[a-z][a-z0-9_-]+$"},
                "version": {"type":"string","pattern":"^\\d+\\.\\d+\\.\\d+$"},
                "name": {"type":"string","maxLength":80},
                "description": {"type":"string","maxLength":500},
                "examples": {"type":"array","items":{"type":"string","maxLength":200},"minItems":1,"maxItems":10},
                "supports_text": {"type":"array","items":{"type":"string","maxLength":100}},
                "excludes_text": {"type":"array","items":{"type":"string","maxLength":100}},
                "assumptions_text": {"type":"array","items":{"type":"string","maxLength":200}},
                "feature_ids": {"type":"object","properties":{"supported":{"type":"array","items":{"type":"string","pattern":"^[a-z][a-z0-9_.-]+$"}},"excluded":{"type":"array","items":{"type":"string","pattern":"^[a-z][a-z0-9_.-]+$"}}}},
                "contract_owner": {"type":"string"}
            }
        },
        "invocation_contract": {
            "type": "object",
            "required": ["capability_id","version","executor","input_schema","output_schema","error_schema","effect_class","idempotency","required_permissions","availability_constraints","fallback_policy","trust_state"],
            "properties": {
                "capability_id": {"type":"string"},
                "version": {"type":"string"},
                "executor": {"type":"object","required":["kind","entrypoint"],"properties":{"kind":{"type":"string","enum":["python_callable","shell_script","http_endpoint","harness"]},"entrypoint":{"type":"string"},"timeout_seconds":{"type":"integer","minimum":1,"maximum":300}}},
                "public_invocation_tool": {"type":"string","default":"invoke_capability"},
                "input_schema": {"type":"object"},
                "output_schema": {"type":"object"},
                "error_schema": {"type":"object","properties":{"clean_failure_codes":{"type":"array","items":{"type":"string"}},"partial_effect_possible":{"type":"boolean"}}},
                "effect_class": {"type":"string","enum":["read_only","mutating","unknown"]},
                "declared_effects": {"type":"array","items":{"type":"string"}},
                "idempotency": {"type":"string","enum":["safe","idempotent","unsafe"]},
                "required_permissions": {"type":"array","items":{"type":"string"}},
                "availability_constraints": {"type":"array","items":{"type":"string"}},
                "fallback_policy": {"type":"string","enum":["allow_execute_code_after_clean_failure","block_escalate","retry_then_escalate"]},
                "trust_state": {"type":"string","enum":["observed","validated","trusted","demoted"]},
                "trust_basis": {"type":"string"},
                "trust_owner": {"type":"string"},
                "trust_review_due": {"type":"string","format":"date"},
                "equivalence_policy_ref": {"type":"string"}
            }
        }
    },
    "type": "object",
    "properties": {
        "registry_version": {"type":"string"},
        "capabilities": {"type":"array","items":{"type":"object","required":["retrieval_metadata","invocation_contract"],"properties":{"retrieval_metadata":{"$ref":"#/definitions/retrieval_metadata"},"invocation_contract":{"$ref":"#/definitions/invocation_contract"},"registered_at":{"type":"string"},"updated_at":{"type":"string"}}}}
    }
}

def main():
    REGISTRY_BASE.mkdir(parents=True, exist_ok=True)
    CONTRACTS_DIR.mkdir(exist_ok=True)
    json.dump(SCHEMA, open(SCHEMA_PATH,"w"), indent=2)
    if not REGISTRY_PATH.exists() or os.path.getsize(REGISTRY_PATH) == 0:
        json.dump({"registry_version":"1.0","capabilities":[]}, open(REGISTRY_PATH,"w"), indent=2)
        print("Created empty registry.")
    else: print("Registry already exists.")
    print(f"Schema: {SCHEMA_PATH}")
    print(f"Registry: {REGISTRY_PATH}")
    print(f"Contracts: {CONTRACTS_DIR}/")
    print("Done.")

if __name__ == "__main__": main()
