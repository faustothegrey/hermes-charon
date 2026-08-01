# Intent Advisor — Design Evolution

*From Intent Gateway (hard) to Intent Advisor (soft)*

## v1 — Intent Gateway (rejected)

A synchronous microservice that classifies every desire before code execution.
Blocks non-compliant actions. Single point of failure.
**Rejected by peer105** as "policy oracle fragile, latenza, prompt injection surface"

## v2 — Intent Advisor (accepted)

A consultative classifier that emits signals, not blocks.

| Aspect | Gateway (v1) | Advisor (v2) |
|--------|-------------|--------------|
| Role | Authorize/block | Classify/suggest |
| Latency | Synchronous on every edit | Async, pre-flight or post-hoc |
| Blocking | On any violation | Only high-risk (rm, deploy, credentials) |
| Prompt injection | Trusts the prompt | Compares declared intent vs real diff |
| Availability | Single point of failure | Fail-open for low/medium, fail-closed only high-risk |
| Output | Pass/Block | `{risk, reason, suggested_harness, confidence}` |

## Position in harness-first hierarchy

```
F1  Tool nativi           ← no advisor
F2  Harness esistenti     ← no advisor
F3  Intent ADVISOR        ← soft pre_tool_call / post_diff plugin
F4  Crea harness          ← advisor suggests if pattern repeats
F5  One-shot exemption    ← advisor classifies risk
```

## Hard block only

The advisor blocks only clearly dangerous or irreversible actions:
- rm/drop/delete on real data
- credentials/exfiltration
- auth/security modification
- deploy/prod operations
- networking/firewall changes
- destructive commands
- hidden persistence / backdoors

Everything else: warning, not block.

## Anti-prompt-injection

Classification cannot trust the prompt alone. The advisor compares:
1. Declared intent (from the prompt)
2. Files touched
3. Real diff
4. Commands executed
5. Suspicious patterns

If diff contradicts intent → raise risk and request review. Do not block (except high-risk).

## Fail-open principle

If the advisor is unavailable: allow low/medium risk, block only predefined high-risk. It must be a library/tool, not a mandatory central service.

## Consensus

All peers (106, 105, 58) agreed on the soft mode approach. peer58: "Non deve diventare un altro orchestratore." peer105: "Se è un vincolo cieco e sincrono su ogni modifica, no."
