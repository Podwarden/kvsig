import base64
import hashlib
import time
from typing import Any

import pytest

from kvsig import Canon, canonicalize, canonicalize_reply, encode

TOOL = {
    "type": "function",
    "function": {
        "name": "ls",
        "description": "list",
        "parameters": {"type": "object", "properties": {"p": {"type": "string"}}},
    },
}


def _c(body: dict[str, Any]) -> Canon:
    c = canonicalize(body)
    assert c is not None
    return c


def _chat(call_id: str = "call_1") -> dict[str, Any]:
    return {
        "model": "m",
        "tools": [TOOL],
        "messages": [
            {"role": "system", "content": "S"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "ls", "arguments": '{"p": "/", "a": 1}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": call_id, "content": "out"},
            {"role": "user", "content": "thanks"},
        ],
    }


def test_shape_of_every_part_type():
    png = b"PNGDATA"
    c = _c(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/PNG;base64," + base64.b64encode(png).decode()
                            },
                        },
                        {"type": "image_url", "image_url": {"url": "https://x/a.png"}},
                        {"type": "file", "file": {"file_id": "file-1"}},
                        {"type": "mystery", "x": 1},
                    ],
                },
                {"role": "assistant", "reasoning_content": "think", "content": "done"},
            ]
        }
    )
    parts = c.messages[0]["parts"]
    assert parts[0] == {"t": "text", "v": "look"}
    assert parts[1] == {
        "t": "media",
        "sha256": hashlib.sha256(png).digest(),
        "mime": "image/png",
        "src": "bytes",
    }
    assert parts[2]["src"] == "url" and parts[2]["mime"] == ""  # never guessed from ".png"
    assert parts[2]["sha256"] == hashlib.sha256(b"https://x/a.png").digest()
    assert parts[3]["src"] == "file_id"
    assert parts[4]["t"] == "opaque" and parts[4]["type"] == "mystery"
    assert c.messages[1]["parts"] == [{"t": "reasoning", "v": "think"}, {"t": "text", "v": "done"}]


def test_url_bytes_and_file_id_never_collide():
    same = "abc"
    a = _c({"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": same}]}]})
    b = _c(
        {"messages": [{"role": "user", "content": [{"type": "file", "file": {"file_id": same}}]}]}
    )
    assert a.messages[0]["parts"][0]["sha256"] == b.messages[0]["parts"][0]["sha256"]
    assert a.messages[0]["parts"][0]["src"] != b.messages[0]["parts"][0]["src"]


def test_percent_encoded_and_bad_base64_data_urls():
    pct = _c(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": "data:text/plain,a%20b"}],
                }
            ]
        }
    )
    assert pct.messages[0]["parts"][0]["sha256"] == hashlib.sha256(b"a b").digest()
    bad = "data:image/png;base64,!!!"
    c = _c({"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": bad}]}]})
    p = c.messages[0]["parts"][0]
    assert p["src"] == "url" and p["sha256"] == hashlib.sha256(bad.encode()).digest()


def test_head_is_the_leading_run_of_system_and_developer():
    c = _c(_chat())
    assert [m["role"] for m in c.head] == ["system"]
    assert [m["role"] for m in c.messages] == ["user", "assistant", "tool", "user"]
    lead = _chat()
    lead["messages"].insert(1, {"role": "developer", "content": "D"})
    assert [m["role"] for m in _c(lead).head] == ["system", "developer"]
    # a later system/developer message stays in the body, in order
    late = _chat()
    late["messages"].insert(3, {"role": "developer", "content": "D"})
    lc = _c(late)
    assert [m["role"] for m in lc.head] == ["system"]
    assert [m["role"] for m in lc.messages] == ["user", "assistant", "developer", "tool", "user"]


def test_tools_neutral_model():
    c = _c(_chat())
    assert c.tools == [
        {
            "name": "ls",
            "desc": "list",
            "schema": '{"type":"object","properties":{"p":{"type":"string"}}}',
        }
    ]
    other = _c({"messages": [], "tools": [{"type": "web_search", "x": 1}]})
    assert other.tools == [{"type": "web_search", "def": '{"type":"web_search","x":1}'}]


def test_legacy_functions_map_to_tools():
    legacy = {"messages": [], "functions": [TOOL["function"]]}
    assert _c(legacy).tools == _c({"messages": [], "tools": [TOOL]}).tools


def test_tool_call_ids_never_enter_the_form():
    assert _c(_chat("call_1")) == _c(_chat("call_ZZZ"))


def test_args_keep_client_member_order():
    call = _c(_chat()).messages[1]["parts"][1]
    assert call == {"t": "tool_call", "name": "ls", "args": '{"p":"/","a":1}', "ref": 0}


def test_unparsable_args_are_tagged_raw():
    body = _chat()
    body["messages"][2]["tool_calls"][0]["function"]["arguments"] = '{"p": '
    call = _c(body).messages[1]["parts"][1]
    assert call == {"t": "tool_call", "name": "ls", "args_raw": '{"p": ', "ref": 0}


def test_ref_is_local_so_a_reply_alone_equals_it_in_context():
    body = _chat()
    in_context = _c(body).messages[1]
    alone = canonicalize_reply(body["messages"][2])
    assert alone == in_context


def test_results_reference_their_calls_out_of_order():
    body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                    {"id": "b", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "b", "content": "B"},
            {"role": "tool", "tool_call_id": "a", "content": "A"},
            {"role": "tool", "tool_call_id": "zzz", "content": "?"},
        ]
    }
    refs = [m["parts"][0]["ref"] for m in _c(body).messages[1:]]
    assert refs == [1, 0, -1]


