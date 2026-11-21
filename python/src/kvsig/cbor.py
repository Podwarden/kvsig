"""The restricted deterministic CBOR profile of decision 0001.

Allowed: integers, byte strings, text strings, arrays, maps with text keys,
``True`` and ``False``. Everything is in preferred (shortest) serialisation and
map keys are sorted bytewise by their encoding (RFC 8949 section 4.2.1).
Anything else (floats, ``None``, other key types) raises ``TypeError``.
"""

from __future__ import annotations

from typing import Any

from kvsig._text import utf8

_MAX_UINT = (1 << 64) - 1


def _head(major: int, n: int, out: bytearray) -> None:
    mt = major << 5
    if n < 24:
        out.append(mt | n)
    elif n < 0x100:
        out.append(mt | 24)
        out.append(n)
    elif n < 0x10000:
        out.append(mt | 25)
        out += n.to_bytes(2, "big")
    elif n < 0x100000000:
        out.append(mt | 26)
        out += n.to_bytes(4, "big")
    elif n <= _MAX_UINT:
        out.append(mt | 27)
        out += n.to_bytes(8, "big")
    else:
        raise ValueError("integer out of CBOR range")


def _text(s: str, out: bytearray) -> None:
    b = utf8(s)
    _head(3, len(b), out)
    out += b


def _enc(o: Any, out: bytearray) -> None:
    # bool before int: bool is a subclass of int.
    if o is True:
        out.append(0xF5)
    elif o is False:
        out.append(0xF4)
    elif isinstance(o, str):
        _text(o, out)
    elif isinstance(o, int):
        if o >= 0:
            _head(0, o, out)
        else:
            _head(1, -1 - o, out)
    elif isinstance(o, (bytes, bytearray)):
        _head(2, len(o), out)
        out += o
    elif isinstance(o, (list, tuple)):
        _head(4, len(o), out)
        for v in o:
            _enc(v, out)
    elif isinstance(o, dict):
        items: list[tuple[bytes, Any]] = []
        for k, v in o.items():
            if not isinstance(k, str):
                raise TypeError("CBOR map keys must be text")
            kb = bytearray()
            _text(k, kb)
            items.append((bytes(kb), v))
        items.sort(key=lambda kv: kv[0])
        for i in range(1, len(items)):
            if items[i][0] == items[i - 1][0]:
                raise ValueError("duplicate CBOR map key after normalisation")
        _head(5, len(items), out)
        for kb, v in items:
            out += kb
            _enc(v, out)
    else:
        raise TypeError(f"type {type(o).__name__} is not in the kvsig CBOR profile")


def encode(obj: Any) -> bytes:
    """The canonical bytes of ``obj``."""
    out = bytearray()
    _enc(obj, out)
    return bytes(out)
