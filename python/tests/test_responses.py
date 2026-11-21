from typing import Any

from kvsig import TEST_KEY, canonicalize, ids


def _c(body: dict[str, Any]):
    c = canonicalize(body, "openai.responses")
    assert c is not None
    return c


def test_string_input_is_one_user_message():
    c = _c({"input": "hi", "instructions": "S"})
    assert c.head == [{"role": "system", "parts": [{"t": "text", "v": "S"}]}]
    assert c.messages == [{"role": "user", "parts": [{"t": "text", "v": "hi"}]}]


def test_leading_developer_items_join_the_head_later_ones_stay():
    c = _c(
        {
            "instructions": "S",
            "input": [
                {"role": "developer", "content": "D"},
                {"role": "user", "content": "u"},
                {"role": "developer", "content": "D2"},
            ],
        }
    )
    assert [m["role"] for m in c.head] == ["system", "developer"]
    assert [m["role"] for m in c.messages] == ["user", "developer"]


def test_consecutive_assistant_side_items_are_one_message():
    c = _c(
        {
            "input": [
                {"role": "user", "content": "go"},
                {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "a"},
                        {"type": "summary_text", "text": "b"},
                    ],
                },
                {"type": "function_call", "call_id": "1", "name": "f", "arguments": "{}"},
                {"type": "function_call", "call_id": "2", "name": "g", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "2", "output": "G"},
                {"type": "function_call_output", "call_id": "1", "output": "F"},
            ]
        }
    )
    assert [m["role"] for m in c.messages] == ["user", "assistant", "tool", "tool"]
    a = c.messages[1]["parts"]
    assert a[0] == {"t": "reasoning", "v": "a\n\nb"}
    assert [p["ref"] for p in a[1:]] == [0, 1]
    assert [m["parts"][0]["ref"] for m in c.messages[2:]] == [1, 0]


def test_encrypted_only_reasoning_is_opaque():
    c = _c({"input": [{"type": "reasoning", "summary": [], "encrypted_content": "gAAA"}]})
    assert c.messages[0]["parts"][0]["type"] == "reasoning"
    assert c.messages[0]["parts"][0]["t"] == "opaque"


def test_custom_tool_calls_are_raw():
    c = _c(
        {
            "input": [
                {"type": "custom_tool_call", "call_id": "1", "name": "patch", "input": "*** Begin"}
            ]
        }
    )
    assert c.messages[0]["parts"][0] == {
        "t": "tool_call",
        "name": "patch",
        "args_raw": "*** Begin",
        "ref": 0,
    }


def test_stateful_requests_get_no_prefix_or_conversation_ids():
    for extra in ({"previous_response_id": "resp_1"}, {"conversation": "conv_1"}):
        c = _c({"input": "more", **extra})
        assert c.stateful
        i = ids(c, TEST_KEY)
        assert i.nodes == () and i.loose_nodes == () and i.conv is None
        assert len(i.msgs) == 1  # message ids are still given
    assert not _c({"input": "more"}).stateful


def test_unknown_items_are_opaque_and_kept():
    c = _c({"input": [{"type": "web_search_call", "id": "ws", "status": "completed"}]})
    assert c.messages[0]["parts"][0]["type"] == "web_search_call"


def test_not_a_responses_body_gives_none():
    assert canonicalize({"messages": []}, "openai.responses") is None


def test_loose_keeps_the_stateful_flag():
    from kvsig import loose

    c = _c({"input": "more", "previous_response_id": "r1"})
    assert loose(c).stateful
    i = ids(loose(c), TEST_KEY)
    assert i.nodes == () and i.conv is None


def test_server_tool_items_stay_inside_the_assistant_turn_and_replies_match():
    from kvsig import canonicalize_reply, message_id

    out = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "look it up"}]},
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": "x"},
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "found"}],
        },
    ]
    c = _c(
        {"input": [{"role": "user", "content": "q"}, *out, {"role": "user", "content": "thanks"}]}
    )
    assert [m["role"] for m in c.messages] == ["user", "assistant", "user"]
    assert [p["t"] for p in c.messages[1]["parts"]] == ["reasoning", "opaque", "text"]
    reply = canonicalize_reply({"output": out}, "openai.responses")
    assert reply is not None
    assert message_id(reply, TEST_KEY) == ids(c, TEST_KEY).msgs[1]


def test_empty_reasoning_item_opens_no_message():
    c = _c(
        {
            "input": [
                {"role": "user", "content": "q"},
                {"type": "reasoning", "summary": []},
                {"role": "user", "content": "q2"},
            ]
        }
    )
    assert [m["role"] for m in c.messages] == ["user", "user"]


def test_non_string_instructions_are_kept_as_opaque():
    a = _c({"input": "hi", "instructions": [{"type": "x", "v": 1}]})
    b = _c({"input": "hi", "instructions": [{"type": "x", "v": 2}]})
    assert a.head[0]["parts"][0]["type"] == "instructions" and a != b