def test_string_equals_single_text_part_and_parts_are_not_merged():
    one = _c({"messages": [{"role": "user", "content": "ab"}]})
    part = _c({"messages": [{"role": "user", "content": [{"type": "text", "text": "ab"}]}]})
    two = _c(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
                }
            ]
        }
    )
    assert one == part
    assert one != two


def test_empty_text_is_dropped_and_dict_content_is_opaque():
    c = _c({"messages": [{"role": "user", "content": ["", {"type": "text", "text": ""}]}]})
    assert c.messages[0]["parts"] == []
    d = _c({"messages": [{"role": "user", "content": {"weird": 1}}]})
    assert d.messages[0]["parts"][0]["t"] == "opaque"


@pytest.mark.parametrize("body", [None, [], "x", {}, {"messages": "no"}, {"messages": None}])
def test_not_a_chat_body_gives_none(body):
    assert canonicalize(body) is None


def test_size_cap_is_exact_on_cbor_bytes():
    body = {"messages": [{"role": "user", "content": "x" * 100}]}
    c = canonicalize(body)
    assert c is not None and c.encoded is not None
    size = len(c.encoded[0]) + sum(len(b) for b in c.encoded[1])
    assert size == len(encode(c.head_payload())) + len(encode(c.messages[0]))
    assert canonicalize(body, max_bytes=size) is not None
    assert canonicalize(body, max_bytes=size - 1) is None


def test_size_cap_counts_strings_outside_text():
    # a huge data-URL header lands in "mime"; a huge role lands in "role"
    junk = "x" * 5000
    for body in (
        {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": f"data:{junk};base64,AA=="}],
                }
            ]
        },
        {"messages": [{"role": junk, "content": "hi"}]},
    ):
        assert canonicalize(body, max_bytes=4000) is None
        assert canonicalize(body) is not None


def test_deep_args_give_none():
    body = _chat()
    body["messages"][2]["tool_calls"][0]["function"]["arguments"] = "[" * 200 + "]" * 200
    assert canonicalize(body) is None


def test_unknown_dialect_raises():
    with pytest.raises(NotImplementedError):
        canonicalize({"messages": []}, "anthropic.messages")


def test_hostile_values_never_raise():
    weird: list[Any] = [None, 1, 1.5, [], {}, "s", {"role": 1}, {"content": [1, None, []]}]
    for w in weird:
        for body in (
            {"messages": [w]},
            {"messages": [{"role": "assistant", "tool_calls": [w]}]},
            {"messages": [{"role": "user", "content": [w]}]},
            {"messages": [], "tools": [w]},
        ):
            canonicalize(body)  # must not raise


def test_canonicalisation_is_linear():
    t0 = time.perf_counter()
    canonicalize({"messages": [{"role": "user", "content": "<system-reminder>" * 50_000}]})
    assert time.perf_counter() - t0 < 1.0


def test_legacy_function_call_and_function_role_are_mapped():
    def body(name: str, args: str) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "user", "content": "go"},
                {
                    "role": "assistant",
                    "content": None,
                    "function_call": {"name": name, "arguments": args},
                },
                {"role": "function", "name": name, "content": "result"},
            ]
        }

    a, b = _c(body("a", "{}")), _c(body("b", '{"q":1}'))
    assert a != b
    assert a.messages[1]["parts"] == [{"t": "tool_call", "name": "a", "args": "{}", "ref": 0}]
    assert a.messages[2] == {
        "role": "function",
        "name": "a",
        "parts": [{"t": "tool_result", "ref": -1, "parts": [{"t": "text", "v": "result"}]}],
    }


def test_refusal_and_audio_are_kept_as_opaque():
    def body(**extra: Any) -> dict[str, Any]:
        return {"messages": [{"role": "assistant", "content": None, **extra}]}

    r1, r2 = _c(body(refusal="no")), _c(body(refusal="never"))
    assert r1.messages[0]["parts"][0]["type"] == "refusal" and r1 != r2
    a1, a2 = _c(body(audio={"id": "x"})), _c(body(audio={"id": "y"}))
    assert a1.messages[0]["parts"][0]["type"] == "audio" and a1 != a2


def test_non_dict_entries_are_opaque_and_keep_their_slot():
    m = _c({"messages": [{"role": "user", "content": "a"}, 5]})
    assert m.messages[1] == {"role": "", "parts": [m.messages[1]["parts"][0]]}
    assert m.messages[1]["parts"][0]["type"] == "message"
    assert m != _c({"messages": [{"role": "user", "content": "a"}]})

    good = {"id": "g", "type": "function", "function": {"name": "f", "arguments": "{}"}}
    c = _c(
        {
            "messages": [
                {"role": "assistant", "tool_calls": [None, good]},
                {"role": "tool", "tool_call_id": "g", "content": "r"},
            ]
        }
    )
    calls = c.messages[0]["parts"]
    assert calls[0]["t"] == "opaque" and calls[1]["ref"] == 1
    assert c.messages[1]["parts"][0]["ref"] == 1


def test_message_name_is_kept():
    a = _c({"messages": [{"role": "user", "name": "alice", "content": "hi"}]})
    b = _c({"messages": [{"role": "user", "name": "bob", "content": "hi"}]})
    assert a.messages[0]["name"] == "alice" and a != b
