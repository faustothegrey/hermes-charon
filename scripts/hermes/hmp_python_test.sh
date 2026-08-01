#!/bin/bash
echo "python3 path: $(command -v python3)"
echo "python3 version: $(python3 --version 2>&1)"
echo "test db access:"
python3 -c "import sqlite3; print('sqlite3 ok')"
echo "ALL GOOD"