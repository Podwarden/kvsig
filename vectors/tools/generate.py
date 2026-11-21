#!/usr/bin/env python3
"""Build vectors/v1 from the case definitions with the reference implementation.

    python vectors/tools/generate.py           write vectors/v1 and manifest.json
    python vectors/tools/generate.py --check   regenerate in memory, fail on any difference

Needs cbor2 (to render the canonical form as readable JSON). Format: see
docs/decisions/0004-test-vectors.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "conformance" / "adapters"))
sys.path.insert(0, str(ROOT / "python" / "src"))

import cases  # noqa: E402
import cases_hand  # noqa: E402, F401
import cases_reply  # noqa: E402, F401
import cbor2  # noqa: E402
import kvsig  # noqa: E402
import python_adapter as ref  # noqa: E402

OUT = ROOT / "vectors" / "v1"
SPEC = "kvsig/1"
FORMAT = 1
TEST_KEYS = [
    {"name": "test-0", "epoch": 0, "key_hex": bytes(range(32)).hex()},
    {"name": "test-255", "epoch": 255, "key_hex": bytes(range(32, 64)).hex()},
]
for _k in TEST_KEYS:
    _k["key_b64"] = base64.b64encode(bytes.fromhex(_k["key_hex"])).decode()
DEFAULT_MAX = kvsig.DEFAULT_MAX_BYTES


def render(o: Any) -> Any:
    """The readable JSON form of a canonical structure: bytes become {"$hex": ...}."""
    if isinstance(o, bytes):
        return {"$hex": o.hex()}
    if isinstance(o, dict):
        return {k: render(v) for k, v in o.items()}
    if isinstance(o, list):
        return [render(v) for v in o]
    return o


def b64(s: str) -> bytes:
    return base64.b64decode(s)


def dump(o: Any) -> bytes:
    return (json.dumps(o, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def fail(msg: str) -> None:
    raise SystemExit(f"generate: {msg}")


def build(c: dict[str, Any]) -> dict[str, Any]:
    v: dict[str, Any] = {
        "id": c["id"],
        "spec": SPEC,
        "level": c["level"],
        "dialect": c["dialect"],
        "category": c["category"],
        "description": c["description"],
    }
    opts = dict(c["options"] or {})
    if c["raw"] is not None:
        raw_b = c["raw"].encode("utf-8")
        body_in = json.loads(raw_b)
        v["input"], v["input_raw_b64"] = None, base64.b64encode(raw_b).decode()
    else:
        body_in = c["body"]
        v["input"], v["input_raw_b64"] = c["body"], None
    if opts.get("max_bytes") in ("AT", "UNDER"):
        canon = kvsig.canonicalize(body_in, c["dialect"])
        if canon is None:
            fail(f"{c['id']}: size probe has no canonical form")
        n = len(kvsig.encode(canon.head_payload())) + sum(
            len(kvsig.encode(m)) for m in canon.messages
        )
        opts["max_bytes"] = n if opts["max_bytes"] == "AT" else n - 1
    if opts:
        v["options"] = opts
    sc = c["scope"] or {}
    scope: dict[str, Any] = {
        "cache_salt": sc.get("cache_salt"),
        "tenant_b64": None,
        "scope_b64": "",
    }
    if sc.get("tenant") is not None:
        scope["tenant_b64"] = base64.b64encode(sc["tenant"]).decode()
    if sc:
        got = ref.handle(
            {"op": "scope", "cache_salt": scope["cache_salt"], "tenant_b64": scope["tenant_b64"]}
        )
        scope["scope_b64"] = got["scope_b64"]
        v["scope"] = scope

    req: dict[str, Any] = {
        "dialect": c["dialect"],
        "input": v["input"],
        "input_raw_b64": v["input_raw_b64"],
    }
    if "max_bytes" in opts:
        req["max_bytes"] = opts["max_bytes"]
    canon = ref.handle({"op": "canonicalize", **req})
    if canon["none"]:
        v["expect"] = {"none": True}
    else:
        cb, lb = b64(canon["canonical_bytes_b64"]), b64(canon["loose_bytes_b64"])
        exp: dict[str, Any] = {
            "none": False,
            "stateful": canon["stateful"],
            "canonical": render(cbor2.loads(cb)),
            "canonical_bytes_b64": canon["canonical_bytes_b64"],
            "loose": render(cbor2.loads(lb)),
            "loose_bytes_b64": canon["loose_bytes_b64"],
            "keys": {},
        }
        for k in TEST_KEYS:
            r = ref.handle(
                {
                    "op": "ids",
                    **req,
                    "key_b64": k["key_b64"],
                    "epoch": k["epoch"],
                    "scope_b64": scope["scope_b64"],
                }
            )
            exp["keys"][str(k["epoch"])] = r["ids"]
        v["expect"] = exp
    if c["reply"] is not None:
        v["reply"] = build_reply(c, v, scope["scope_b64"])
    return v


def build_reply(c: dict[str, Any], v: dict[str, Any], scope_b64: str) -> dict[str, Any]:
    rp = c["reply"]
    out: dict[str, Any] = {
        "response": rp["response"],
        "matches_msg_index": rp["index"],
        "exact": rp["exact"],
        "keys": {},
    }
    for k in TEST_KEYS:
        r = ref.handle(
            {
                "op": "reply_id",
                "dialect": c["dialect"],
                "input": rp["response"],
                "key_b64": k["key_b64"],
                "epoch": k["epoch"],
                "scope_b64": scope_b64,
            }
        )
        if r["none"]:
            fail(f"{c['id']}: reply gave no id")
        out["canonical_bytes_b64"] = r["canonical_bytes_b64"]
        out["canonical"] = render(cbor2.loads(b64(r["canonical_bytes_b64"])))
        out["keys"][str(k["epoch"])] = {"msg": r["msg"], "loose_msg": r["loose_msg"]}
        ks = v["expect"]["keys"][str(k["epoch"])]
        i = rp["index"]
        if r["loose_msg"] != ks["loose_msgs"][i]:
            fail(f"{c['id']}: reply loose id does not match request message {i}")
        if rp["exact"] and r["msg"] != ks["msgs"][i]:
            fail(f"{c['id']}: reply exact id does not match request message {i}")
        if not rp["exact"] and r["msg"] == ks["msgs"][i]:
            fail(f"{c['id']}: marked exact=false but the exact ids match")
    return out


def check_relations(vs: dict[str, dict[str, Any]]) -> None:
    for v in vs.values():
        for rel in v.get("relations", []):
            w = vs.get(rel["other"])
            if w is None:
                fail(f"{v['id']}: unknown relation target {rel['other']}")
            if v["expect"].get("none") or w["expect"].get("none"):
                fail(f"{v['id']}: relation on a no-ids vector")
            for epoch, ks in v["expect"]["keys"].items():
                same = ks[rel["field"]] == w["expect"]["keys"][epoch][rel["field"]]
                if same != rel["same"]:
                    fail(
                        f"{v['id']}: relation {rel['field']} vs {rel['other']} "
                        f"expected same={rel['same']}, got {same}"
                    )


def generate() -> dict[str, bytes]:
    ids = [c["id"] for c in cases.CASES]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        fail(f"duplicate case ids: {sorted(dup)}")
    vs: dict[str, dict[str, Any]] = {}
    for c in cases.CASES:
        v = build(c)
        v["relations"] = list(c["relations"])
        vs[v["id"]] = v
    # cross-dialect equivalence: every group shares one canonical form
    for g in cases.GROUPS:
        outs = {json.dumps(vs[i]["expect"].get("canonical_bytes_b64")) for i in g}
        if len(outs) != 1:
            fail(f"not equivalent across dialects: {g}")
        for i in g:
            vs[i]["equivalent_to"] = [j for j in g if j != i]
    check_relations(vs)
    files: dict[str, bytes] = {}
    entries = []
    for vid in sorted(vs):
        v = vs[vid]
        if not v.get("relations"):
            v.pop("relations", None)
        order = [
            "id",
            "spec",
            "level",
            "dialect",
            "category",
            "description",
            "options",
            "input",
            "input_raw_b64",
            "scope",
            "expect",
            "equivalent_to",
            "relations",
            "reply",
        ]
        v = {k: v[k] for k in order if k in v}
        path = f"{vid}.json"
        data = dump(v)
        files[path] = data
        entries.append(
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "level": v["level"],
                "dialect": v["dialect"],
                "category": v["category"],
            }
        )
    manifest = {
        "spec": SPEC,
        "format": FORMAT,
        "loose": "loose/1",
        "status": "draft",
        "keys": TEST_KEYS,
        "count": len(entries),
        "files": entries,
    }
    files["manifest.json"] = dump(manifest)
    return files


def main() -> int:
    files = generate()
    if "--check" in sys.argv:
        bad = []
        on_disk = {p.relative_to(OUT).as_posix() for p in OUT.rglob("*.json")}
        for path in sorted(on_disk - set(files)):
            bad.append(f"stale file: {path}")
        for path, data in sorted(files.items()):
            f = OUT / path
            if not f.is_file():
                bad.append(f"missing: {path}")
            elif f.read_bytes() != data:
                bad.append(f"differs: {path}")
        if bad:
            print("vectors/v1 does not match the generator; run vectors/tools/generate.py")
            print(*bad[:40], sep="\n  ")
            return 1
        print(f"vectors/v1 is up to date ({len(files) - 1} vectors)")
        return 0
    for p in OUT.rglob("*.json"):
        p.unlink()
    for path, data in files.items():
        f = OUT / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    print(f"wrote {len(files) - 1} vectors and manifest.json to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
