from __future__ import annotations
"""
compatibility.py — Capability Reuse Plugin: Hard Filters & Schema Validation
============================================================================
Deterministic compatibility checks between a request and a capability contract.
No LLM calls, no scoring — just Yes/No on hard constraints.

Used by the retriever to filter candidates before scoring/rerank.
Used by Tier 1 bypass validation (§8.1) for contradiction checks.
"""
import json, re
from dataclasses import dataclass
from typing import Any, Optional

# ── Compatibility result ──

@dataclass
class CompatibilityResult:
    """Result of a compatibility check."""
    compatible: bool
    reason: str = ""

def compatible() -> CompatibilityResult:
    return CompatibilityResult(compatible=True)

def incompatible(reason: str) -> CompatibilityResult:
    return CompatibilityResult(compatible=False, reason=reason)

# ── Effect class safety ──

# Allowed effect class transitions for intervention
# A read-only capability may be offered for any request.
# A mutating capability may only be offered for mutating requests.
ALLOWED_EFFECT_TRANSITIONS = {
    "read_only": {"read_only", "unknown", ""},
    "mutating": {"mutating"},
    "unknown": {"read_only", "unknown", ""},
}

def check_effect_class(request_effect: str, capability_effect: str) -> CompatibilityResult:
    """
    Check that a capability's effect class is compatible with the request's
    implied effect class.
    
    If request_effect is empty/unknown, only read_only capabilities are injected
    (conservative default). Mutating capabilities require explicit request hint.
    """
    if not request_effect:
        # Default: only offer read-only for unknown request effect
        if capability_effect == "read_only":
            return compatible()
        return incompatible(
            f"Capability effect is '{capability_effect}', but request effect "
            f"is unknown. Only read_only capabilities are offered by default."
        )

    allowed = ALLOWED_EFFECT_TRANSITIONS.get(request_effect, set())
    if capability_effect in allowed:
        return compatible()
    return incompatible(
        f"Effect class mismatch: request='{request_effect}', "
        f"capability='{capability_effect}'. "
        f"Allowed transitions from '{request_effect}': {allowed}"
    )

# ── Trust state ──

def check_trust_state(capability_trust_state: str) -> CompatibilityResult:
    """Only 'trusted' capabilities are eligible for intervention."""
    if capability_trust_state == "trusted":
        return compatible()
    return incompatible(
        f"Capability trust state is '{capability_trust_state}', "
        f"must be 'trusted' for intervention"
    )

# ── Permission check ──

def check_permissions(required_permissions: list[str],
                      available_permissions: list[str]) -> CompatibilityResult:
    """Check that all required permissions are available."""
    if not required_permissions:
        return compatible()
    if not available_permissions:
        return incompatible(f"Required permissions {required_permissions} but none available")

    missing = [p for p in required_permissions if p not in available_permissions]
    if missing:
        return incompatible(f"Missing required permissions: {missing}")
    return compatible()

# ── Availability constraints ──

def check_availability(availability_constraints: list[str],
                       available_capabilities: list[str]) -> CompatibilityResult:
    """Check that all availability constraints are satisfied."""
    if not availability_constraints:
        return compatible()
    missing = [c for c in availability_constraints if c not in available_capabilities]
    if missing:
        return incompatible(f"Unsatisfied availability constraints: {missing}")
    return compatible()

# ── Feature exclusion check ──

def check_feature_exclusion(requested_features: list[str],
                            excluded_features: list[str]) -> CompatibilityResult:
    """
    Check that none of the requested features are in the excluded list.
    Contract silence on a feature does NOT count as exclusion.
    """
    if not excluded_features or not requested_features:
        return compatible()
    
    excluded = set(excluded_features)
    conflicts = [f for f in requested_features if f in excluded]
    if conflicts:
        return incompatible(
            f"Requested features {conflicts} are explicitly excluded "
            f"by this capability contract"
        )
    return compatible()

# ── Schema validation (lightweight) ──

