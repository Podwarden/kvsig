#!/usr/bin/env python3
"""Conformance adapter for the Python reference implementation.

Speaks the line protocol described in conformance/README.md: one JSON request
per line on stdin, one JSON response per line on stdout.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

try:
    import kvsig
except ImportError:  # running from a checkout without an install
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
    import kvsig

from kvsig import LOOSE_V1, Key, canonicalize, canonicalize_reply, encode, ids, message_id
from kvsig.loose import loose_message

DIALECTS = list(kvsig.SUPPORTED)
LEVELS = 3


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _body(req: dict[str, Any]) -> Any:
    raw = req.get("input_raw_b64")
    if raw is not None:
        return json.loads(base64.b64decode(raw))
    return req.get("input")


def _limit(req: dict[str, Any]) -> dict[str, Any]:
    return {"max_bytes": req["max_bytes"]} if req.get("max_bytes") is not None else {}


def _form(c: Any) -> dict[str, Any]:
    return {"head": c.head, "tools": c.tools, "messages": c.messages}


def _key(req: dict[str, Any]) -> Key:
    return Key(req["epoch"], base64.b64decode(req["key_b64"]))


def _scope(req: dict[str, Any]) -> bytes:
    return base64.b64decode(req.get("scope_b64") or "")


def handle(req: dict[str, Any]) -> dict[str, Any]:
    op = req.get("op")
    if op == "info":
        return {
            "ok": True,
            "name": "kvsig-python",
            "version": getattr(kvsig, "__version__", None),
            "spec": kvsig.SPEC_LABEL,
            "levels": LEVELS,
            "dialects": DIALECTS,
        }
    if op == "scope":
        tenant = req.get("tenant_b64")
        s = kvsig.scope_from(
            cache_salt=req.get("cache_salt"),
            tenant=base64.b64decode(tenant) if tenant is not None else None,
        )
        return {"ok": True, "scope_b64": _b64(s)}
    if op == "canonicalize":
        c = canonicalize(_body(req), req["dialect"], **_limit(req))
        if c is None:
            return {"ok": True, "none": True}
        return {
            "ok": True,
            "none": False,
            "stateful": c.stateful,
            "canonical_bytes_b64": _b64(encode(_form(c))),
            "loose_bytes_b64": _b64(encode(_form(kvsig.loose(c)))),
        }
    if op == "ids":
        c = canonicalize(_body(req), req["dialect"], **_limit(req))
        if c is None:
            return {"ok": True, "none": True}
        i = ids(c, _key(req), _scope(req))
        return {
            "ok": True,
            "none": False,
            "ids": {
                "head": i.head,
                "sys": i.sys,
                "tools": i.tools,
                "msgs": list(i.msgs),
                "nodes": list(i.nodes),
                "loose_head": i.loose_head,
                "loose_sys": i.loose_sys,
                "loose_tools": i.loose_tools,
                "loose_msgs": list(i.loose_msgs),
                "loose_nodes": list(i.loose_nodes),
                "conv": i.conv,
            },
        }
    if op == "reply_id":
        resp = _body(req)
        if req["dialect"] == "openai.chat":
            # the reply is the first choice's message
            try:
                resp = resp["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                return {"ok": True, "none": True}
        m = canonicalize_reply(resp, req["dialect"], **_limit(req))
        if m is None:
            return {"ok": True, "none": True}
        key, scope = _key(req), _scope(req)
        return {
            "ok": True,
            "none": False,
            "canonical_bytes_b64": _b64(encode(m)),
            "loose_bytes_b64": _b64(encode(loose_message(m))),
            "msg": message_id(m, key, scope),
            "loose_msg": message_id(m, key, scope, profile=LOOSE_V1),
        }
    return {"ok": False, "error": f"unknown op {op!r}"}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            out = handle(json.loads(line))
        except Exception as e:  # noqa: BLE001 -- report, never crash the harness
            out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
