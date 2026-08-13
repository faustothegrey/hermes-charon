# Phase 1B active canary testing — peer-target discipline

Use this reference when testing the capability-reuse active path, especially the first read-only canary (`hmp-healthcheck@1.0.0`).

## Core distinction

Do not confuse the plugin host with the healthcheck target.

- Plugin host: the machine where `capability-reuse` is installed and whose Hermes runtime is being tested.
- HMP target: the peer whose `/hmp/health` or `/health` endpoint is probed by the dispatcher.

A successful `hmp-healthcheck(peerX)` proves the plugin host can dispatch a read-only capability that probes peerX. It does not prove peerX has the `capability-reuse` plugin deployed.

Before recommending manual tests, explicitly state this distinction if deployment is unclear.

## Preferred manual canary flow

Environment for active canary tests:

```bash
export CAPABILITY_REUSE_MODE=active
export CAPABILITY_REUSE_ACTIVE_CAPABILITIES=hmp-healthcheck
export CAPABILITY_REUSE_INTERVENTION_THRESHOLD=0.65
export CAPABILITY_REUSE_MINIMUM_MARGIN=0.10
```

Test only the user-approved peer target. If the user says “use peer128 for all testing,” all live HMP probes, examples, and reports should target peer128 only unless they explicitly change scope.

Recommended checks:

1. Active retrieval:
   - Prompt: `check HMP health for peer128`
   - Expected: active intervention for `hmp-healthcheck@1.0.0`.

2. Raw-code block:
   - With an open intervention, attempt raw `execute_code`.
   - Expected: blocked with message referencing the active intervention ID.

3. Live invoke:
   - Invoke `hmp-healthcheck@1.0.0` with `peer_list=["peer128"]`.
   - Expected: structured output with `peer=peer128`, `status=ok|timeout|error`, latency or clean error.
   - Never report fake success; timeout/offline is a valid clean result.

4. False-positive safety:
   - `send a message to peer128 saying hello` → must not select healthcheck.
   - `deploy the HMP plugin to peer128` → must not select healthcheck.

5. Clean read-only fallback:
   - Simulate or induce a timeout for peer128 healthcheck.
   - Expected: clean failure can issue a single-use fallback token; token consumption transitions to `fallback_consumed`.

## Retrieval scoring pitfall found in peer128 testing

Short operational prompts such as `check HMP health for peer128` can be too terse for broad Jaccard/bigram scoring against long registry metadata. The durable fix was a deterministic boost only for `hmp-healthcheck` when the prompt contains both:

- `hmp`
- explicit health/status/check/ping intent (`health`, `healthy`, `status`, `check`, `ping`)

This keeps short health prompts above active threshold while avoiding false positives for mutating prompts like `send a message to peer128` or `deploy the HMP plugin to peer128`.

## Reporting rule

When summarizing manual canary tests, separate:

- active retrieval result
- block result
- live invoke result
- false-positive safety result
- fallback-token result
- regression/conformance result

Also state where the plugin is actually deployed. If the plugin is on peer106 and the target is peer128, say exactly that.