def validate_against_schema(value: Any, schema: dict) -> CompatibilityResult:
    """
    Lightweight schema validation. Checks type, required fields, and
    constraints like minItems, maxLength, minimum, maximum.

    This fallback is intentionally dependency-free. The invocation boundary
    calls strict_validate_against_schema() for full contract enforcement.
    """
    if not schema:
        return compatible()

    schema_type = schema.get("type", "")

    # Type check
    if schema_type == "object":
        if not isinstance(value, dict):
            return incompatible(f"Expected object, got {type(value).__name__}")
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                return incompatible(f"Missing required field: '{field}'")
        # Check property types
        props = schema.get("properties", {})
        for key, val in value.items():
            if key in props:
                prop_schema = props[key]
                result = validate_against_schema(val, prop_schema)
                if not result.compatible:
                    return result

    elif schema_type == "array":
        if not isinstance(value, list):
            return incompatible(f"Expected array, got {type(value).__name__}")
        min_items = schema.get("minItems", 0)
        if len(value) < min_items:
            return incompatible(f"Array has {len(value)} items, minimum is {min_items}")
        max_items = schema.get("maxItems", float("inf"))
        if len(value) > max_items:
            return incompatible(f"Array has {len(value)} items, maximum is {max_items}")
        items_schema = schema.get("items", {})
        for item in value:
            result = validate_against_schema(item, items_schema)
            if not result.compatible:
                return result

    elif schema_type == "string":
        if not isinstance(value, str):
            return incompatible(f"Expected string, got {type(value).__name__}")
        max_len = schema.get("maxLength", float("inf"))
        if len(value) > max_len:
            return incompatible(f"String exceeds maxLength {max_len} ({len(value)} chars)")

    elif schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return incompatible(f"Expected integer, got {type(value).__name__}")
        if "minimum" in schema and value < schema["minimum"]:
            return incompatible(f"Integer {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            return incompatible(f"Integer {value} > maximum {schema['maximum']}")

    elif schema_type == "number":
        if not isinstance(value, (int, float)):
            return incompatible(f"Expected number, got {type(value).__name__}")

    elif schema_type == "boolean":
        if not isinstance(value, bool):
            return incompatible(f"Expected boolean, got {type(value).__name__}")

    return compatible()


def strict_validate_against_schema(value: Any, schema: dict) -> CompatibilityResult:
    """Strict JSON-Schema-like validation used at invoke_capability boundary.

    Uses jsonschema.Draft7Validator when installed; otherwise enforces the
    draft-07 subset present in bundled contracts, including union types,
    additionalProperties, required, arrays/items, numeric bounds and strings.
    """
    if not schema:
        return compatible()
    try:
        from jsonschema import Draft7Validator  # type: ignore
        errors = sorted(Draft7Validator(schema).iter_errors(value), key=lambda e: list(e.path))
        if errors:
            e = errors[0]
            path = "/" + "/".join(str(p) for p in e.path) if e.path else "/"
            return incompatible(f"{path}: {e.message}")
        return compatible()
    except ImportError:
        return _validate_schema_subset(value, schema, path="/")


def _validate_schema_subset(value: Any, schema: dict, path: str = "/") -> CompatibilityResult:
    if not schema:
        return compatible()
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        results = [_validate_schema_subset(value, dict(schema, type=t), path) for t in schema_type]
        if any(r.compatible for r in results):
            return compatible()
        return incompatible(f"{path}: value does not match any allowed type {schema_type}")
    if schema_type == "object":
        if not isinstance(value, dict):
            return incompatible(f"{path}: expected object, got {type(value).__name__}")
        for field in schema.get("required", []):
            if field not in value:
                return incompatible(f"{path}: missing required field {field}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = [k for k in value if k not in props]
            if extra:
                return incompatible(f"{path}: additional properties not allowed: {extra}")
        for key, val in value.items():
            if key in props:
                child = path.rstrip("/") + "/" + str(key)
                r = _validate_schema_subset(val, props[key], child)
                if not r.compatible:
                    return r
    elif schema_type == "array":
        if not isinstance(value, list):
            return incompatible(f"{path}: expected array, got {type(value).__name__}")
        if "minItems" in schema and len(value) < schema["minItems"]:
            return incompatible(f"{path}: array has {len(value)} items, minimum is {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return incompatible(f"{path}: array has {len(value)} items, maximum is {schema['maxItems']}")
        item_schema = schema.get("items", {})
        for idx, item in enumerate(value):
            r = _validate_schema_subset(item, item_schema, path.rstrip("/") + f"/{idx}")
            if not r.compatible:
                return r
    elif schema_type == "string":
        if not isinstance(value, str):
            return incompatible(f"{path}: expected string, got {type(value).__name__}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            return incompatible(f"{path}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return incompatible(f"{path}: string exceeds maxLength {schema['maxLength']}")
        if "enum" in schema and value not in schema["enum"]:
            return incompatible(f"{path}: value not in enum")
    elif schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return incompatible(f"{path}: expected integer, got {type(value).__name__}")
        if "minimum" in schema and value < schema["minimum"]:
            return incompatible(f"{path}: integer {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            return incompatible(f"{path}: integer {value} > maximum {schema['maximum']}")
    elif schema_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return incompatible(f"{path}: expected number, got {type(value).__name__}")
    elif schema_type == "boolean":
        if not isinstance(value, bool):
            return incompatible(f"{path}: expected boolean, got {type(value).__name__}")
    elif schema_type == "null":
        if value is not None:
            return incompatible(f"{path}: expected null, got {type(value).__name__}")
    return compatible()

# ── Tier 1 contradiction checks (§8.1) ──

def check_tier1_missing_feature(claimed_feature_id: str,
                                 capability_id: str,
                                 capability_version: str) -> CompatibilityResult:
    """
    Tier 1 check: If the agent claims a supported feature is missing, but the
    capability contract declares it as supported → contradiction.
    
    Only positive contradictions are flagged. Contract silence is never
    treated as suspicious (§8.1).
    """
    from . import registry as reg
    
    supported = reg.get_feature_ids(capability_id, capability_version)
    
    if claimed_feature_id in supported:
        return incompatible(
            f"Tier 1 contradiction: feature '{claimed_feature_id}' is declared "
            f"as supported by {capability_id}@{capability_version}, "
            f"but agent claimed it is missing"
        )
    
    return compatible()  # No contradiction

def check_tier1_missing_output_field(field_path: str,
                                      capability_id: str,
                                      capability_version: str) -> CompatibilityResult:
    """
    Tier 1 check: If the agent claims a specific output field is missing,
    but the output schema declares it → contradiction.
    """
    from . import registry as reg
    
    schema = reg.output_schema(capability_id, capability_version)
    if not schema:
        return compatible()
    
    # Simple path check: split by "/" and walk the schema
    parts = [p for p in field_path.split("/") if p]
    current = schema
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            elif "items" in current and isinstance(current.get("items"), dict):
                current = current["items"].get("properties", {}).get(part, {})
            elif "properties" in current:
                current = current["properties"].get(part, {})
            else:
                return compatible()  # Not found → no contradiction
        else:
            return compatible()
    
    return incompatible(
        f"Tier 1 contradiction: output field '{field_path}' exists in "
        f"{capability_id}@{capability_version} output schema"
    )

def check_tier1_environment_constraint(constraint_id: str,
                                        capability_id: str,
                                        capability_version: str,
                                        satisfied_constraints: list[str]) -> CompatibilityResult:
    """
    Tier 1 check: If agent claims environment constraint is unsatisfied,
    but it's actually satisfied → contradiction.
    """
    if constraint_id in satisfied_constraints:
        return incompatible(
            f"Tier 1 contradiction: constraint '{constraint_id}' is satisfied "
            f"in the current environment"
        )
    return compatible()

# ── Full compatibility check ──

def check_all(
    capability: dict,
    request_effect: str = "",
    available_permissions: list[str] | None = None,
    available_capabilities: list[str] | None = None,
    requested_features: list[str] | None = None,
) -> CompatibilityResult:
    """
    Run all hard compatibility checks for a capability.
    Short-circuits on first failure.
    """
    inv = capability.get("invocation_contract", {})
    
    # 1. Trust state
    r = check_trust_state(inv.get("trust_state", ""))
    if not r.compatible:
        return r
    
    # 2. Effect class
    r = check_effect_class(request_effect, inv.get("effect_class", ""))
    if not r.compatible:
        return r
    
    # 3. Permissions
    r = check_permissions(
        inv.get("required_permissions", []),
        available_permissions or []
    )
    if not r.compatible:
        return r
    
    # 4. Availability
    r = check_availability(
        inv.get("availability_constraints", []),
        available_capabilities or []
    )
    if not r.compatible:
        return r
    
    # 5. Feature exclusion
    meta = capability.get("retrieval_metadata", {})
    excluded = meta.get("feature_ids", {}).get("excluded", [])
    r = check_feature_exclusion(requested_features or [], excluded)
    if not r.compatible:
        return r
    
    return compatible()