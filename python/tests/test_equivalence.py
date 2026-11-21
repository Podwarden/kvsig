"""One conversation, three API dialects, one canonical form."""

import base64
from typing import Any

import pytest

from kvsig import TEST_KEY, canonicalize, canonicalize_reply, ids, message_id

PNG = base64.b64encode(b"PNGDATA").decode()
SCHEMA = {"type": "object", "properties": {"p": {"type": "string"}}}


def chat() -> dict[str, Any]:
    return {
        "model": "m",
        "tools": [
            {
                "type": "function",
                "function": {"name": "ls", "description": "list", "parameters": SCHEMA},
            }
        ],
        "messages": [
            {"role": "system", "content": "S"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
                ],
            },
            {
                "role": "assistant",
                "reasoning_content": "think",
                "content": "ok",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "ls", "arguments": '{"p": "/"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "out"},
            {"role": "user", "content": "thanks"},
        ],
    }


def anthropic() -> dict[str, Any]:
    return {
        "model": "m",
        "max_tokens": 100,
        "system": [{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "ls", "description": "list", "input_schema": SCHEMA}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hi"},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": PNG},
                    },
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "think", "signature": "sig-abc"},
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "id": "toolu_1", "name": "ls", "input": {"p": "/"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "out"},
                    {"type": "text", "text": "thanks", "cache_control": {"type": "ephemeral"}},
                ],
            },
        ],
    }


def responses() -> dict[str, Any]:
    return {
        "model": "m",
        "instructions": "S",
        "tools": [
            {
                "type": "function",
                "name": "ls",
                "description": "list",
                "parameters": SCHEMA,
                "strict": False,
            }
        ],
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "hi"},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{PNG}",
                        "detail": "auto",
                    },
                ],
            },
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [],
                "content": [{"type": "reasoning_text", "text": "think"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            },
            {"type": "function_call", "call_id": "call_9", "name": "ls", "arguments": '{"p": "/"}'},
            {"type": "function_call_output", "call_id": "call_9", "output": "out"},
            {"role": "user", "content": "thanks"},
        ],
    }


BODIES = {"openai.chat": chat, "anthropic.messages": anthropic, "openai.responses": responses}


def _canon(dialect: str):
    c = canonicalize(BODIES[dialect](), dialect)
    assert c is not None, dialect
    return c


def test_three_dialects_give_one_canonical_form():
    forms = {d: _canon(d) for d in BODIES}
    assert forms["anthropic.messages"] == forms["openai.chat"]
    assert forms["openai.responses"] == forms["openai.chat"]


def test_three_dialects_give_the_same_ids():
    got = {d: ids(_canon(d), TEST_KEY) for d in BODIES}
    assert got["anthropic.messages"] == got["openai.chat"] == got["openai.responses"]
    assert got["openai.chat"].conv is not None


@pytest.mark.parametrize(
    ("dialect", "response"),
    [
        (
            "openai.chat",
            {
                "role": "assistant",
                "reasoning_content": "think",
                "content": "ok",
                "tool_calls": [
                    {
                        "id": "x",
                        "type": "function",
                        "function": {"name": "ls", "arguments": '{"p":"/"}'},
                    }
                ],
            },
        ),
        (
            "anthropic.messages",
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "thinking", "thinking": "think", "signature": "s"},
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "id": "toolu_x", "name": "ls", "input": {"p": "/"}},
                ],
            },
        ),
        (
            "openai.responses",
            {
                "id": "resp_1",
                "object": "response",
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs",
                        "summary": [],
                        "content": [{"type": "reasoning_text", "text": "think"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "c",
                        "name": "ls",
                        "arguments": '{"p":"/"}',
                    },
                ],
            },
        ),
    ],
)
def test_replies_match_the_assistant_message_of_the_next_request(dialect, response):
    m = canonicalize_reply(response, dialect)
    assert m is not None
    nxt = ids(_canon(dialect), TEST_KEY)
    assert message_id(m, TEST_KEY) == nxt.msgs[1]
