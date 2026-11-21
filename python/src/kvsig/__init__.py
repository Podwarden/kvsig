"""kvsig: keyed, content-derived ids for LLM chat conversations.

Reference implementation of the kvsig specification (draft). Pure functions,
no third-party dependencies. Hostile input never raises: it yields ``None``.
"""

from __future__ import annotations

from typing import Any

from kvsig.cbor import encode
from kvsig.dialects import SUPPORTED, Dialect
from kvsig.dialects import openai_chat as _openai_chat
from kvsig.ids import SPEC_LABEL, IdCache, Ids, ids, ids_all_epochs, message_id, scope_from
from kvsig.keys import TEST_KEY, InMemoryKeyProvider, Key, KeyProvider, KeyRing
from kvsig.loose import LOOSE_V1, LooseProfile, loose
from kvsig.model import DEFAULT_MAX_CHARS, Budget, Canon, Message, NoIds

__all__ = [
    "DEFAULT_MAX_CHARS",
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


def _check(dialect: str) -> None:
    if dialect not in SUPPORTED:
        raise NotImplementedError(f"dialect {dialect!r} is not implemented in this release")


def canonicalize(
    body: Any, dialect: Dialect = "openai.chat", *, max_chars: int = DEFAULT_MAX_CHARS
) -> Canon | None:
    """The canonical form of a request body, or None when the request gets no
    ids (not a chat body, over ``max_chars`` of text, nested too deep, or
    unreadable). Raises only for an unknown ``dialect``."""
    _check(dialect)
    try:
        if not isinstance(body, dict):
            return None
        return _openai_chat.canonicalize(body, Budget(max_chars))
    except NoIds:
        return None
    except Exception:  # noqa: BLE001 -- identity input must never fail a request
        return None


def canonicalize_reply(
    message: Any, dialect: Dialect = "openai.chat", *, max_chars: int = DEFAULT_MAX_CHARS
) -> Message | None:
    """A response's assistant message, canonicalised alone, so that its
    ``message_id`` equals the id of the same message in the next request."""
    _check(dialect)
    try:
        if not isinstance(message, dict):
            return None
        return _openai_chat.reply(message, Budget(max_chars))
    except NoIds:
        return None
    except Exception:  # noqa: BLE001
        return None


def conversation_id(i: Ids) -> str | None:
    return i.conv
