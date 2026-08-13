#!/usr/bin/env python3
"""Parity battery for HMP plugin v0.1.4 (:18643, dual-plane merged).

Tests:
  T1  /send alias accepts legacy dual-plane body {session_id, text}
  T2  Multi-turn context preserved via session_id (peer_pair_id)
  T3  Session isolation: two different session_ids do NOT mix
  T4  /hmp/send + /hmp/poll lifecycle still works (no session_id)
  T5  agent-card reports version 0.1.4 and /send endpoint
  T6  clean 404 on unknown message_id poll
Uses stdlib urllib only. Peer target: peer70 localhost.
"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:18643"


def post(path, body, timeout=180):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:  # noqa
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"raw": str(e)}


def get(path, timeout=15):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:  # noqa
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"raw": str(e)}


def send_alias(session_id, text, timeout=180):
    return post("/send", {"session_id": session_id, "text": text}, timeout=timeout)


def main():
    results = []
    def rec(name, ok, detail=""):
        results.append((name, ok, detail))
        print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))

    # T5 agent-card first (cheap, no agent roundtrip)
    st, card = get("/hmp/agent-card")
    ver = card.get("version", "")
    has_send = "/send" in card.get("endpoints", [])
    rec("T5 agent-card v0.1.4 + /send", st == 200 and ver == "0.1.4" and has_send,
        "version=%s endpoints=%s" % (ver, card.get("endpoints")))

    # T6 poll unknown -> 404
    st, body = get("/hmp/poll/definitely_unknown_id_xyz")
    rec("T6 404 on unknown poll", st == 404 and body.get("status") == "not_found",
        "http=%s body=%s" % (st, body))

    # T1 legacy /send alias
    st, resp = send_alias("parity_t1_%d" % int(time.time()), "Reply with exactly: ALIAS_OK", timeout=240)
    ok1 = st == 200 and resp.get("status") == "ok" and "ALIAS_OK" in str(resp.get("response", ""))
    rec("T1 /send alias legacy body", ok1, "http=%s resp=%s" % (st, str(resp)[:200]))

    # T2 multi-turn context in one session
    sid = "parity_t2_%d" % int(time.time())
    st, r1 = send_alias(sid, "Memorizza il numero 7.", timeout=240)
    st, r2 = send_alias(sid, "Aggiungi 3. Poi dimmi solo il numero.", timeout=240)
    ok2 = r2.get("status") == "ok" and "10" in str(r2.get("response", ""))
    rec("T2 multi-turn context (7+3=10)", ok2, "r2=%s" % str(r2.get("response", ""))[:200])

    # T3 session isolation
    sidA = "parity_t3a_%d" % int(time.time())
    sidB = "parity_t3b_%d" % int(time.time())
    send_alias(sidA, "Chiamami ALICE.", timeout=240)
    send_alias(sidB, "Chiamami BOB.", timeout=240)
    st, ra = send_alias(sidA, "Come mi chiamo? Rispondi solo col nome.", timeout=240)
    st, rb = send_alias(sidB, "E a me? Rispondi solo col nome.", timeout=240)
    ok3 = "ALICE" in str(ra.get("response", "")).upper() and "BOB" in str(rb.get("response", "")).upper()
    rec("T3 session isolation A/B", ok3, "A=%s B=%s" % (str(ra.get("response", ""))[:80], str(rb.get("response", ""))[:80]))

    # T4 classic send+poll without session_id
    mid = "parity_t4_%d" % int(time.time() * 1000)
    st, acc = post("/hmp/send", {
        "hmp_version": "1.0", "message_id": mid, "from": "parity", "to": "peer70",
        "type": "request", "timeout": 240, "payload": {"text": "Reply with exactly: POLL_OK"},
    })
    ok4 = acc.get("accepted") is True and acc.get("status") == "queued"
    deadline = time.time() + 240
    while time.time() < deadline:
        st, p = get("/hmp/poll/" + mid)
        if p.get("status") in ("completed", "failed"):
            break
        time.sleep(3)
    ok4 = ok4 and p.get("status") == "completed" and "POLL_OK" in str(p.get("response_text", ""))
    rec("T4 classic send+poll", ok4, "status=%s resp=%s" % (p.get("status"), str(p.get("response_text", ""))[:100]))

    passed = sum(1 for _, ok, _ in results if ok)
    print("\nSUMMARY: %d/%d passed" % (passed, len(results)))
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
