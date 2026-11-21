"""Canonical JSON text, for the JSON values the canonical form keeps
(tool-call arguments, tool schemas, unknown parts). See decision 0002."""

from __future__ import annotations

import math
from decimal import Decimal
from json.encoder import encode_basestring
from typing import Any

from kvsig._text import scalar

#: Deeper JSON values give no ids (a defined outcome, not an error).
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
            return str(v)
    return es6_number(v)


def _dump(v: Any, sort: bool, depth: int, out: list[str]) -> None:
    if depth > MAX_DEPTH:
        raise TooDeep
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
        keys = list(v.keys())
        for k in keys:
            if not isinstance(k, str):
                raise TypeError("JSON object keys must be strings")
        if sort:
            keys = sorted(keys, key=scalar)
        out.append("{")
        for i, k in enumerate(keys):
            if i:
                out.append(",")
            out.append(encode_basestring(scalar(k)))
            out.append(":")
            _dump(v[k], sort, depth + 1, out)
        out.append("}")
    elif isinstance(v, (list, tuple)):
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
    _dump(v, sort, 1, out)
    return "".join(out)
