#!/usr/bin/env python3
"""
HMP Dream Engine — cron script (no_agent=True)
Runs daily at 02:00 CEST on peer70.

1. Archives messages older than 30 days (deletes terminal states)
2. Cleans up idempotency keys older than 7 days
3. Compacts the SQLite database (VACUUM + WAL checkpoint)
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/.hermes/skills/autonomous-ai-agents/hmp-protocol/scripts"))

from hmp import init_cron

def main():
    bus, config = init_cron()

    # Archive old messages (terminal states, > 30 days)
    archived = bus.archive_old_messages(days=30)
    print(f"hmp-dream-engine: archived {archived} terminal messages older than 30 days")

    # Cleanup idempotency keys (any state, > 7 days)
    cleaned = bus.cleanup_idempotency_keys(days=7)
    print(f"hmp-dream-engine: cleaned {cleaned} idempotency records older than 7 days")

    # Compact
    bus.compact()
    print("hmp-dream-engine: VACUUM complete")

    # Stats
    pending = bus.count_pending()
    print(f"hmp-dream-engine: {pending} pending/queued messages remaining")

    bus.close()

if __name__ == "__main__":
    main()