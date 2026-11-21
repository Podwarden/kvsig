#!/usr/bin/env python3
"""kvsig conformance runner.

    python conformance/run.py [options] -- <adapter command ...>

Starts the adapter, sends it one JSON request per line, compares every answer
with the test vectors under ``vectors/v1`` and prints a pass/fail table per
level and dialect. Exit status: 0 all pass, 1 failures, 2 setup error.
Standard library only. See conformance/README.md for the protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VECTORS = ROOT / "vectors" / "v1"

EXACT_FIELDS = ("head", "sys", "tools", "msgs", "nodes")
LOOSE_FIELDS = ("loose_head", "loose_sys", "loose_tools", "loose_msgs", "loose_nodes", "conv")


class Adapter:
    def __init__(self, cmd: list[str]) -> None:
        self.p = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8"
        )

    def call(self, req: dict[str, Any]) -> dict[str, Any]:
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError("adapter closed its output")
        out = json.loads(line)
        if not out.get("ok"):
            raise RuntimeError(f"adapter error: {out.get('error')}")
        return out

    def close(self) -> None:
        if self.p.stdin:
            self.p.stdin.close()
        self.p.wait(timeout=10)


def check_manifest(vdir: Path) -> list[str]:
    """Problems between ``manifest.json`` and the files on disk."""
    man = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    listed = {f["path"]: f["sha256"] for f in man["files"]}
    problems = []
    on_disk = {
        p.relative_to(vdir).as_posix()
        for p in vdir.rglob("*")
        if p.is_file() and p.name != "manifest.json" and p.suffix == ".json"
    }
    for path in sorted(on_disk - set(listed)):
        problems.append(f"not in the manifest: {path}")
    for path, digest in sorted(listed.items()):
        f = vdir / path
        if not f.is_file():
            problems.append(f"listed but missing: {path}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            problems.append(f"hash differs: {path}")
    return problems


def load(vdir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    man = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    vecs = [json.loads((vdir / f["path"]).read_text(encoding="utf-8")) for f in man["files"]]
    return man, vecs


def request(v: dict[str, Any], op: str, **extra: Any) -> dict[str, Any]:
    r: dict[str, Any] = {"op": op, "dialect": v["dialect"], **extra}
    r["input"] = v.get("input")
    if v.get("input_raw_b64") is not None:
        r["input_raw_b64"] = v["input_raw_b64"]
    mb = v.get("options", {}).get("max_bytes")
    if mb is not None:
        r["max_bytes"] = mb
    return r


def run_vector(a: Adapter, v: dict[str, Any], keys: list[dict[str, Any]], level: int) -> str | None:
    """None when the vector passes, else the first difference."""
    exp = v["expect"]
    sc = v.get("scope") or {}
    scope_b64 = sc.get("scope_b64", "")
    if sc.get("cache_salt") is not None or sc.get("tenant_b64") is not None:
        got = a.call(
            {"op": "scope", "cache_salt": sc.get("cache_salt"), "tenant_b64": sc.get("tenant_b64")}
        )
        if got["scope_b64"] != scope_b64:
            return f"scope: got {got['scope_b64']!r}, want {scope_b64!r}"

    got = a.call(request(v, "canonicalize"))
    if exp.get("none"):
        if not got["none"]:
            return "canonicalize: expected no ids, got a canonical form"
    else:
        if got["none"]:
            return "canonicalize: got no ids, expected a canonical form"
        if got["canonical_bytes_b64"] != exp["canonical_bytes_b64"]:
            return "canonical bytes differ"
        if got["stateful"] != exp["stateful"]:
            return f"stateful: got {got['stateful']}, want {exp['stateful']}"
        if level >= 2 and got["loose_bytes_b64"] != exp["loose_bytes_b64"]:
            return "loose bytes differ"

    fields = EXACT_FIELDS + (LOOSE_FIELDS if level >= 2 else ())
    for k in keys:
        epoch = str(k["epoch"])
        got = a.call(request(v, "ids", key_b64=k["key_b64"], epoch=k["epoch"], scope_b64=scope_b64))
        if exp.get("none"):
            if not got["none"]:
                return f"ids (epoch {epoch}): expected no ids"
            continue
        if got["none"]:
            return f"ids (epoch {epoch}): got no ids"
        want = exp["keys"][epoch]
        for f in fields:
            if got["ids"].get(f) != want[f]:
                return f"ids (epoch {epoch}) {f}: got {got['ids'].get(f)!r}, want {want[f]!r}"

    rp = v.get("reply")
    if rp is not None and level >= 3:
        for k in keys:
            epoch = str(k["epoch"])
            r = {
                "op": "reply_id",
                "dialect": v["dialect"],
                "input": rp["response"],
                "key_b64": k["key_b64"],
                "epoch": k["epoch"],
                "scope_b64": scope_b64,
            }
            got = a.call(r)
            if got["none"]:
                return "reply_id: got no id"
            if got["canonical_bytes_b64"] != rp["canonical_bytes_b64"]:
                return "reply canonical bytes differ"
            want = rp["keys"][epoch]
            for f in ("msg", "loose_msg"):
                if got[f] != want[f]:
                    return f"reply (epoch {epoch}) {f}: got {got[f]!r}, want {want[f]!r}"
    return None


def relation_problems(vecs: list[dict[str, Any]]) -> list[str]:
    """Self-consistency of the vector set: equivalences and relations hold on
    the expected values themselves."""
    by_id = {v["id"]: v for v in vecs}
    out = []
    for v in vecs:
        for o in v.get("equivalent_to", []):
            w = by_id.get(o)
            if w is None:
                out.append(f"{v['id']}: equivalent_to unknown vector {o}")
            elif w["expect"].get("canonical_bytes_b64") != v["expect"].get("canonical_bytes_b64"):
                out.append(f"{v['id']}: not equivalent to {o}")
        for rel in v.get("relations", []):
            w = by_id.get(rel["other"])
            if w is None:
                out.append(f"{v['id']}: relation to unknown vector {rel['other']}")
                continue
            for epoch, ks in v["expect"].get("keys", {}).items():
                same = ks[rel["field"]] == w["expect"]["keys"][epoch][rel["field"]]
                if same != rel["same"]:
                    out.append(f"{v['id']}: {rel['field']} vs {rel['other']}: same={same}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    ap.add_argument("--level", type=int, help="level to test (default: what the adapter declares)")
    ap.add_argument("--only", help="run only vectors whose id contains this text")
    ap.add_argument(
        "--manifest-only",
        action="store_true",
        help="only check the manifest hashes against the files, then exit",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="list every failure")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- adapter command")
    args = ap.parse_args()
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd and not args.manifest_only:
        ap.error("give the adapter command after --")

    problems = check_manifest(args.vectors)
    if problems:
        print(
            "manifest check failed (regenerate with vectors/tools/generate.py):",
            *problems,
            sep="\n  ",
        )
        return 2
    if args.manifest_only:
        print("manifest matches the files")
        return 0
    man, vecs = load(args.vectors)
    rel = relation_problems(vecs)
    if rel:
        print("vector set is not self-consistent:", *rel, sep="\n  ")
        return 2
    keys = man["keys"]

    a = Adapter(cmd)
    try:
        info = a.call({"op": "info"})
        level = args.level or info["levels"]
        dialects = list(info["dialects"])
        print(
            f"adapter {info.get('name')}  spec {info.get('spec')}  level {level}  "
            f"dialects {', '.join(dialects)}"
        )
        cells: dict[tuple[int, str], list[int]] = {}
        failures = []
        for v in vecs:
            if v["dialect"] not in dialects or v["level"] > level:
                continue
            if args.only and args.only not in v["id"]:
                continue
            try:
                why = run_vector(a, v, keys, level)
            except Exception as e:  # noqa: BLE001
                why = f"{type(e).__name__}: {e}"
            c = cells.setdefault((v["level"], v["dialect"]), [0, 0])
            c[1] += 1
            if why is None:
                c[0] += 1
            else:
                failures.append((v["id"], why))
    finally:
        a.close()

    width = max([len(d) for d in dialects] + [9]) + 2
    print()
    print("level".ljust(7) + "".join(d.rjust(width) for d in dialects) + "total".rjust(width))
    tp = tt = 0
    for lv in range(1, level + 1):
        row = "".ljust(0) + f"L{lv}".ljust(7)
        rp = rt = 0
        for d in dialects:
            p, t = cells.get((lv, d), [0, 0])
            rp, rt = rp + p, rt + t
            row += (f"{p}/{t}" if t else "-").rjust(width)
        row += f"{rp}/{rt}".rjust(width)
        print(row)
        tp, tt = tp + rp, tt + rt
    print(f"\n{tp}/{tt} passed, {len(failures)} failed")
    shown = failures if args.verbose else failures[:15]
    for vid, why in shown:
        print(f"FAIL {vid}: {why[:300]}")
    if len(failures) > len(shown):
        print(f"... {len(failures) - len(shown)} more (use -v)")
    if not failures:
        print(f"Level {level} conformant for: {', '.join(dialects)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
