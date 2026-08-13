# Runtime evidence status — capability-reuse

Updated after external review, 2026-07-27.

## Current evidence split

| Evidence class | Status | Meaning |
|---|---:|---|
| Local controller conformance | 15/15 PASS | Unit/integration harness exercises plugin registration, callbacks, protocol state machine, injection rendering, block-origin constants, token behavior, and simulated dispatch seams. |
| Active-path regression tests | PASS | Source test suite validates six external-review blockers and selected canary behavior. |
| Pinned Hermes runtime conformance | PENDING/PARTIAL | Not yet proven across a real pinned Hermes CLI/gateway/delegated execution path with raw runtime artifacts. |

The local conformance suite is useful implementation evidence, but it is not formal C8 closure evidence by itself. Do not report local harness 15/15 as full pinned-runtime conformance.

## Required pinned-runtime evidence for formal C8

For each deployment surface being claimed, collect raw artifacts showing:

1. plugin artifact discovered once and registered by the actual PluginManager;
2. `pre_llm_call` fires once per real user turn and injection reaches the current model context in active mode;
3. `pre_tool_call` fires exactly once per underlying `execute_code` handler call;
4. `{ "action": "block", ... }` from the real hook prevents actual handler execution;
5. `post_tool_call` fires for success, failure, and blocked outcomes with stable identifiers;
6. session/task/tool/turn identifiers are stable enough for correlation, including degraded cases where `turn_id` is absent;
7. concurrent tool calls cannot double-claim one intervention under the actual runtime scheduler;
8. plugin exceptions/timeouts fail open in the real runtime;
9. gateway/CLI/delegated surfaces are separately evidenced, not assumed equivalent;
10. raw event chains and deployment manifests include hashes, runtime version, command line, and timestamps.

## Known caveats

- In-memory intervention state is single-process canary state. Multi-worker gateways or process restarts require a shared transactional store before formal active enforcement.
- Missing `turn_id` is supported with TTL and pre-LLM next-turn cleanup, but formal active rollout still requires pinned-runtime proof that hook-visible identifiers are sufficient.
- Local hook latency is not enough for formal C9; live runtime latency distributions are still required.
