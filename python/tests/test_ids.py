import copy
import threading
from typing import Any

import pytest

from kvsig import (
    TEST_KEY,
    IdCache,
    Key,
    KeyRing,
    canonicalize,
    canonicalize_reply,
    conversation_id,
    ids,
    ids_all_epochs,
    message_id,
    scope_from,
)
from kvsig.loose import LOOSE_V1, WHITESPACE_V1, LooseProfile

K1 = Key(1, bytes([1]) * 32)
K2 = Key(2, bytes([2]) * 32)


def _body(*user: str, system: str = "S") -> dict[str, Any]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for i, u in enumerate(user):
        msgs.append({"role": "user", "content": u})
        if i < len(user) - 1:
            msgs.append({"role": "assistant", "content": f"a{i}"})
    return {"messages": msgs}


def _ids(body: dict[str, Any], key: Key = K1, scope: bytes = b"", **kw: Any):
    c = canonicalize(body)
    assert c is not None
    return ids(c, key, scope, **kw)


def test_shape_and_epoch_byte():
    i = _ids(_body("hi", "more"))
    for x in (i.head, i.loose_head, i.conv, *i.msgs, *i.nodes, *i.loose_msgs, *i.loose_nodes):
        assert x is not None and len(x) == 34 and x == x.lower()
        assert x.startswith("01")
    assert len(i.msgs) == len(i.nodes) == 3
    assert _ids(_body("hi"), TEST_KEY).head.startswith("00")


def test_deterministic():
    assert _ids(_body("hi")) == _ids(_body("hi"))


def test_key_and_scope_change_every_id():
    a, b = _ids(_body("hi"), K1), _ids(_body("hi"), K2)
    assert a.head[2:] != b.head[2:] and a.msgs[0][2:] != b.msgs[0][2:]
    s = _ids(_body("hi"), K1, scope_from(cache_salt="tenant-a"))
    assert s.head != a.head and s.conv != a.conv


def test_scope_from():
    assert scope_from() == b""
    assert len(scope_from(cache_salt="x")) == 32
    assert scope_from(cache_salt="x") != scope_from(tenant=b"x")
    assert scope_from(cache_salt="x", tenant=b"t") != scope_from(cache_salt="x")


def test_nodes_chain_and_extend_by_one_per_message():
    short, long_ = _ids(_body("hi")), _ids(_body("hi", "more"))
    assert long_.nodes[: len(short.nodes)] == short.nodes
    assert long_.loose_nodes[: len(short.loose_nodes)] == short.loose_nodes


def test_msg_id_is_independent_of_position_and_head():
    a = _ids(_body("hi", "x", system="S1"))
    b = _ids(_body("y", "hi", system="S2"))
    assert a.msgs[0] == b.msgs[2]
    assert a.nodes[0] != b.nodes[2]


def test_conv_is_stable_across_turns_reminders_and_dates():
    base = _ids(_body("hi"))
    later = _ids(_body("hi", "next", "and more"))
    noisy = _body("hi")
    noisy["messages"][0]["content"] = "S\n2026-11-20\n<system-reminder>r</system-reminder>"
    assert base.conv == later.conv == _ids(noisy).conv
    assert _ids(noisy).head != base.head  # the exact head did change


def test_conv_differs_per_first_message_and_none_without_body():
    assert _ids(_body("hi")).conv != _ids(_body("hello")).conv
    empty = _ids({"messages": [{"role": "system", "content": "S"}]})
    assert empty.conv is None and conversation_id(empty) is None


def test_reply_message_id_matches_next_request():
    reply = {
        "role": "assistant",
        "content": "sure",
        "tool_calls": [
            {"id": "c9", "type": "function", "function": {"name": "f", "arguments": "{}"}}
        ],
    }
    m = canonicalize_reply(reply)
    assert m is not None
    nxt = _body("hi")
    nxt["messages"].append(reply)
    nxt["messages"].append({"role": "tool", "tool_call_id": "c9", "content": "r"})
    i = _ids(nxt)
    assert message_id(m, K1) == i.msgs[1]
    assert message_id(m, K1, profile=LOOSE_V1) == i.loose_msgs[1]


