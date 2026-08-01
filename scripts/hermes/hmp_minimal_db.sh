#!/bin/bash
echo "=== MINIMAL DB TEST ==="
python3 -c "import sqlite3; c = sqlite3.connect('/home/fausto/.hermes/data/hmp/agent_messages.db'); print('DB opened'); c.close(); print('OK')"
echo "DONE"