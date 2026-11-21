# ruff: noqa: E501
"""Level 3 vectors: reply linkage. Each vector is the NEXT request (which carries the
assistant message back) plus the response that produced it. The reply's message id
must equal the loose id of body message ``index`` (always) and its exact id when
``exact`` is true (a client that drops reasoning makes the exact ids differ)."""

from __future__ import annotations

import json

from cases import ANTH, CHAT, RESP, SCHEMA, add


def reply(dialect, slug, desc, request, response, index, exact=True):
    add(
        dialect,
        slug,
        3,
        "reply",
        desc,
        request,
        reply={"response": response, "index": index, "exact": exact},
    )


def usr(t):
    return {"role": "user", "content": t}


def chat_resp(message):
    return {
        "id": "chatcmpl-synthetic-1",
        "object": "chat.completion",
        "model": "m",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }


def chat_calls(*names):
    return [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {"name": n, "arguments": json.dumps({"path": "/" + n})},
        }
        for i, n in enumerate(names)
    ]


_T = [{"type": "function", "function": {"name": "ls", "description": "List", "parameters": SCHEMA}}]
_SYS = {"role": "system", "content": "S"}

# ------------------------------------------------------------------ openai.chat
m = {"role": "assistant", "content": "Four."}
reply(
    CHAT,
    "reply-text",
    "A plain text reply equals the assistant message of the next request.",
    {"model": "m", "messages": [_SYS, usr("2+2?"), m, usr("thanks")]},
    chat_resp(m),
    1,
)

m = {"role": "assistant", "content": None, "tool_calls": chat_calls("a", "b")}
reply(
    CHAT,
    "reply-tool-calls",
    "Two tool calls and no content.",
    {
        "model": "m",
        "tools": _T,
        "messages": [
            usr("go"),
            m,
            {"role": "tool", "tool_call_id": "call_1", "content": "B"},
            {"role": "tool", "tool_call_id": "call_0", "content": "A"},
        ],
    },
    chat_resp(m),
    1,
)

m = {
    "role": "assistant",
    "reasoning_content": "think first",
    "content": "On it.",
    "tool_calls": chat_calls("ls"),
}
reply(
    CHAT,
    "reply-reasoning-sent-back",
    "Reasoning, text and a call; the client sends all of it back.",
    {
        "model": "m",
        "tools": _T,
        "messages": [usr("go"), m, {"role": "tool", "tool_call_id": "call_0", "content": "A"}],
    },
    chat_resp(m),
    1,
)

m = {
    "role": "assistant",
    "reasoning_content": "think first",
    "content": "On it.",
    "tool_calls": chat_calls("ls"),
}
sent = {k: v for k, v in m.items() if k != "reasoning_content"}
reply(
    CHAT,
    "reply-reasoning-not-sent-back",
    "The client drops reasoning: exact ids differ, loose ids still match.",
    {
        "model": "m",
        "tools": _T,
        "messages": [usr("go"), sent, {"role": "tool", "tool_call_id": "call_0", "content": "A"}],
    },
    chat_resp(m),
    1,
    exact=False,
)

m = {"role": "assistant", "content": None, "refusal": "I cannot help with that."}

m = {"role": "assistant", "content": "Hi", "annotations": [], "function_call": None}
sent = {"role": "assistant", "content": "Hi"}

# ------------------------------------------------------------------ anthropic.messages
_AT = [{"name": "ls", "description": "List", "input_schema": SCHEMA}]


def anth_resp(content):
    return {
        "id": "msg_synthetic_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": content,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }


c = [{"type": "text", "text": "Four."}]
reply(
    ANTH,
    "reply-text",
    "A plain text reply.",
    {
        "model": "m",
        "max_tokens": 9,
        "system": "S",
        "messages": [usr("2+2?"), {"role": "assistant", "content": c}, usr("thanks")],
    },
    anth_resp(c),
    1,
)

c = [
    {"type": "tool_use", "id": "toolu_a", "name": "ls", "input": {"path": "/a"}},
    {"type": "tool_use", "id": "toolu_b", "name": "ls", "input": {"path": "/b"}},
]
reply(
    ANTH,
    "reply-tool-use",
    "Two tool_use blocks.",
    {
        "model": "m",
        "max_tokens": 9,
        "tools": _AT,
        "messages": [
            usr("go"),
            {"role": "assistant", "content": c},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_b", "content": "B"},
                    {"type": "tool_result", "tool_use_id": "toolu_a", "content": "A"},
                ],
            },
        ],
    },
    anth_resp(c),
    1,
)

