"""Unicode scalar handling shared by every encoder (decision 0001, rule 4)."""

from __future__ import annotations

import re

# A well-formed surrogate pair, or any lone surrogate.
_SURROGATES = re.compile("[\ud800-\udbff][\udc00-\udfff]|[\ud800-\udfff]")


def _fix(m: re.Match[str]) -> str:
    g = m.group()
    if len(g) == 2:
        return chr(0x10000 + ((ord(g[0]) - 0xD800) << 10) + (ord(g[1]) - 0xDC00))
    return "\ufffd"


def scalar(s: str) -> str:
    """``s`` as Unicode scalar values: a surrogate pair becomes the code point it
    stands for, a lone surrogate becomes U+FFFD. No normalisation."""
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        return _SURROGATES.sub(_fix, s)
    return s


def utf8(s: str) -> bytes:
    """UTF-8 bytes of ``scalar(s)``."""
    try:
        return s.encode("utf-8")
    except UnicodeEncodeError:
        return _SURROGATES.sub(_fix, s).encode("utf-8")
