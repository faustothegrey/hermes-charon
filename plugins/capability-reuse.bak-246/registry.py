from __future__ import annotations
"""
registry.py — Capability Reuse Plugin: Registry Reader
======================================================
Reads the capability registry from ~/.hermes/data/capability-registry/.

Structure:
  data/capability-registry/
    registry.json       ← Index: list of capabilities with metadata
    schema.json         ← JSON Schema (for validation)
    contracts/          ← Per-capability invocation contracts
      hmp-healthcheck.json
      hmp-send.json
      peer-heartbeat.json

All reads are cached in memory for fast-path retrieval.
Registry is read once at plugin init and refreshed on demand.
"""
import json, os, threading
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone

REGISTRY_DIR = Path.home() / ".hermes" / "data" / "capability-registry"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"
CONTRACTS_DIR = REGISTRY_DIR / "contracts"

# ── Cache ──
_cache_lock = threading.Lock()
_registry_cache: Optional[dict] = None        # Full registry index
_contract_cache: dict[str, dict] = {}          # capability_id → contract
_last_refresh: float = 0.0
_CACHE_TTL = 60.0  # seconds before auto-refresh

# ── Exceptions ──

class RegistryError(Exception):
    """Base registry error."""

class CapabilityNotFound(RegistryError):
    """Requested capability_id not found."""

class VersionNotFound(RegistryError):
    """Requested capability version not found."""

# ── Internal helpers ──

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _timestamp():
    return datetime.now(timezone.utc).timestamp()

# ── Public API ──

def load(force: bool = False) -> Optional[dict]:
    """
    Load the registry index into cache. Returns the registry dict.
    Cached for _CACHE_TTL seconds. Use force=True to bypass cache.
    """
    global _registry_cache, _last_refresh

    now = _timestamp()
    with _cache_lock:
        if not force and _registry_cache and (now - _last_refresh) < _CACHE_TTL:
            return _registry_cache

        if not REGISTRY_PATH.exists():
            _registry_cache = {"registry_version": "1.0", "capabilities": []}
            return _registry_cache

        try:
            _registry_cache = json.loads(REGISTRY_PATH.read_text())
            _last_refresh = now
            return _registry_cache
        except (json.JSONDecodeError, OSError) as e:
            raise RegistryError(f"Cannot read registry: {e}") from e

def refresh():
    """Force a cache refresh."""
    return load(force=True)

def get_capability(capability_id: str, version: str = "") -> Optional[dict]:
    """
    Find a capability by ID and optional version.
    Returns the full registry entry (retrieval_metadata + invocation_contract).
    If version is empty, returns the latest version.
    """
    reg = load()
    caps = reg.get("capabilities", [])

    candidates = [c for c in caps
                  if c.get("retrieval_metadata", {}).get("capability_id") == capability_id]

    if not candidates:
        return None

    if version:
        for c in candidates:
            if c.get("retrieval_metadata", {}).get("version") == version:
                return c
        return None

    # Latest version (semver compare)
    def _sort_key(c):
        try:
            parts = c["retrieval_metadata"]["version"].split(".")
            return tuple(int(x) for x in parts)
        except (ValueError, KeyError):
            return (0, 0, 0)

    candidates.sort(key=_sort_key, reverse=True)
    return candidates[0]

def list_capabilities(trust_state: str = "",
                      effect_class: str = "",
                      limit: int = 50) -> list[dict]:
    """
    List capabilities with optional filters.
    Returns list of registry entries.
    """
    reg = load()
    caps = reg.get("capabilities", [])

    if trust_state:
        caps = [c for c in caps
                if c.get("invocation_contract", {}).get("trust_state") == trust_state]
    if effect_class:
        caps = [c for c in caps
                if c.get("invocation_contract", {}).get("effect_class") == effect_class]

    return caps[:limit]

def get_contract(capability_id: str, version: str = "") -> Optional[dict]:
    """
    Get the invocation contract for a capability.
    First tries in-memory cache, then reads from contracts/ directory.
    """
    global _contract_cache

    # Try in-memory cache
    key = f"{capability_id}@{version}" if version else capability_id
    with _cache_lock:
        if key in _contract_cache:
            return _contract_cache[key]

    # Try cap directory
    cap = get_capability(capability_id, version)
    if cap and "invocation_contract" in cap:
        contract = cap["invocation_contract"]
        with _cache_lock:
            _contract_cache[key] = contract
        return contract

    # Exact version lookups must fail closed. Do not silently fall back to an
    # unversioned contract when the caller requested a specific version.
    if version:
        contract_file = CONTRACTS_DIR / capability_id / f"{version}.json"
        if not contract_file.exists():
            return None
    else:
        contract_file = CONTRACTS_DIR / f"{capability_id}.json"
    if contract_file.exists():
        try:
            contract = json.loads(contract_file.read_text())
            if version and (contract.get("capability_id") != capability_id or contract.get("version") != version):
                return None
            with _cache_lock:
                _contract_cache[key] = contract
            return contract
        except (json.JSONDecodeError, OSError):
            pass

    return None

