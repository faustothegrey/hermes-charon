#!/usr/bin/env python3
import hashlib
f = "/home/fausto/.hermes/scripts/hmp-dual-plane.py"
with open(f, "rb") as fh:
    md5 = hashlib.md5(fh.read()).hexdigest()
print(f"File: {f}")
print(f"Linee: {len(open(f).readlines())}")
print(f"MD5: {md5}")
expected = "7b52b096a22ceae9292515f645bfd544"
print(f"Match: {'✅ SI' if md5 == expected else '❌ NO'}")
