"""One system prompt in the shapes clients send it (decision 0005).

OpenCode 2.3.2 moved its system prompt in Responses requests from
``instructions`` to a leading ``developer`` message item. Exact ids keep the
two apart (a role is something the model sees); ``loose/2`` reads them as one.
"""

from typing import Any

import pytest

from kvsig import LOOSE_V1, LOOSE_V2, TEST_KEY, Ids, canonicalize, ids, loose, message_id
from kvsig.loose import WHITESPACE_V1, LooseProfile

T = "You are a coding agent.\n\nBe brief."
TOOLS = [{"type": "function", "name": "ls", "parameters": {"type": "object"}}]
CHAT_TOOLS = [{"type": "function", "function": {"name": "ls", "parameters": {"type": "object"}}}]
USER = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}]


def _ids(body: dict[str, Any], dialect: str, profile=LOOSE_V1) -> Ids:
    c = canonicalize(body, dialect)  # type: ignore[arg-type]
    assert c is not None
    return ids(c, TEST_KEY, profile=profile)


def _instructions() -> dict[str, Any]:
    return {"model": "m", "instructions": T, "input": USER, "tools": TOOLS}


def _developer_item() -> dict[str, Any]:
    dev = {"type": "message", "role": "developer", "content": T}
    return {"model": "m", "input": [dev, *USER], "tools": TOOLS}


def _chat(role: str) -> dict[str, Any]:
    msgs = [{"role": role, "content": T}, {"role": "user", "content": "hi"}]
    return {"model": "m", "messages": msgs, "tools": CHAT_TOOLS}


def _anthropic() -> dict[str, Any]:
    tools = [{"name": "ls", "input_schema": {"type": "object"}}]
    return {"model": "m", "max_tokens": 8, "system": T, "tools": tools,
            "messages": [{"role": "user", "content": "hi"}]}  # fmt: skip


def test_loose_v1_keeps_the_two_shapes_apart():
    a, b = _ids(_instructions(), "openai.responses"), _ids(_developer_item(), "openai.responses")
    assert a.msgs == b.msgs and a.tools == b.tools and a.loose_tools == b.loose_tools
    for f in ("sys", "head", "loose_sys", "loose_head", "conv"):
        assert getattr(a, f) != getattr(b, f), f
    assert a.nodes[0] != b.nodes[0]


def test_loose_v2_gives_one_conversation_and_one_loose_head():
    a = _ids(_instructions(), "openai.responses", LOOSE_V2)
    b = _ids(_developer_item(), "openai.responses", LOOSE_V2)
    for f in ("loose_sys", "loose_head", "conv", "loose_nodes", "loose_msgs"):
        assert getattr(a, f) == getattr(b, f), f
    # exact ids are untouched by the loose profile: the role differs on the wire
    for f in ("sys", "head", "nodes"):
        assert getattr(a, f) != getattr(b, f), f


def test_loose_v2_matches_across_dialects():
    shapes = [
        _ids(_instructions(), "openai.responses", LOOSE_V2),
        _ids(_developer_item(), "openai.responses", LOOSE_V2),
        _ids(_chat("system"), "openai.chat", LOOSE_V2),
        _ids(_chat("developer"), "openai.chat", LOOSE_V2),
        _ids(_anthropic(), "anthropic.messages", LOOSE_V2),
    ]
    assert len({(i.loose_sys, i.loose_head, i.conv) for i in shapes}) == 1
    # exact: instructions == chat system == anthropic system; the developer shapes pair up
    assert shapes[0].head == shapes[2].head == shapes[4].head
    assert shapes[1].head == shapes[3].head != shapes[0].head


def test_exact_ids_do_not_depend_on_the_loose_profile():
    a = _ids(_developer_item(), "openai.responses", LOOSE_V1)
    b = _ids(_developer_item(), "openai.responses", LOOSE_V2)
    assert (a.head, a.sys, a.tools, a.msgs, a.nodes) == (b.head, b.sys, b.tools, b.msgs, b.nodes)
    # different profile versions never give equal loose ids
    assert a.loose_sys != b.loose_sys and a.conv != b.conv


def test_loose_v2_renames_mid_conversation_developer_messages_too():
    c = canonicalize(
        {"input": [{"role": "user", "content": "u"}, {"role": "developer", "content": "D"}]},
        "openai.responses",
    )
    assert c is not None
    assert [m["role"] for m in loose(c, LOOSE_V2).messages] == ["user", "system"]
    assert [m["role"] for m in loose(c, LOOSE_V1).messages] == ["user", "developer"]
    dev, sysm = c.messages[1], {"role": "system", "parts": c.messages[1]["parts"]}
    assert message_id(dev, TEST_KEY, profile=LOOSE_V2) == message_id(
        sysm, TEST_KEY, profile=LOOSE_V2
    )
    assert message_id(dev, TEST_KEY) != message_id(sysm, TEST_KEY)


def test_loose_v2_keeps_other_roles_and_does_not_mutate():
    c = canonicalize(_chat("developer"), "openai.chat")
    assert c is not None
    lv = loose(c, LOOSE_V2)
    assert [m["role"] for m in lv.head] == ["system"]
    assert [m["role"] for m in lv.messages] == ["user"]
    assert c.head[0]["role"] == "developer"


def test_loose_v1_fingerprint_is_unchanged_by_the_new_field():
    same = LooseProfile(LOOSE_V1.version, LOOSE_V1.block_tags, WHITESPACE_V1, ())
    assert same.fingerprint == LOOSE_V1.fingerprint
    assert LOOSE_V2.fingerprint != LOOSE_V1.fingerprint


@pytest.mark.parametrize(
    "role_map",
    [(("developer",),), (("", "system"),), (("developer", "system"), ("developer", "user"))],
)
def test_bad_role_maps_are_rejected(role_map):
    with pytest.raises(ValueError):
        LooseProfile("t/1", (), WHITESPACE_V1, role_map)
