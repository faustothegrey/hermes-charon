# Peer Collaborative Design & Review Pattern

When designing or significantly changing the HMP protocol (or any shared infrastructure), use peer106 as a **design reviewer**. This session established a repeatable workflow.

## When to Use

- New protocol version or major architecture change
- Implementation decisions with tradeoffs (e.g. client-side vs server-side)
- Before deploying to production — get a second pair of eyes
- When stuck between two approaches — peer106 often spots blind spots

## The Pattern

### Phase 1: Implement on peer70

1. Write the PoC/implementation on peer70 (the coordinator)
2. Test locally — verify basic functionality
3. Don't polish yet — get the architecture right first

### Phase 2: Request Review via HMP

Send a message to peer106 via **HMP** (`:18643`) — not via API. Use a clear, structured request:

```
curl -s -X POST http://127.0.0.1:18643/hmp/send \
  -H "Content-Type: application/json" \
  -d "{\"message_id\":\"review_$(date +%s)\",\"from\":\"peer70\",\"to\":\"peer106\",
       \"text\":\"REVISIONE: [describe what changed, what to review, key questions]\"}"
```

Include in the message:
- What you built/why
- The specific questions you want answered
- Where the relevant files are (path on peer70)
- Any tradeoffs you're weighing

### Phase 3: Iterate

1. Wait for peer106's response (can take 30-60s)
2. Read the response carefully — peer106 is thorough
3. Fix issues found, re-test
4. Ask for a second review if the changes were significant

### Phase 4: Final Approval

Before deploying to production:
1. Get explicit "OK" from peer106
2. Bump protocol version
3. Document the final architecture
4. Send summary email to Fausto

## Observed Behavior

- peer106 is **thorough** — catches SQLite threading issues, architecture blind spots, missing fallback cases
- peer106 is **honest** — will say "this isn't ready" or "this approach is wrong" when needed
- peer106 is **slow** via HMP (10-30s), sometimes via API too — be patient
- peer106 **cannot run terminal/execute_code** in HMP/DM context — work around this by SCP-ing files first

## Tips

- **SCP files** to peer106 before asking for review on code files (peer106 can then read them locally)
- **Keep review requests short** (<500 chars) — peer106 processes them faster
- **Don't ask yes/no questions** — ask for technical opinions with reasoning
- **Challenge his conclusions** when you disagree — peer106 respects good counter-arguments
