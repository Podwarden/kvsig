from typing import Any

from kvsig import canonicalize


def _c(body: dict[str, Any]):
    c = canonicalize(body, "anthropic.messages")
    assert c is not None
    return c


def _msgs(*m: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"model": "m", "max_tokens": 10, "messages": list(m), **extra}


def test_system_string_and_blocks_are_one_head_message():
    a = _c(_msgs({"role": "user", "content": "hi"}, system="S"))
    b = _c(_msgs({"role": "user", "content": "hi"}, system=[{"type": "text", "text": "S"}]))
    assert a == b and a.head == [{"role": "system", "parts": [{"t": "text", "v": "S"}]}]
    assert _c(_msgs({"role": "user", "content": "hi"})).head == []


def test_tool_results_split_out_in_place_and_keep_their_images():
    c = _c(
        _msgs(
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "a", "name": "f", "input": {}},
                    {"type": "tool_use", "id": "b", "name": "f", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "b",
                        "content": [
                            {"type": "text", "text": "B"},
                            {"type": "image", "source": {"type": "url", "url": "https://x/i.png"}},
                        ],
                    },
                    {"type": "tool_result", "tool_use_id": "a", "content": "A", "is_error": True},
                    {"type": "text", "text": "next"},
                ],
            },
        )
    )
    roles = [m["role"] for m in c.messages]
    assert roles == ["assistant", "tool", "tool", "user"]
    b, a = c.messages[1]["parts"][0], c.messages[2]["parts"][0]
    assert b["ref"] == 1 and b["parts"][1]["t"] == "media" and "error" not in b
    assert a["ref"] == 0 and a["error"] is True
    assert c.messages[3]["parts"] == [{"t": "text", "v": "next"}]


def test_thinking_signature_and_cache_control_do_not_count():
    def body(sig: str, cc: bool) -> dict[str, Any]:
        blk: dict[str, Any] = {"type": "text", "text": "ok"}
        if cc:
            blk["cache_control"] = {"type": "ephemeral"}
        return _msgs(
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "t", "signature": sig}, blk],
            },
        )

    assert _c(body("a", False)) == _c(body("b", True))


def test_redacted_thinking_and_server_blocks_are_opaque_and_kept():
    c = _c(
        _msgs(
            {
                "role": "assistant",
                "content": [
                    {"type": "redacted_thinking", "data": "xyz"},
                    {
                        "type": "server_tool_use",
                        "id": "s",
                        "name": "web_search",
                        "input": {"q": "a"},
                    },
                    {"type": "web_search_tool_result", "tool_use_id": "s", "content": []},
                ],
            }
        )
    )
    assert [p["type"] for p in c.messages[0]["parts"]] == [
        "redacted_thinking",
        "server_tool_use",
        "web_search_tool_result",
    ]
    other = _c(
        _msgs({"role": "assistant", "content": [{"type": "redacted_thinking", "data": "abc"}]})
    )
    assert other.messages[0]["parts"][0] != c.messages[0]["parts"][0]


def test_documents_with_a_title_are_kept_whole():
    plain = {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": "D"},
    }
    titled = {**plain, "title": "T"}
    a = _c(_msgs({"role": "user", "content": [plain]})).messages[0]["parts"][0]
    b = _c(_msgs({"role": "user", "content": [titled]})).messages[0]["parts"][0]
    assert a["t"] == "media" and a["mime"] == "text/plain"
    assert b["t"] == "opaque"


def test_server_tools_keep_their_definition_without_cache_control():
    t = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
    a = _c(_msgs({"role": "user", "content": "q"}, tools=[t]))
    b = _c(
        _msgs(
            {"role": "user", "content": "q"}, tools=[{**t, "cache_control": {"type": "ephemeral"}}]
        )
    )
    assert (
        a.tools
        == b.tools
        == [
            {
                "type": "web_search_20250305",
                "def": '{"type":"web_search_20250305","name":"web_search","max_uses":3}',
            }
        ]
    )


def test_line_wrapped_base64_matches_chat():
    import base64

    from kvsig import canonicalize as canon

    raw = base64.b64encode(b"PNGDATA" * 20).decode()
    wrapped = "\n".join(raw[i : i + 40] for i in range(0, len(raw), 40))
    a = _c(
        _msgs(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": wrapped},
                    }
                ],
            }
        )
    )
    chat = canon(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + raw}}
                    ],
                }
            ]
        }
    )
    assert chat is not None
    assert a.messages[0]["parts"][0]["t"] == "media"
    assert a.messages[0]["parts"] == chat.messages[0]["parts"]


def test_cache_control_is_stripped_only_at_the_top_of_a_block():
    def block(inner):
        return {
            "type": "mcp_tool_use",
            "id": "m",
            "name": "q",
            "input": {"cache_control": inner},
            "cache_control": {"type": "ephemeral"},
        }

    a = _c(_msgs({"role": "assistant", "content": [block("one")]})).messages[0]["parts"][0]
    b = _c(_msgs({"role": "assistant", "content": [block("two")]})).messages[0]["parts"][0]
    c = _c(
        _msgs(
            {"role": "assistant", "content": [{**block("one"), "cache_control": {"type": "other"}}]}
        )
    ).messages[0]["parts"][0]
    assert a != b  # a data field named cache_control is content
    assert a == c  # the block's own cache marker is not
