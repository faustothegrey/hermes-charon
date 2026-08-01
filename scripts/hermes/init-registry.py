#!/usr/bin/env python3
"""
Capability Registry — Schema v1.0
Phase 0.1: Structure for storing registered capabilities.

Directory: ~/.hermes/data/capability-registry/
  schema.json           — This schema definition
  registry.json         — Index of all registered capabilities
  contracts/            — Per-capability invocation contracts
    hmp-healthcheck.json
    hmp-send.json
    peer-health-watch.json
    ...

Each capability version has two records:
  1) Retrieval metadata (for matching against requests)
  2) Invocation contract (for typed execution)

See spec §5.1 and §5.2 for field semantics.
"""

CAPABILITY_REGISTRY_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Capability Registry Schema v1.0",
    "description": "Schema for Hermes Capability Retrieval & Reuse Control Loop — Phase 0.1",
    "version": "1.0",
    "definitions": {
        "retrieval_metadata": {
            "type": "object",
            "required": [
                "capability_id", "version", "name", "description",
                "examples", "supports_text", "excludes_text", "contract_owner"
            ],
            "properties": {
                "capability_id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]+$"},
                "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                "name": {"type": "string", "maxLength": 80},
                "description": {"type": "string", "maxLength": 500},
                "examples": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 200},
                    "minItems": 1,
                    "maxItems": 10
                },
                "supports_text": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 100},
                    "description": "Human-readable list of supported features"
                },
                "excludes_text": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 100},
                    "description": "Human-readable list of explicitly excluded features"
                },
                "assumptions_text": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 200},
                    "description": "Assumptions the capability makes about the environment"
                },
                "feature_ids": {
                    "type": "object",
                    "properties": {
                        "supported": {
                            "type": "array",
                            "items": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]+$"}
                        },
                        "excluded": {
                            "type": "array",
                            "items": {"type": "string", "pattern": "^[a-z][a-z0-9_.-]+$"}
                        }
                    }
                },
                "contract_owner": {"type": "string", "description": "Named person or role"}
            }
        },
        "invocation_contract": {
            "type": "object",
            "required": [
                "capability_id", "version", "executor",
                "input_schema", "output_schema", "error_schema",
                "effect_class", "idempotency",
                "required_permissions", "availability_constraints",
                "fallback_policy", "trust_state"
            ],
            "properties": {
                "capability_id": {"type": "string"},
                "version": {"type": "string"},
                "executor": {
                    "type": "object",
                    "required": ["kind", "entrypoint"],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["python_callable", "shell_script", "http_endpoint", "harness"]
                        },
                        "entrypoint": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300}
                    }
                },
                "public_invocation_tool": {
                    "type": "string",
                    "default": "invoke_capability"
                },
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "error_schema": {
                    "type": "object",
                    "properties": {
                        "clean_failure_codes": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "partial_effect_possible": {"type": "boolean"}
                    }
                },
                "effect_class": {
                    "type": "string",
                    "enum": ["read_only", "mutating", "unknown"]
                },
                "declared_effects": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "idempotency": {
                    "type": "string",
                    "enum": ["safe", "idempotent", "unsafe"]
                },
                "required_permissions": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "availability_constraints": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "fallback_policy": {
                    "type": "string",
                    "enum": [
                        "allow_execute_code_after_clean_failure",
                        "block_escalate",
                        "retry_then_escalate"
                    ]
                },
                "trust_state": {
                    "type": "string",
                    "enum": ["observed", "validated", "trusted", "demoted"]
                },
                "trust_basis": {"type": "string"},
                "trust_owner": {"type": "string"},
                "trust_review_due": {"type": "string", "format": "date"},
                "equivalence_policy_ref": {"type": "string"}
            }
        }
    },
    "type": "object",
    "properties": {
        "registry_version": {"type": "string"},
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["retrieval_metadata", "invocation_contract"],
                "properties": {
                    "retrieval_metadata": {"$ref": "#/definitions/retrieval_metadata"},
                    "invocation_contract": {"$ref": "#/definitions/invocation_contract"},
                    "registered_at": {"type": "string", "format": "date-time"},
                    "updated_at": {"type": "string", "format": "date-time"}
                }
            }
        }
    }
}

if __name__ == "__main__":
    import json
    from pathlib import Path
    
    registry_dir = Path.home() / ".hermes" / "data" / "capability-registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    
    # Write schema
    schema_path = registry_dir / "schema.json"
    with open(schema_path, "w") as f:
        json.dump(CAPABILITY_REGISTRY_SCHEMA, f, indent=2)
    print(f"✅ Schema written: {schema_path}")
    
    # Write empty registry index
    registry_path = registry_dir / "registry.json"
    empty_registry = {
        "registry_version": "1.0",
        "capabilities": []
    }
    with open(registry_path, "w") as f:
        json.dump(empty_registry, f, indent=2)
    print(f"✅ Empty registry created: {registry_path}")
    
    # Create contracts directory
    contracts_dir = registry_dir / "contracts"
    contracts_dir.mkdir(exist_ok=True)
    print(f"✅ Contracts directory: {contracts_dir}")
    
    print()
    print("📂 Structure:")
    print(f"  {registry_dir}/")
    print(f"  ├── schema.json")
    print(f"  ├── registry.json")
    print(f"  └── contracts/")
