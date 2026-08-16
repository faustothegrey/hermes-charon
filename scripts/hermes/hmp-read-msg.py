#!/usr/bin/env python3
"""hmp-read-msg.py — legge messaggi HMP dal DB INTEGRO (mai dal log).

Il log del gateway mostra solo una preview troncata (80 chars) e NON il
message_id: leggere i messaggi dal log è la causa di falsi "troncamenti"
(messaggi che in realtà sono arrivati integri). Il DB
~/.hermes/data/hmp_gateway_plugin/messages.db contiene il campo `text`
integrale.

Uso:
  hmp-read-msg.py <message_id>          # messaggio specifico (testo integro)
  hmp-read-msg.py --last [peer]         # ultimo messaggio (da un peer)
  hmp-read-msg.py --from <peer> [N]     # ultimi N messaggi da un peer
  hmp-read-msg.py --db PATH             # path db alternativo

Esce 0 se trovato, 1 se non trovato.
"""
import argparse
import json
import os
import sqlite3
import sys

DEFAULT_DB = os.path.join(
    os.path.expanduser("~/.hermes"), "data", "hmp_gateway_plugin", "messages.db"
)


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def show(con: sqlite3.Connection, row: sqlite3.Row) -> None:
    d = dict(row)
    print(f"message_id: {d.get('message_id')}")
    print(f"from: {d.get('from_peer')} -> to: {d.get('to_peer')} | status: {d.get('status')}")
    print(f"len text: {len(d.get('text') or '')}")
    print("--- TESTO INTEGRALE ---")
    print(d.get("text") or "")
    print("--- FINE (integrale) ---")
    if d.get("response_text"):
        print(f"--- RISPOSTA ({len(d.get('response_text') or '')} chars) ---")
        print(d.get("response_text"))
        print("--- FINE RISPOSTA ---")


def main() -> int:
    ap = argparse.ArgumentParser(description="Leggi messaggi HMP dal DB (integro).")
    ap.add_argument("message_id", nargs="?", help="message_id specifico")
    ap.add_argument("--last", metavar="PEER", nargs="?", const="", help="ultimo messaggio (da un peer)")
    ap.add_argument("--from", dest="from_peer", metavar="PEER", help="messaggi da un peer")
    ap.add_argument("--db", default=DEFAULT_DB, help="path db alternativo")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"ERRORE: db non trovato: {args.db}", file=sys.stderr)
        return 2

    con = connect(args.db)

    if args.message_id:
        cur = con.execute(
            "SELECT * FROM hmp_gateway_messages WHERE message_id = ?", (args.message_id,)
        )
        row = cur.fetchone()
        if not row:
            print(f"non trovato: {args.message_id}", file=sys.stderr)
            return 1
        show(con, row)
        return 0

    if args.last is not None:
        if args.last:
            cur = con.execute(
                "SELECT * FROM hmp_gateway_messages WHERE from_peer = ? ORDER BY rowid DESC LIMIT 1",
                (args.last,),
            )
        else:
            cur = con.execute("SELECT * FROM hmp_gateway_messages ORDER BY rowid DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("nessun messaggio trovato", file=sys.stderr)
            return 1
        show(con, row)
        return 0

    if args.from_peer:
        cur = con.execute(
            "SELECT * FROM hmp_gateway_messages WHERE from_peer = ? ORDER BY rowid DESC LIMIT 5",
            (args.from_peer,),
        )
        rows = cur.fetchall()
        if not rows:
            print(f"nessun messaggio da {args.from_peer}", file=sys.stderr)
            return 1
        for row in rows:
            show(con, row)
            print()
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