def test_rotation_window():
    ring = KeyRing(current=K2, accepted=(K1,))
    c = canonicalize(_body("hi"))
    assert c is not None
    both = ids_all_epochs(c, ring)
    assert set(both) == {1, 2}
    assert both[1] == ids(c, K1) and both[2] == ids(c, K2)
    with pytest.raises(ValueError):
        KeyRing(current=K1, accepted=(Key(1, bytes(32)),))


def test_keys_validate_and_redact():
    with pytest.raises(ValueError):
        Key(1, b"short")
    with pytest.raises(ValueError):
        Key(256, bytes(32))
    with pytest.raises(ValueError):
        Key.generate(0)
    assert "redacted" in repr(Key.generate(3)) and "\\x" not in repr(Key.generate(3))


def test_cache_gives_identical_ids_and_is_bounded():
    bodies = [_body(*[f"m{j}" for j in range(n)]) for n in range(1, 8)]
    cache = IdCache(max_entries=10)
    for b in bodies:
        assert _ids(b, cache=cache) == _ids(b)
    assert len(cache) <= 10


def test_cache_is_safe_across_threads():
    cache = IdCache()
    body = _body(*[f"m{j}" for j in range(30)])
    want = _ids(body)
    errors: list[Any] = []

    def run() -> None:
        for _ in range(20):
            if _ids(copy.deepcopy(body), cache=cache) != want:
                errors.append("mismatch")

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_known_answer_under_test_key():
    """Pins today's bytes. A change here is a change to the draft spec and
    needs a decision record."""
    c = canonicalize(
        {"messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}]}
    )
    assert c is not None
    i = ids(c, TEST_KEY)
    assert (i.head, i.msgs[0], i.conv) == KNOWN


# Cross-checked against cbor2 (canonical=True) and a hand-built HMAC, 2026-11-20.
KNOWN = (
    "00b831865363828bd68585ae54120585d6",
    "006ab68e2caa01601261dfe441a3bd1f2f",
    "0088652dfe9eaa2ba5183f380ccfa921da",
)


def _conv(*msgs: dict[str, Any]) -> str | None:
    c = canonicalize({"messages": [{"role": "system", "content": "S"}, *msgs]})
    assert c is not None
    return ids(c, K1).conv


def test_conv_skips_openers_that_loosen_to_nothing():
    env = "<environment_context>cwd=/a</environment_context>"
    a = _conv({"role": "user", "content": env}, {"role": "user", "content": "fix the parser"})
    b = _conv({"role": "user", "content": env}, {"role": "user", "content": "write a README"})
    assert a != b
    # and the anchor is that first real message, wherever later turns go
    a2 = _conv(
        {"role": "user", "content": env},
        {"role": "user", "content": "fix the parser"},
        {"role": "assistant", "content": "done"},
    )
    assert a == a2


def test_conv_is_none_when_nothing_has_content():
    assert _conv({"role": "user", "content": "<system-reminder>r</system-reminder>"}) is None


def test_mid_conversation_developer_message_keeps_conv():
    base = _conv({"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"})
    mid = _conv(
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
        {"role": "developer", "content": "be brief"},
        {"role": "user", "content": "next"},
    )
    assert base == mid


def test_ids_all_epochs_honours_the_profile():
    p = LooseProfile("t/1", (("<x>", "</x>"),), WHITESPACE_V1)
    c = canonicalize(_body("hi <x>noise</x>"))
    assert c is not None
    ring = KeyRing(current=K2, accepted=(K1,))
    assert ids_all_epochs(c, ring, profile=p)[1] == ids(c, K1, profile=p)


def test_cache_is_keyed_by_the_table_not_the_version():
    p = LooseProfile("loose/1", (("<x>", "</x>"),), WHITESPACE_V1)
    c = canonicalize(_body("hi <x>noise</x>"))
    assert c is not None
    cache = IdCache()
    default = ids(c, K1, cache=cache)
    custom = ids(c, K1, cache=cache, profile=p)
    assert custom == ids(c, K1, profile=p)
    assert custom.loose_msgs != default.loose_msgs


def test_unexpected_errors_are_logged_not_raised(monkeypatch, caplog):
    import kvsig
    from kvsig.dialects import openai_chat

    def boom(*a: Any, **k: Any) -> Any:
        raise KeyError("bug")

    monkeypatch.setattr(openai_chat, "canonicalize", boom)
    with caplog.at_level("ERROR", logger="kvsig"):
        assert kvsig.canonicalize({"messages": []}) is None
    assert "unexpected error" in caplog.text
