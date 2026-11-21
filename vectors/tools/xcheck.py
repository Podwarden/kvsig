#!/usr/bin/env python3
"""Independent cross-check of the vectors.

Re-derives, for every vector that has ids, the canonical bytes from the readable
canonical form (cbor2, canonical mode), the loose form (a second implementation of the
loose/1 rules, written from decision 0002), and every id with a hand-built HMAC, exactly
as decision 0002 defines. It never imports kvsig. Any mismatch is a bug in the library,
the vectors or the spec text: the exit status is 1 and each mismatch is printed.

    python vectors/tools/xcheck.py [--vectors vectors/v1]      (needs cbor2)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cbor2

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- bytes and ids
def unrender(o: Any) -> Any:
    if isinstance(o, dict):
        if set(o) == {"$hex"}:
            return bytes.fromhex(o["$hex"])
        return {k: unrender(v) for k, v in o.items()}
    if isinstance(o, list):
        return [unrender(v) for v in o]
    return o


def cbor(o: Any) -> bytes:
    return cbor2.dumps(o, canonical=True)


def H(key: bytes, epoch: int, label: str, scope: bytes, payload: bytes) -> bytes:
    msg = b"kvsig/1" + b"\x00" + label.encode() + b"\x00" + bytes([len(scope)]) + scope + payload
    return bytes([epoch]) + hmac.new(key, msg, hashlib.sha256).digest()[:16]


# ---------------------------------------------------------------- loose/1, second implementation
# Unicode White_Space plus U+001C..U+001F, listed from the Unicode character database.
WS = set(
    [0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680]
    + list(range(0x2000, 0x200B))
    + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000]
)
ASCII_LOWER = {i: i + 32 for i in range(ord("A"), ord("Z") + 1)}
BLOCKS = [
    ("<system-reminder>", "</system-reminder>"),
    ("<environment_context>", "</environment_context>"),
]
DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
TIME = r"[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?"
DATE_LINE = re.compile(r"[ \t]*" + DATE + "(?:" + TIME + r")?[ \t]*")


def strip_blocks(text: str, open_tag: str, close_tag: str) -> str:
    low = text.translate(ASCII_LOWER)  # same length: ASCII-only lowering
    out, pos = [], 0
    while True:
        i = low.find(open_tag, pos)
        if i < 0:
            break
        j = low.find(close_tag, i + len(open_tag))
        if j < 0:
            break  # unclosed: the rest stays
        out.append(text[pos:i])
        pos = j + len(close_tag)
    out.append(text[pos:])
    return "".join(out)


def loose_text(t: str) -> str:
    for o, c in BLOCKS:
        t = strip_blocks(t, o, c)
    t = "\n".join(line for line in t.split("\n") if not DATE_LINE.fullmatch(line))
    words, cur = [], []
    for ch in t:
        if ord(ch) in WS:
            if cur:
                words.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        words.append("".join(cur))
    return " ".join(words)


class Num(str):
    pass


def resort(text: str) -> str:
    v = json.loads(
        text,
        parse_float=Num,
        parse_int=Num,
        object_pairs_hook=lambda ps: dict(sorted(ps, key=lambda kv: kv[0])),
    )

    def dump(x: Any) -> str:
        if isinstance(x, Num):
            return str(x)
        if isinstance(x, dict):
            return (
                "{"
                + ",".join(json.dumps(k, ensure_ascii=False) + ":" + dump(y) for k, y in x.items())
                + "}"
            )
        if isinstance(x, list):
            return "[" + ",".join(dump(y) for y in x) + "]"
        return json.dumps(x, ensure_ascii=False)

    return dump(v)


def loose_parts(parts: list[Any]) -> list[Any]:
    out = []
    for p in parts:
        t = p["t"]
        if t == "reasoning":
            continue
        if t == "text":
            v = loose_text(p["v"])
            if v:
                out.append({"t": "text", "v": v})
        elif t == "tool_result":
            out.append({**p, "parts": loose_parts(p["parts"])})
        elif t == "tool_call" and "args" in p:
            out.append({**p, "args": resort(p["args"])})
        else:
            out.append(p)
    return out


def loose_msg(m: dict[str, Any]) -> dict[str, Any]:
    return {**m, "parts": loose_parts(m["parts"])}


def loose_tool(t: dict[str, Any]) -> dict[str, Any]:
    if "schema" in t:
        return {**t, "schema": resort(t["schema"])}
    return {**t, "def": resort(t["def"])}


def loose_form(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "head": [loose_msg(m) for m in c["head"]],
        "tools": [loose_tool(t) for t in c["tools"]],
        "messages": [loose_msg(m) for m in c["messages"]],
    }


# ---------------------------------------------------------------- ids
def derive_ids(
    form: dict[str, Any],
    loose: dict[str, Any],
    key: bytes,
    epoch: int,
    scope: bytes,
    stateful: bool,
) -> dict[str, Any]:
    def h(label: str, payload: bytes) -> bytes:
        return H(key, epoch, label, scope, payload)

    head = h("head", cbor({"head": form["head"], "tools": form["tools"]}))
    lhead = h("loose/1:head", cbor({"head": loose["head"], "tools": loose["tools"]}))
    msgs = [h("msg", cbor(m)) for m in form["messages"]]
    lmsgs = [h("loose/1:msg", cbor(m)) for m in loose["messages"]]
    nodes, lnodes = [], []
    prev, lprev = head, lhead
    for m, lm in zip(msgs, lmsgs, strict=True):
        prev = h("node", prev + m)
        lprev = h("loose/1:node", lprev + lm)
        nodes.append(prev)
        lnodes.append(lprev)
    lsys = h("loose/1:sys", cbor({"head": loose["head"]}))
    anchor = next((lm for lm, m in zip(lmsgs, loose["messages"], strict=True) if m["parts"]), None)
    conv = None
    if anchor is not None and not stateful:
        conv = h("loose/1:conv", lsys + anchor).hex()
    return {
        "head": head.hex(),
        "sys": h("sys", cbor({"head": form["head"]})).hex(),
        "tools": h("tools", cbor({"tools": form["tools"]})).hex(),
        "msgs": [x.hex() for x in msgs],
        "nodes": [] if stateful else [x.hex() for x in nodes],
        "loose_head": lhead.hex(),
        "loose_sys": lsys.hex(),
        "loose_tools": h("loose/1:tools", cbor({"tools": loose["tools"]})).hex(),
        "loose_msgs": [x.hex() for x in lmsgs],
        "loose_nodes": [] if stateful else [x.hex() for x in lnodes],
        "conv": conv,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vectors", type=Path, default=ROOT / "vectors" / "v1")
    args = ap.parse_args()
    man = json.loads((args.vectors / "manifest.json").read_text())
    keys = {k["epoch"]: bytes.fromhex(k["key_hex"]) for k in man["keys"]}
    bad: list[str] = []
    done: Counter[str] = Counter()
    ids_checked = 0

    def check(vid: str, what: str, got: Any, want: Any) -> None:
        if got != want:
            bad.append(f"{vid}: {what}: independent {got!r} != vector {want!r}")

    for f in man["files"]:
        v = json.loads((args.vectors / f["path"]).read_text())
        exp = v["expect"]
        if exp.get("none"):
            continue
        vid = v["id"]
        form = unrender(exp["canonical"])
        check(
            vid,
            "canonical bytes",
            base64.b64encode(cbor(form)).decode(),
            exp["canonical_bytes_b64"],
        )
        loose = loose_form(form)
        check(vid, "loose form", loose, unrender(exp["loose"]))
        check(vid, "loose bytes", base64.b64encode(cbor(loose)).decode(), exp["loose_bytes_b64"])
        sc = v.get("scope") or {}
        scope = base64.b64decode(sc.get("scope_b64", ""))
        if sc.get("cache_salt") or sc.get("tenant_b64"):
            m: dict[str, Any] = {}
            if sc.get("cache_salt"):
                m["cache_salt"] = sc["cache_salt"]
            if sc.get("tenant_b64"):
                m["tenant"] = base64.b64decode(sc["tenant_b64"])
            check(vid, "scope", hashlib.sha256(cbor(m)).digest(), scope)
        for epoch, want in exp["keys"].items():
            got = derive_ids(form, loose, keys[int(epoch)], int(epoch), scope, exp["stateful"])
            for fld, val in got.items():
                check(vid, f"epoch {epoch} {fld}", val, want[fld])
                ids_checked += 1
            rp = v.get("reply")
            if rp:
                rf = unrender(rp["canonical"])
                check(
                    vid,
                    "reply canonical bytes",
                    base64.b64encode(cbor(rf)).decode(),
                    rp["canonical_bytes_b64"],
                )
                kk = keys[int(epoch)]
                check(
                    vid,
                    f"epoch {epoch} reply msg",
                    H(kk, int(epoch), "msg", scope, cbor(rf)).hex(),
                    rp["keys"][epoch]["msg"],
                )
                check(
                    vid,
                    f"epoch {epoch} reply loose_msg",
                    H(kk, int(epoch), "loose/1:msg", scope, cbor(loose_msg(rf))).hex(),
                    rp["keys"][epoch]["loose_msg"],
                )
        done[v["category"]] += 1
    n = sum(done.values())
    print(
        f"re-derived {n} vectors ({ids_checked} id values) in {len(done)} categories, "
        f"{len(bad)} mismatches"
    )
    print("categories:", ", ".join(f"{k}={c}" for k, c in sorted(done.items())))
    for line in bad[:40]:
        print("MISMATCH", line)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
