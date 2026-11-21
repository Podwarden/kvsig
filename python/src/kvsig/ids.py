"""Keyed ids over the canonical form (decision 0002, "Ids").

``H(K, label, scope, payload) = epoch || HMAC-SHA-256(K, "kvsig/1" 0 label 0
len(scope) scope payload)[:16]``, rendered as 34 lowercase hex characters.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from kvsig.cbor import encode
from kvsig.keys import Key, KeyRing
from kvsig.loose import LOOSE_V1, LooseProfile, loose_head, loose_message
from kvsig.model import Canon, Message

SPEC_LABEL = "kvsig/1"
_SPEC = SPEC_LABEL.encode()


@dataclass(frozen=True)
class Ids:
    epoch: int
    head: str
    msgs: tuple[str, ...]
    nodes: tuple[str, ...]
    loose_head: str
    loose_msgs: tuple[str, ...]
    loose_nodes: tuple[str, ...]
    #: the conversation id: None when the body has no messages
    conv: str | None


def scope_from(*, cache_salt: str | None = None, tenant: bytes | None = None) -> bytes:
    """The scope bytes: empty when neither input is given."""
    m: dict[str, object] = {}
    if cache_salt:
        m["cache_salt"] = cache_salt
    if tenant:
        m["tenant"] = bytes(tenant)
    return hashlib.sha256(encode(m)).digest() if m else b""


def _hasher(key: Key, label: bytes, scope: bytes) -> Callable[[bytes], bytes]:
    if len(scope) > 255:
        raise ValueError("scope longer than 255 bytes")
    pre = _SPEC + b"\x00" + label + b"\x00" + bytes([len(scope)]) + scope
    epoch = bytes([key.epoch])
    secret = key.secret
    digest = hmac.digest

    def h(payload: bytes) -> bytes:
        return epoch + digest(secret, pre + payload, "sha256")[:16]

    return h


class IdCache:
    """Exact id -> loose id, so the loose transform only runs for messages this
    process has not hashed yet. Bounded, thread-safe, holds ids only."""

    def __init__(self, max_entries: int = 65_536) -> None:
        self._max = max_entries
        self._d: OrderedDict[bytes, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, k: bytes) -> bytes | None:
        with self._lock:
            v = self._d.get(k)
            if v is not None:
                self._d.move_to_end(k)
            return v

    def put(self, k: bytes, v: bytes) -> None:
        with self._lock:
            self._d[k] = v
            while len(self._d) > self._max:
                self._d.popitem(last=False)

    def __len__(self) -> int:
        return len(self._d)


class _NoCache:
    def get(self, k: bytes) -> bytes | None:
        return None

    def put(self, k: bytes, v: bytes) -> None:
        pass


def ids(
    canon: Canon,
    key: Key,
    scope: bytes = b"",
    *,
    cache: IdCache | None = None,
    profile: LooseProfile = LOOSE_V1,
) -> Ids:
    c: IdCache | _NoCache = cache if cache is not None else _NoCache()
    lp = profile.version.encode() + b":"
    # Cache keys carry the profile: the same exact id has a different loose id
    # under another profile.
    ck = lp
    h_msg = _hasher(key, b"msg", scope)
    h_node = _hasher(key, b"node", scope)
    h_lmsg = _hasher(key, lp + b"msg", scope)
    h_lnode = _hasher(key, lp + b"node", scope)

    head = _hasher(key, b"head", scope)(encode({"head": canon.head, "tools": canon.tools}))
    lhead = c.get(ck + head)
    if lhead is None:
        lhead = _hasher(key, lp + b"head", scope)(encode(loose_head(canon, profile)))
        c.put(ck + head, lhead)

    msgs = [h_msg(encode(m)) for m in canon.messages]
    nodes: list[bytes] = []
    lmsgs: list[bytes] = []
    lnodes: list[bytes] = []
    prev, lprev = head, lhead
    for m, mid in zip(canon.messages, msgs, strict=True):
        prev = h_node(prev + mid)
        nodes.append(prev)
        lm = c.get(ck + mid)
        if lm is None:
            lm = h_lmsg(encode(loose_message(m, profile)))
            c.put(ck + mid, lm)
        lmsgs.append(lm)
        # An exact node fixes its whole prefix, so it fixes the loose node too.
        ln = c.get(ck + prev)
        if ln is None:
            ln = h_lnode(lprev + lm)
            c.put(ck + prev, ln)
        lnodes.append(ln)
        lprev = ln

    conv = None
    if lnodes:
        conv = _hasher(key, lp + b"conv", scope)(lhead + lnodes[0]).hex()
    return Ids(
        epoch=key.epoch,
        head=head.hex(),
        msgs=tuple(x.hex() for x in msgs),
        nodes=tuple(x.hex() for x in nodes),
        loose_head=lhead.hex(),
        loose_msgs=tuple(x.hex() for x in lmsgs),
        loose_nodes=tuple(x.hex() for x in lnodes),
        conv=conv,
    )


def ids_all_epochs(
    canon: Canon, ring: KeyRing, scope: bytes = b"", *, cache: IdCache | None = None
) -> dict[int, Ids]:
    """Ids under every key of ``ring``, for lookups during a rotation."""
    return {k.epoch: ids(canon, k, scope, cache=cache) for k in ring.keys()}


def message_id(
    msg: Message, key: Key, scope: bytes = b"", *, profile: LooseProfile | None = None
) -> str:
    """One message's id: exact, or loose under ``profile``. A reply hashed
    alone equals the same message inside the next request."""
    if profile is None:
        return _hasher(key, b"msg", scope)(encode(msg)).hex()
    lp = profile.version.encode() + b":"
    return _hasher(key, lp + b"msg", scope)(encode(loose_message(msg, profile))).hex()
