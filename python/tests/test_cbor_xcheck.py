"""Our encoder against cbor2's canonical mode (the encoder behind vLLM's
``sha256_cbor``) on random structures inside the kvsig profile."""

import random

import pytest

from kvsig.cbor import encode

cbor2 = pytest.importorskip("cbor2")


def _gen(rnd: random.Random, depth: int = 0):
    r = rnd.random()
    if depth > 3 or r < 0.3:
        return rnd.choice(
            [
                rnd.randint(-(2**40), 2**40),
                rnd.randint(0, 30),
                "".join(chr(rnd.randint(32, 0x2FFF)) for _ in range(rnd.randint(0, 30))),
                b"\x00\xff" * rnd.randint(0, 3),
                True,
                False,
            ]
        )
    if r < 0.6:
        return [_gen(rnd, depth + 1) for _ in range(rnd.randint(0, 5))]
    keys = "abcdefgh" + chr(0xE9) + "z"
    return {
        "".join(rnd.choice(keys) for _ in range(rnd.randint(0, 30))): _gen(rnd, depth + 1)
        for _ in range(rnd.randint(0, 6))
    }


def test_matches_cbor2_canonical():
    rnd = random.Random(7)
    for _ in range(3000):
        v = _gen(rnd)
        assert encode(v) == cbor2.dumps(v, canonical=True)