c = [
    {"type": "thinking", "thinking": "plan it", "signature": "sig-synthetic"},
    {"type": "text", "text": "Calling."},
    {"type": "tool_use", "id": "toolu_a", "name": "ls", "input": {"path": "/a"}},
]
reply(
    ANTH,
    "reply-thinking-sent-back",
    "Thinking, text and tool_use sent back unchanged.",
    {
        "model": "m",
        "max_tokens": 9,
        "tools": _AT,
        "messages": [
            usr("go"),
            {"role": "assistant", "content": c},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_a", "content": "A"}],
            },
        ],
    },
    anth_resp(c),
    1,
)
reply(
    ANTH,
    "reply-thinking-not-sent-back",
    "The client drops the thinking block: loose ids still match.",
    {
        "model": "m",
        "max_tokens": 9,
        "tools": _AT,
        "messages": [
            usr("go"),
            {"role": "assistant", "content": c[1:]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_a", "content": "A"}],
            },
        ],
    },
    anth_resp(c),
    1,
    exact=False,
)

c = [
    {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "q"}},
    {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [{"type": "x"}]},
    {"type": "text", "text": "Found it.", "citations": [{"type": "x", "cited_text": "y"}]},
]
sent = [c[0], c[1], {"type": "text", "text": "Found it."}]
reply(
    ANTH,
    "reply-server-tool-blocks",
    "Server tool blocks are opaque; citations on text are ignored.",
    {
        "model": "m",
        "max_tokens": 9,
        "messages": [usr("search"), {"role": "assistant", "content": sent}, usr("thanks")],
    },
    anth_resp(c),
    1,
)

# ------------------------------------------------------------------ openai.responses
_RT = [{"type": "function", "name": "ls", "description": "List", "parameters": SCHEMA}]


def resp_resp(output):
    return {
        "id": "resp_synthetic_1",
        "object": "response",
        "model": "m",
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }


def _msg(text):
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _fc(i, name):
    return {
        "type": "function_call",
        "id": f"fc_{i}",
        "call_id": f"call_{i}",
        "name": name,
        "arguments": json.dumps({"path": "/" + name}),
    }


def _u(t):
    return {"type": "message", "role": "user", "content": t}


out = [_msg("Four.")]
reply(
    RESP,
    "reply-text",
    "A plain text reply.",
    {"model": "m", "instructions": "S", "input": [_u("2+2?"), *out, _u("thanks")]},
    resp_resp(out),
    1,
)

out = [_fc(0, "a"), _fc(1, "b")]
reply(
    RESP,
    "reply-function-calls",
    "Two function calls.",
    {
        "model": "m",
        "tools": _RT,
        "input": [
            _u("go"),
            *out,
            {"type": "function_call_output", "call_id": "call_1", "output": "B"},
            {"type": "function_call_output", "call_id": "call_0", "output": "A"},
        ],
    },
    resp_resp(out),
    1,
)

out = [
    {"type": "reasoning", "id": "rs_1", "summary": [{"type": "summary_text", "text": "plan it"}]},
    _msg("Calling."),
    _fc(0, "ls"),
]
reply(
    RESP,
    "reply-reasoning-sent-back",
    "Reasoning summary, message and call, sent back unchanged.",
    {
        "model": "m",
        "tools": _RT,
        "input": [
            _u("go"),
            *out,
            {"type": "function_call_output", "call_id": "call_0", "output": "A"},
        ],
    },
    resp_resp(out),
    1,
)
reply(
    RESP,
    "reply-reasoning-not-sent-back",
    "The client drops the reasoning item: loose ids still match.",
    {
        "model": "m",
        "tools": _RT,
        "input": [
            _u("go"),
            *out[1:],
            {"type": "function_call_output", "call_id": "call_0", "output": "A"},
        ],
    },
    resp_resp(out),
    1,
    exact=False,
)

out = [
    {
        "type": "web_search_call",
        "id": "ws_1",
        "status": "completed",
        "action": {"type": "search", "query": "q"},
    },
    _msg("Found it."),
]
reply(
    RESP,
    "reply-web-search-call",
    "A server-side tool item is an opaque part inside the reply.",
    {"model": "m", "input": [_u("search"), *out, _u("thanks")]},
    resp_resp(out),
    1,
)

out = [
    {
        "type": "custom_tool_call",
        "id": "ct_1",
        "call_id": "call_k",
        "name": "patch",
        "input": "*** Begin ***",
    }
]

out = [_msg("Part one."), _msg("Part two.")]
reply(
    RESP,
    "reply-two-message-items",
    "Two assistant message items are one reply message.",
    {"model": "m", "input": [_u("go"), *out, _u("ok")]},
    resp_resp(out),
    1,
)