def input_schema(capability_id: str, version: str = "") -> Optional[dict]:
    """Get input schema for a capability."""
    contract = get_contract(capability_id, version)
    return contract.get("input_schema") if contract else None

def output_schema(capability_id: str, version: str = "") -> Optional[dict]:
    """Get output schema."""
    contract = get_contract(capability_id, version)
    return contract.get("output_schema") if contract else None

def error_schema(capability_id: str, version: str = "") -> Optional[dict]:
    """Get error schema."""
    contract = get_contract(capability_id, version)
    return contract.get("error_schema") if contract else None

def get_effect_class(capability_id: str, version: str = "") -> Optional[str]:
    """Get effect class for a capability."""
    contract = get_contract(capability_id, version)
    return contract.get("effect_class") if contract else None

def get_trust_state(capability_id: str, version: str = "") -> Optional[str]:
    """Get trust state."""
    contract = get_contract(capability_id, version)
    return contract.get("trust_state") if contract else None

def get_feature_ids(capability_id: str, version: str = "") -> list[str]:
    """Get supported feature IDs for a capability from retrieval metadata."""
    cap = get_capability(capability_id, version)
    if not cap:
        return []
    return cap.get("retrieval_metadata", {}).get("feature_ids", {}).get("supported", [])

def get_excluded_feature_ids(capability_id: str, version: str = "") -> list[str]:
    """Get excluded feature IDs."""
    cap = get_capability(capability_id, version)
    if not cap:
        return []
    return cap.get("retrieval_metadata", {}).get("feature_ids", {}).get("excluded", [])

def get_examples(capability_id: str, version: str = "") -> list[str]:
    """Get example requests for a capability."""
    cap = get_capability(capability_id, version)
    if not cap:
        return []
    return cap.get("retrieval_metadata", {}).get("examples", [])

def get_supports_text(capability_id: str, version: str = "") -> list[str]:
    """Get human-readable supported features."""
    cap = get_capability(capability_id, version)
    if not cap:
        return []
    return cap.get("retrieval_metadata", {}).get("supports_text", [])

def get_fallback_policy(capability_id: str, version: str = "") -> Optional[str]:
    """Get fallback policy."""
    contract = get_contract(capability_id, version)
    return contract.get("fallback_policy") if contract else None

def get_contract_hash(capability_id: str, version: str = "") -> str:
    """Compute a quick hash of the contract for provenance tracking."""
    import hashlib
    contract = get_contract(capability_id, version)
    if not contract:
        return ""
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:16]

def is_capability_read_only(capability_id: str, version: str = "") -> bool:
    """Check if a capability is declared read-only."""
    return get_effect_class(capability_id, version) == "read_only"

def is_capability_trusted(capability_id: str, version: str = "") -> bool:
    """Check if a capability version is trusted."""
    return get_trust_state(capability_id, version) == "trusted"

def is_failure_clean(capability_id: str, version: str, failure_code: str) -> bool:
    """Check if a failure code is declared as clean for this capability."""
    contract = get_contract(capability_id, version)
    if not contract:
        return False
    clean_codes = contract.get("error_schema", {}).get("clean_failure_codes", [])
    return failure_code in clean_codes

# ── Stats ──

def get_stats() -> dict:
    """Return registry statistics."""
    reg = load()
    caps = reg.get("capabilities", [])
    if not caps:
        return {"total": 0, "trust_states": {}, "effect_classes": {}}

    trust_states = {}
    effect_classes = {}
    by_version = {}
    owners = set()

    for c in caps:
        meta = c.get("retrieval_metadata", {})
        inv = c.get("invocation_contract", {})
        ts = inv.get("trust_state", "unknown")
        ec = inv.get("effect_class", "unknown")
        ver = meta.get("version", "0.0.0")
        owner = meta.get("contract_owner", "?")
        cid = meta.get("capability_id", "?")

        trust_states[ts] = trust_states.get(ts, 0) + 1
        effect_classes[ec] = effect_classes.get(ec, 0) + 1
        by_version[cid] = ver
        owners.add(owner)

    return {
        "total": len(caps),
        "trust_states": trust_states,
        "effect_classes": effect_classes,
        "latest_versions": by_version,
        "contract_owners": list(owners),
        "registry_version": reg.get("registry_version", "?"),
        "source": str(REGISTRY_PATH),
    }

def get_registry_version() -> str:
    """Return the registry data format version."""
    reg = load()
    return reg.get("registry_version", "?")

def get_latest_version(capability_id: str) -> Optional[str]:
    """Get the latest version string for a capability."""
    cap = get_capability(capability_id)
    if cap:
        return cap.get("retrieval_metadata", {}).get("version")
    return None

def get_all_capability_ids() -> list[str]:
    """Get all registered capability IDs."""
    reg = load()
    return [c.get("retrieval_metadata", {}).get("capability_id", "?")
            for c in reg.get("capabilities", [])]

def get_capability_count() -> int:
    """Total number of registered capability versions."""
    reg = load()
    return len(reg.get("capabilities", []))