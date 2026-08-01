#!/usr/bin/env python3
"""
HMP Watchdog — cron script (no_agent=True)
Runs every 2m on peer70.

Checks for stalled messages (working but no heartbeat for > 5 min).
Marks them as timed_out.
"""
import sys
import os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts"))

from hmp import init_cron, STATE_TIMED_OUT, build_error

STALL_TIMEOUT = 300  # 5 min

def main():
    bus, config = init_cron()

    stalled = bus.get_stalled(max_age_seconds=STALL_TIMEOUT)
    for msg in stalled:
        err = build_error("timeout", "No heartbeat for > 5 min", cause="heartbeat_missed")
        bus.update_status(
            msg["message_id"],
            STATE_TIMED_OUT,
            cause="heartbeat_missed",
            error=err,
        )
        print(f"hmp-watchdog: {msg['message_id']} timed out (from {msg['from_peer']})")

    if not stalled:
        quiet = True  # Silenzioso se tutto ok — output vuoto = nessuna notifica
        pass

    bus.close()

if __name__ == "__main__":
    main()