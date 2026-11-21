import pytest

from kvsig.cbor import encode


@pytest.mark.parametrize(
    ("value", "hex_"),
    [
        # RFC 8949 Appendix A
        (0, "00"),
        (1, "01"),
        (10, "0a"),
        (23, "17"),
        (24, "1818"),
        (25, "1819"),
        (100, "1864"),
        (1000, "1903e8"),
        (1000000, "1a000f4240"),
        (1000000000000, "1b000000e8d4a51000"),
        (18446744073709551615, "1bffffffffffffffff"),
        (-1, "20"),
        (-10, "29"),
        (-100, "3863"),
        (-1000, "3903e7"),
        (False, "f4"),
        (True, "f5"),
        (b"", "40"),
        (b"\x01\x02\x03\x04", "4401020304"),
        ("", "60"),
        ("a", "6161"),
        ("IETF", "6449455446"),
        ('"\\', "62225c"),
        ("ü", "62c3bc"),
        ("水", "63e6b0b4"),
        ("\U00010151", "64f0908591"),
        ([], "80"),
        ([1, 2, 3], "83010203"),
        ([1, [2, 3], [4, 5]], "8301820203820405"),
        ({}, "a0"),
        ({"a": 1, "b": [2, 3]}, "a26161016162820203"),
        (["a", {"b": "c"}], "826161a161626163"),
    ],
)
def test_rfc8949_appendix_a(value, hex_):
    assert encode(value).hex() == hex_


def test_map_keys_sorted_bytewise_by_encoding():
    # shorter keys encode with a smaller head byte, so they sort first
    assert encode({"bb": 1, "a": 2, "c": 3}) == encode({"a": 2, "c": 3, "bb": 1})
    assert encode({"bb": 1, "a": 2, "c": 3}).hex() == "a3616102616303626262" + "01"


def test_insertion_order_does_not_matter():
    assert encode({"x": 1, "y": 2}) == encode({"y": 2, "x": 1})


@pytest.mark.parametrize("bad", [1.5, None, {1: "a"}, object(), 1 << 64, -(1 << 64) - 1])
def test_outside_the_profile_is_rejected(bad):
    with pytest.raises((TypeError, ValueError)):
        encode(bad)


def test_lone_surrogate_becomes_replacement_char():
    assert encode("a\ud800b") == encode("a\ufffdb")


def test_surrogate_pair_becomes_its_code_point():
    # built with chr(): a formatter must not fold the two code points into one
    pair = chr(0xD83D) + chr(0xDE00)
    assert len(pair) == 2
    assert encode(pair) == encode("\U0001f600")


def test_duplicate_keys_after_surrogate_fix_are_rejected():
    with pytest.raises(ValueError):
        encode({"\ud800": 1, "\udc00": 2})  # noqa: F601 -- distinct keys; ruff misreads them
