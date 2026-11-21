"""kvsig: keyed, content-derived ids for LLM chat conversations.

Reference implementation of the kvsig specification (draft). Pure functions,
no third-party dependencies. Hostile input never raises: it yields ``None``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from kvsig.cbor import encode
from kvsig.dialects import SUPPORTED, Dialect
from kvsig.dialects import openai_chat as _openai_chat
from kvsig.ids import SPEC_LABEL, IdCache, Ids, ids, ids_all_epochs, message_id, scope_from
from kvsig.keys import TEST_KEY, InMemoryKeyProvider, Key, KeyProvider, KeyRing
from kvsig.loose import LOOSE_V1, LooseProfile, loose
from kvsig.model import DEFAULT_MAX_BYTES, Budget, Canon, Message, NoIds, finish

__all__ = [
    "DEFAULT_MAX_BYTES",
    "LOOSE_V1",
    "SPEC_LABEL",
    "TEST_KEY",
    "Canon",
    "Dialect",
    "IdCache",
    "Ids",
    "InMemoryKeyProvider",
    "Key",
    "KeyProvider",
    "KeyRing",
    "LooseProfile",
    "Message",
    "canonicalize",
    "canonicalize_reply",
    "conversation_id",
    "encode",
    "ids",
    "ids_all_epochs",
    "loose",
    "message_id",
    "scope_from",
]

log = logging.getLogger("kvsig")

T = TypeVar("T")


def _check(dialect: str) -> None:
    if dialect not in SUPPORTED:
        raise NotImplementedError(f"dialect {dialect!r} is not implemented in this release")


def _fail_open(what: str, fn: Callable[[], T | None]) -> T | None:
    """Run ``fn``; the defined "no ids" outcomes return None quietly. Anything
    else is a bug in this library: it still returns None (an id must never
    fail a request) but is logged, so a broken deployment is visible."""
    try:
        return fn()
    except (NoIds, RecursionError):
        return None
    except Exception:  # noqa: BLE001 -- identity must never fail a request
        log.exception("kvsig: unexpected error in %s; returning no ids", what)
        return None


def canonicalize(
    body: Any, dialect: Dialect = "openai.chat", *, max_bytes: int = DEFAULT_MAX_BYTES
) -> Canon | None:
    """The canonical form of a request body, or None when the request gets no
    ids: not a chat body, over ``max_bytes`` of canonical CBOR, or nested too
    deep. Raises only for an unknown ``dialect``."""
    _check(dialect)

    def run() -> Canon | None:
        if not isinstance(body, dict):
            return None
        c = _openai_chat.canonicalize(body, Budget(max_bytes))
        return None if c is None else finish(c, max_bytes)

    return _fail_open("canonicalize", run)


def canonicalize_reply(
    message: Any, dialect: Dialect = "openai.chat", *, max_bytes: int = DEFAULT_MAX_BYTES
) -> Message | None:
    """A response's assistant message, canonicalised alone, so that its
    ``message_id`` equals the id of the same message in the next request."""
    _check(dialect)

    def run() -> Message | None:
        if not isinstance(message, dict):
            return None
        m = _openai_chat.reply(message, Budget(max_bytes))
        return m if len(encode(m)) <= max_bytes else None

    return _fail_open("canonicalize_reply", run)


def conversation_id(i: Ids) -> str | None:
    return i.conv
