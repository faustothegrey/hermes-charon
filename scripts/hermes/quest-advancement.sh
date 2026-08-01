# Quest Advancement Cron — Migrated from N56VV to peer70
# Run every 4h. Checks Quest tracking files and advances active quests.
#
# Quest files live under ~/Documents/Obsidian Vault/Hermes/Quests/<quest>.md
# If the vault path doesn't exist, fall back to ~/.hermes/quests-staging/
#
# Max 3 parallel quests, round-robin every 4h.