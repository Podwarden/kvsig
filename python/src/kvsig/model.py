"""The canonical data model (decision 0002) and helpers shared by dialects.

A canonical message is ``{"role": str, "parts": [part, ...]}``. Parts are
plain dicts whose ``"t"`` names the type; see ``docs/decisions/0002``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote_to_bytes

from kvsig import jsontext
from kvsig._text import utf8
from kvsig.cbor import encode

HEAD_ROLES = ("system", "developer")

#: Default cap on the size of a canonical form: the CBOR bytes of the head
#: payload plus every body message (exact profile).
DEFAULT_MAX_BYTES = 2 << 20

Message = dict[str, Any]
Part = dict[str, Any]


@dataclass(frozen=True)
class Canon:
    """A canonicalised request: head messages, tools, body messages.

    Treat it as immutable: ``encoded`` caches the CBOR of the head payload and
    of each body message, and is not updated if the lists are changed."""

    head: list[Message]
    tools: list[dict[str, Any]]
    messages: list[Message]
    #: The request continues server-side history (OpenAI Responses
    #: ``previous_response_id`` or ``conversation``): the body is not the whole
    #: conversation, so there are no prefix or conversation ids.
    stateful: bool = False
    encoded: tuple[bytes, tuple[bytes, ...]] | None = field(default=None, compare=False, repr=False)

    def head_payload(self) -> dict[str, Any]:
        return {"head": self.head, "tools": self.tools}


class NoIds(Exception):
    """The request gets no ids: over the size cap, too deep, or unreadable."""


class Budget:
    """An early exit for oversized requests. It counts code points of strings
    that appear verbatim in the canonical form. Each one encodes to at least as
    many UTF-8 bytes, so the count never exceeds the CBOR size and the exit
    never rejects a request the exact byte check would accept."""

    __slots__ = ("left",)

    def __init__(self, max_chars: int) -> None:
        self.left = max_chars

    def charge(self, n: int) -> None:
        self.left -= n
        if self.left < 0:
            raise NoIds("canonical form over the size cap")


def json_text(v: Any, budget: Budget, *, sort: bool = False) -> str:
    try:
        s = jsontext.dump(v, sort=sort)
    except (jsontext.TooDeep, RecursionError) as e:
        raise NoIds("JSON value nests too deep") from e
    budget.charge(len(s))
    return s


def text_part(v: str, budget: Budget) -> Part | None:
    if not v:
        return None
    budget.charge(len(v))
    return {"t": "text", "v": v}


def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


_B64_WS = re.compile(r"[ \t\n\r\f\v]+")


def media_bytes(data: bytes, mime: str) -> Part:
    return {"t": "media", "sha256": _sha(data), "mime": mime.strip().lower(), "src": "bytes"}


def media_ref(ref: str, src: str, mime: str = "") -> Part:
    return {"t": "media", "sha256": _sha(utf8(ref)), "mime": mime.strip().lower(), "src": src}


def finish(canon: Canon, max_bytes: int) -> Canon | None:
    """``canon`` with its encodings attached, or None when they exceed
    ``max_bytes``. This is the normative size check."""
    head = encode(canon.head_payload())
    total = len(head)
    if total > max_bytes:
        return None
    msgs: list[bytes] = []
    for m in canon.messages:
        b = encode(m)
        total += len(b)
        if total > max_bytes:
            return None
        msgs.append(b)
    return Canon(canon.head, canon.tools, canon.messages, canon.stateful, (head, tuple(msgs)))


def media_from_url(url: Any) -> Part:
    """A media part for an image/video URL or a ``data:`` URL."""
    url = url if isinstance(url, str) else ""
    if url.startswith("data:") and "," in url:
        header, _, payload = url[5:].partition(",")
        meta = header.split(";")
        try:
            if "base64" in (m.strip().lower() for m in meta[1:]):
                data = base64.b64decode(_B64_WS.sub("", payload), validate=True)
            else:
                data = unquote_to_bytes(payload)
            return media_bytes(data, meta[0])
        except (binascii.Error, ValueError):
            pass
    return media_ref(url, "url")


def without_cache_control(v: Any) -> Any:
    """``v`` without ``cache_control`` members at any depth: a cache marker
    changes where a provider caches, never what the conversation is."""
    if isinstance(v, dict):
        return {k: without_cache_control(x) for k, x in v.items() if k != "cache_control"}
    if isinstance(v, list):
        return [without_cache_control(x) for x in v]
    return v


def opaque(p: Any, budget: Budget, type_: str | None = None) -> Part:
    """A value the dialect mapping does not know: kept, hashed, never dropped.
    ``type_`` names it when the value carries no ``type`` member. Cache
    markers are not part of it."""
    t = type_ if type_ is not None else (p.get("type") if isinstance(p, dict) else None)
    try:
        p = without_cache_control(p)
    except RecursionError as e:
        raise NoIds("value nests too deep") from e
    text = json_text(p, budget)
    return {"t": "opaque", "type": t if isinstance(t, str) else "", "sha256": _sha(utf8(text))}


def tool_args(raw: Any, budget: Budget) -> tuple[str, str]:
    """``("args", canonical JSON text)``, or ``("args_raw", raw)`` when a string
    does not parse as JSON."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except RecursionError as e:
            raise NoIds("tool arguments nest too deep") from e
        except ValueError:
            budget.charge(len(raw))
            return "args_raw", raw
        return "args", json_text(parsed, budget)
    return "args", json_text(raw, budget)
