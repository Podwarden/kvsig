"""Deployment keys and key rings."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Protocol

KEY_BYTES = 32


@dataclass(frozen=True)
class Key:
    """A deployment key. Epochs 1..255 are for real keys; 0 is reserved for
    published test keys."""

    epoch: int
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.epoch, int) or not 0 <= self.epoch <= 255:
            raise ValueError("epoch must be 0..255")
        if not isinstance(self.secret, bytes) or len(self.secret) != KEY_BYTES:
            raise ValueError(f"key must be {KEY_BYTES} bytes")

    @classmethod
    def generate(cls, epoch: int) -> Key:
        if epoch == 0:
            raise ValueError("epoch 0 is reserved for test keys")
        return cls(epoch, secrets.token_bytes(KEY_BYTES))

    def __repr__(self) -> str:
        return f"Key(epoch={self.epoch}, secret=<redacted>)"


#: The published test key (epoch 0): bytes 0x00..0x1f.
TEST_KEY = Key(0, bytes(range(KEY_BYTES)))


@dataclass(frozen=True)
class KeyRing:
    """The current key plus older keys still accepted for lookups."""

    current: Key
    accepted: tuple[Key, ...] = ()

    def __post_init__(self) -> None:
        epochs = [k.epoch for k in self.keys()]
        if len(set(epochs)) != len(epochs):
            raise ValueError("epochs in a key ring must be distinct")

    def keys(self) -> tuple[Key, ...]:
        return (self.current, *self.accepted)


class KeyProvider(Protocol):
    """Where a deployment's key ring comes from (a file, a secret store, a
    cluster control plane). The caller decides when to refresh."""

    def ring(self) -> KeyRing: ...


class InMemoryKeyProvider:
    def __init__(self, ring: KeyRing) -> None:
        self._ring = ring

    def ring(self) -> KeyRing:
        return self._ring
