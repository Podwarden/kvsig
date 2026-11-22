"""The loose profile: the canonical form without harness noise.

The table is data. Any change to it is a new profile version, and the version
is part of every loose id label, so ids from different tables never compare
equal by accident.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from kvsig import jsontext
from kvsig.cbor import encode
from kvsig.model import Canon, Message, Part

#: The whitespace set the loose profile collapses: the code points for which
#: Python's ``str.isspace`` is true (Unicode White_Space plus U+001C..U+001F).
WHITESPACE_V1 = frozenset(
    (
        0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x001C, 0x001D, 0x001E, 0x001F, 0x0020,
        0x0085, 0x00A0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
        0x2007, 0x2008, 0x2009, 0x200A, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
    )
)  # fmt: skip


@dataclass(frozen=True)
class LooseProfile:
    """A loose-profile table. Validated on construction."""

    version: str
    #: (open tag, close tag) blocks removed from text, matched ASCII case-insensitively
    block_tags: tuple[tuple[str, str], ...]
    whitespace: frozenset[int]
    #: (from, to) message roles: a message whose role is ``from`` reads as
    #: ``to`` in the loose form. Empty in ``loose/1``.
    role_map: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.version or "\x00" in self.version or ":" in self.version:
            raise ValueError("version must be a non-empty label without NUL or ':'")
        for pair in self.block_tags:
            if len(pair) != 2 or not all(isinstance(t, str) and t for t in pair):
                raise ValueError("block_tags must be (open, close) pairs of non-empty strings")
        if not self.whitespace or not all(
            isinstance(c, int) and 0 <= c <= 0x10FFFF and not 0xD800 <= c <= 0xDFFF
            for c in self.whitespace
        ):
            raise ValueError("whitespace must be a non-empty set of Unicode scalar values")
        for pair in self.role_map:
            if len(pair) != 2 or not all(isinstance(r, str) and r for r in pair):
                raise ValueError("role_map must be (from, to) pairs of non-empty strings")
        if len({f for f, _ in self.role_map}) != len(self.role_map):
            raise ValueError("role_map must map each role at most once")

    @property
    def fingerprint(self) -> bytes:
        """8 bytes that change with any part of the table (used to key caches)."""
        return _compiled(self).fingerprint


LOOSE_V1 = LooseProfile(
    version="loose/1",
    block_tags=(
        ("<system-reminder>", "</system-reminder>"),
        ("<environment_context>", "</environment_context>"),
    ),
    whitespace=WHITESPACE_V1,
)

#: ``loose/1`` plus one rule: a ``developer`` message reads as a ``system``
#: message (decision 0005, proposed). Not the default while 0005 is open.
LOOSE_V2 = LooseProfile(
    version="loose/2",
    block_tags=LOOSE_V1.block_tags,
    whitespace=WHITESPACE_V1,
    role_map=(("developer", "system"),),
)

# A line holding only an ISO date or date-time. Lines end at LF only.
_DATE_LINE = re.compile(
    r"^[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?)?[ \t]*$",
    re.MULTILINE | re.ASCII,
)
# Cheap necessary conditions, so text with no date line skips the line scan.
_DATE_AT_START = re.compile(r"[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
_DATE_AFTER_NL = re.compile(r"\n[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)


class _Compiled:
    def __init__(self, p: LooseProfile) -> None:
        flags = re.IGNORECASE | re.ASCII
        self.blocks = tuple(
            (re.compile(re.escape(o), flags), re.compile(re.escape(c), flags))
            for o, c in p.block_tags
        )
        table: dict[str, Any] = {
            "version": p.version,
            "block_tags": [list(t) for t in p.block_tags],
            "whitespace": sorted(p.whitespace),
        }
        if p.role_map:
            table["role_map"] = [list(t) for t in p.role_map]
        self.fingerprint = hashlib.sha256(encode(table)).digest()[:8]
        self.roles = dict(p.role_map)
        self.py_split = p.whitespace == WHITESPACE_V1
        self.ws = "".join(chr(c) for c in sorted(p.whitespace))


_COMPILED: dict[LooseProfile, _Compiled] = {}


def _compiled(p: LooseProfile) -> _Compiled:
    c = _COMPILED.get(p)
    if c is None:
        c = _COMPILED[p] = _Compiled(p)
    return c


def _strip_blocks(v: str, open_re: re.Pattern[str], close_re: re.Pattern[str]) -> str:
    """``v`` without open ... close blocks, in linear time. An unclosed tag
    leaves the rest of the text as it is."""
    out: list[str] = []
    pos = 0
    while True:
        o = open_re.search(v, pos)
        if o is None:
            break
        c = close_re.search(v, o.end())
        if c is None:
            break
        out.append(v[pos : o.start()])
        pos = c.end()
    if pos == 0:
        return v
    out.append(v[pos:])
    return "".join(out)


def _collapse(v: str, c: _Compiled) -> str:
    if c.py_split:
        return " ".join(v.split())
    return " ".join(w for w in re.split(f"[{re.escape(c.ws)}]+", v) if w)


def loose_text(v: str, profile: LooseProfile = LOOSE_V1) -> str:
    """One text in its loose form ("" means the text is dropped)."""
    c = _compiled(profile)
    if "<" in v:
        for open_re, close_re in c.blocks:
            v = _strip_blocks(v, open_re, close_re)
    if _DATE_AT_START.match(v) or _DATE_AFTER_NL.search(v):
        v = _DATE_LINE.sub("", v)
    return _collapse(v, c)


def _resort(text: str) -> str:
    return jsontext.dump(json.loads(text), sort=True)


def _parts(parts: list[Part], p: LooseProfile) -> list[Part]:
    out: list[Part] = []
    for part in parts:
        t = part["t"]
        if t == "reasoning":
            continue
        if t == "text":
            v = loose_text(part["v"], p)
            if v:
                out.append({"t": "text", "v": v})
        elif t == "tool_result":
            out.append({**part, "parts": _parts(part["parts"], p)})
        elif t == "tool_call" and "args" in part:
            out.append({**part, "args": _resort(part["args"])})
        else:
            out.append(part)
    return out


def loose_message(m: Message, profile: LooseProfile = LOOSE_V1) -> Message:
    # Everything but the parts (role, name) is kept as it is, except a role the
    # profile's role map renames.
    out: Message = {**m, "parts": _parts(m["parts"], profile)}
    roles = _compiled(profile).roles
    if roles and m["role"] in roles:
        out["role"] = roles[m["role"]]
    return out


def _tool(t: dict[str, Any]) -> dict[str, Any]:
    if "schema" in t:
        return {**t, "schema": _resort(t["schema"])}
    return {**t, "def": _resort(t["def"])}


def loose_head(canon: Canon, profile: LooseProfile = LOOSE_V1) -> dict[str, Any]:
    """The loose head payload: ``{"head": [...], "tools": [...]}``."""
    return {
        "head": [loose_message(m, profile) for m in canon.head],
        "tools": [_tool(t) for t in canon.tools],
    }


def loose(canon: Canon, profile: LooseProfile = LOOSE_V1) -> Canon:
    """``canon`` in its loose form. Never mutates its input."""
    h = loose_head(canon, profile)
    return Canon(
        head=h["head"],
        tools=h["tools"],
        messages=[loose_message(m, profile) for m in canon.messages],
        stateful=canon.stateful,
    )
