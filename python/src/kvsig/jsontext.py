"""Canonical JSON text, for the JSON values the canonical form keeps
(tool-call arguments, tool schemas, unknown parts). See decision 0002."""

from __future__ import annotations

import math
from decimal import Decimal
from json.encoder import encode_basestring
from typing import Any

from kvsig._text import scalar

#: Containers (arrays and objects) may nest this deep; one more level gives
#: no ids (a defined outcome, not an error). Scalars never count.
MAX_DEPTH = 128

_SAFE_INT = 1 << 53


class TooDeep(ValueError):
    """A JSON value nests deeper than ``MAX_DEPTH``."""


def es6_number(f: float) -> str:
    """``f`` printed with ECMAScript ``Number.prototype.toString`` (RFC 8785
    section 3.2.2.3). Non-finite values print as ``null``."""
    if not math.isfinite(f):
        return "null"
    if f == 0:
        return "0"
    sign = "-" if f < 0 else ""
    # repr() is the shortest round-trip digit string, as ECMAScript requires.
    _, digs, exp = Decimal(repr(abs(f))).as_tuple()
    digits = "".join(map(str, digs)).lstrip("0")
    stripped = digits.rstrip("0")
    exp = int(exp) + (len(digits) - len(stripped))
    digits = stripped
    k = len(digits)
    n = k + exp
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mant = digits[0] + ("." + digits[1:] if k > 1 else "")
        body = f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def _number(v: int | float) -> str:
    if isinstance(v, int):
        if -_SAFE_INT <= v <= _SAFE_INT:
            return str(v)
        try:
            return es6_number(float(v))
        except OverflowError:
            # Too large for a double: a JSON parser that reads numbers as
            # doubles sees an infinity, which prints as null.
            return "null"
    return es6_number(v)


def _members(v: dict[Any, Any], sort: bool) -> list[tuple[str, Any]]:
    """Members with keys as Unicode scalars. Keys that become equal after
    surrogate repair are merged: the last value wins, at the first position
    (the rule JSON parsers apply to duplicate keys)."""
    merged: dict[str, Any] = {}
    for k, val in v.items():
        if not isinstance(k, str):
            raise TypeError("JSON object keys must be strings")
        merged[scalar(k)] = val
    items = list(merged.items())
    if sort:
        items.sort(key=lambda kv: kv[0])
    return items


def _dump(v: Any, sort: bool, depth: int, out: list[str]) -> None:
    """``depth`` is the number of containers enclosing ``v``."""
    if v is None:
        out.append("null")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif isinstance(v, str):
        out.append(encode_basestring(scalar(v)))
    elif isinstance(v, (int, float)):
        out.append(_number(v))
    elif isinstance(v, dict):
        if depth >= MAX_DEPTH:
            raise TooDeep
        out.append("{")
        for i, (k, val) in enumerate(_members(v, sort)):
            if i:
                out.append(",")
            out.append(encode_basestring(k))
            out.append(":")
            _dump(val, sort, depth + 1, out)
        out.append("}")
    elif isinstance(v, (list, tuple)):
        if depth >= MAX_DEPTH:
            raise TooDeep
        out.append("[")
        for i, item in enumerate(v):
            if i:
                out.append(",")
            _dump(item, sort, depth + 1, out)
        out.append("]")
    else:
        raise TypeError(f"type {type(v).__name__} is not a JSON value")


def dump(v: Any, *, sort: bool = False) -> str:
    """Canonical JSON text of ``v``. Member order is kept unless ``sort``."""
    out: list[str] = []
    _dump(v, sort, 0, out)
    return "".join(out)
