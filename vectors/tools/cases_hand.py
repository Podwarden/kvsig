# ruff: noqa: E501
"""Hand-written, dialect-specific vector cases (see cases.py for the shared parts)."""

from __future__ import annotations

from cases import *


def relate(vid, field, other, same):
    for c in CASES:
        if c["id"] == vid:
            c["relations"].append({"field": field, "other": other, "same": same})
            return
    raise KeyError(vid)


def chat(msgs, **kw):
    return {"model": "m", "messages": msgs, **kw}


def anth(msgs, system=None, **kw):
    b = {"model": "m", "max_tokens": 64, "messages": msgs, **kw}
    if system is not None:
        b["system"] = system
    return b


def resp(items, **kw):
    return {"model": "m", "input": items, **kw}


def usr(t):
    return {"role": "user", "content": t}


def dataurl(data=PNG, mime="image/png", flag="base64"):
    return f"data:{mime};{flag},{b64(data)}"


# ============================================================ chat: parts, head, structure
add(
    CHAT,
    "request-parameters-ignored",
    1,
    "basics",
    "Request parameters other than messages and tools do not affect the ids.",
    chat(
        [usr("Hello, world")],
        temperature=0.2,
        stream=True,
        metadata={"k": "v"},
        user="u1",
        max_tokens=10,
    ),
)
relate("openai.chat/request-parameters-ignored", "head", "openai.chat/user-only", True)
relate("openai.chat/request-parameters-ignored", "msgs", "openai.chat/user-only", True)
add(CHAT, "content-string", 1, "parts", "String content is one text part.", chat([usr("ab")]))
add(
    CHAT,
    "content-parts",
    1,
    "parts",
    "A single text part equals the string form.",
    chat([usr([{"type": "text", "text": "ab"}])]),
)
relate("openai.chat/content-parts", "msgs", "openai.chat/content-string", True)
add(
    CHAT,
    "content-adjacent-text-not-merged",
    1,
    "parts",
    "Two adjacent text parts stay two parts (not equal to the joined string).",
    chat([usr([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])]),
)
relate("openai.chat/content-adjacent-text-not-merged", "msgs", "openai.chat/content-string", False)
add(
    CHAT,
    "empty-text-dropped",
    1,
    "parts",
    "Empty text parts and empty content are dropped.",
    chat(
        [
            usr([{"type": "text", "text": ""}, "x", {"type": "text", "text": ""}]),
            usr(""),
            {"role": "assistant", "content": None},
        ]
    ),
)
add(
    CHAT,
    "message-name",
    1,
    "parts",
    "A non-empty name is part of the message; an empty one is not.",
    chat(
        [
            {"role": "user", "name": "alice", "content": "hi"},
            {"role": "user", "name": "", "content": "hi"},
        ]
    ),
)
add(
    CHAT,
    "developer-role-head",
    1,
    "head",
    "The leading run of system and developer messages is the head, in order.",
    chat([{"role": "developer", "content": "D"}, {"role": "system", "content": "S"}, usr("go")]),
)
add(
    CHAT,
    "system-mid-conversation",
    1,
    "head",
    "A system message after the first body message stays in the body; the head keeps its prefix.",
    chat(
        [
            {"role": "system", "content": "S"},
            usr("go"),
            {"role": "assistant", "content": "ok"},
            {"role": "system", "content": "late"},
            usr("more"),
        ]
    ),
)
add(
    CHAT,
    "head-only",
    1,
    "head",
    "Only system messages: empty body, no conversation id.",
    chat([{"role": "system", "content": "S"}]),
)
add(
    CHAT,
    "empty-messages",
    1,
    "head",
    "An empty message list is a valid, empty conversation.",
    chat([]),
)
add(CHAT, "body-not-an-object", 1, "head", "A body that is not an object: no ids.", [1, 2])
add(
    CHAT,
    "non-object-message",
    1,
    "opaque",
    "Messages that are not objects are kept as role-less opaque messages.",
    chat(["just a string", usr("x"), 5, None, ["a"]]),
)
add(
    CHAT,
    "unknown-content-part",
    1,
    "opaque",
    "An unknown part type is opaque (hash of its canonical JSON text).",
    chat([usr([{"type": "mystery", "z": 1, "a": [1, 2]}])]),
)
add(
    CHAT,
    "refusal-and-audio",
    1,
    "opaque",
    "Assistant refusal and audio fields become opaque parts, after the content.",
    chat([usr("x"), {"role": "assistant", "content": "c", "refusal": "no", "audio": {"id": "a1"}}]),
)
add(
    CHAT,
    "reasoning-content-field",
    1,
    "parts",
    "reasoning_content is the first part of an assistant message.",
    chat([usr("x"), {"role": "assistant", "reasoning_content": "A", "content": "c"}]),
)
add(
    CHAT,
    "reasoning-field-alias",
    1,
    "parts",
    "The alias field `reasoning` gives the same part.",
    chat([usr("x"), {"role": "assistant", "reasoning": "A", "content": "c"}]),
)
relate("openai.chat/reasoning-field-alias", "msgs", "openai.chat/reasoning-content-field", True)
add(
    CHAT,
    "legacy-functions",
    1,
    "tool-refs",
    "Deprecated functions, function_call and role function map to tools, a call and a ref -1 result.",
    chat(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": None,
                "function_call": {"name": "ls", "arguments": '{"path":"/"}'},
            },
            {"role": "function", "name": "ls", "content": "out"},
        ],
        functions=[{"name": "ls", "description": "List", "parameters": SCHEMA}],
    ),
)
add(
    CHAT,
    "custom-tool-call",
    1,
    "tool-refs",
    "A custom tool call keeps its raw input as args_raw.",
    chat(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "k1",
                        "type": "custom",
                        "custom": {"name": "patch", "input": "*** Begin ***"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "k1", "content": "applied"},
        ]
    ),
)
add(
    CHAT,
    "non-object-tool-call",
    1,
    "tool-refs",
    "A tool_calls entry that is not an object still takes an index; the next call is index 1.",
    chat(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    5,
                    {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r"},
        ]
    ),
)
add(
    CHAT,
    "tool-call-arguments-missing",
    1,
    "unparsable-args",
    "Missing arguments canonicalise as the JSON value null.",
    chat(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "a"}}],
            },
        ]
    ),
)
add(
    CHAT,
    "tool-unknown-type",
    1,
    "parts",
    "A non-function tool is {type, def} with def the canonical JSON text.",
    chat([usr("x")], tools=[{"type": "web_search", "search_context_size": "low", "a": [1]}]),
)
add(
    CHAT,
    "tool-no-parameters",
    1,
    "parts",
    'A function tool without parameters has schema "null".',
    chat([usr("x")], tools=[{"type": "function", "function": {"name": "noop"}}]),
)


# ============================================================ unicode on the wire (raw bytes)
def raw_chat(text_json, role="user"):
    return '{"model":"m","messages":[{"role":"' + role + '","content":' + text_json + "}]}"


LONE_HI = BS + "ud800"
LONE_LO = BS + "udc00"
add(
    CHAT,
    "unicode-lone-surrogate-high",
    1,
    "unicode",
    "A lone high surrogate escape in a text becomes U+FFFD.",
    raw=raw_chat('"a' + LONE_HI + 'b"'),
)
add(
    CHAT,
    "unicode-lone-surrogate-low",
    1,
    "unicode",
    "A lone low surrogate escape becomes U+FFFD.",
    raw=raw_chat('"a' + LONE_LO + 'b"'),
)
add(
    CHAT,
    "unicode-fffd-literal",
    1,
    "unicode",
    "The literal U+FFFD text: same ids as the lone surrogate cases.",
    chat([usr("a" + FFFD + "b")]),
)
relate("openai.chat/unicode-fffd-literal", "msgs", "openai.chat/unicode-lone-surrogate-high", True)
relate("openai.chat/unicode-lone-surrogate-low", "msgs", "openai.chat/unicode-fffd-literal", True)
add(
    CHAT,
    "unicode-surrogate-pair-escape",
    1,
    "unicode",
    "A high then low surrogate escape is one astral character.",
    raw=raw_chat('"x' + BS + "ud83d" + BS + 'ude00y"'),
)
add(
    CHAT,
    "unicode-astral-literal",
    1,
    "unicode",
    "The same character written literally.",
    chat([usr("x" + EMOJI + "y")]),
)
relate(
    "openai.chat/unicode-surrogate-pair-escape", "msgs", "openai.chat/unicode-astral-literal", True
)
add(
    CHAT,
    "unicode-reversed-pair",
    1,
    "unicode",
    "A low then a high surrogate are two lone surrogates: two U+FFFD.",
    raw=raw_chat('"' + LONE_LO + LONE_HI + '"'),
)
add(
    CHAT,
    "unicode-lone-surrogate-in-args",
    1,
    "unicode",
    "A lone surrogate inside the arguments text (as a JSON escape) is repaired in the canonical args.",
    chat(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "f",
                            "arguments": '{"k":"v' + LONE_HI + '","' + LONE_LO + '":1}',
                        },
                    }
                ],
            },
        ]
    ),
)
add(
    CHAT,
    "unicode-lone-surrogate-in-names",
    1,
    "unicode",
    "Lone surrogates in a tool name and description (wire escapes) are repaired.",
    raw='{"model":"m","messages":[{"role":"user","content":"x"}],"tools":[{"type":"function",'
    '"function":{"name":"f' + LONE_HI + '","description":"d' + LONE_LO + '","parameters":{}}}]}',
)
add(
    ANTH,
    "unicode-lone-surrogate-in-text",
    1,
    "unicode",
    "A lone surrogate in an Anthropic text block.",
    raw='{"model":"m","max_tokens":1,"messages":[{"role":"user","content":[{"type":"text",'
    '"text":"a' + LONE_HI + 'b"}]}]}',
)
add(
    ANTH,
    "unicode-lone-surrogate-in-input-key",
    1,
    "unicode",
    "Lone surrogates in tool_use input keys merge after repair; the last value wins.",
    raw='{"model":"m","max_tokens":1,"messages":[{"role":"user","content":"x"},{"role":"assistant",'
    '"content":[{"type":"tool_use","id":"t1","name":"f","input":{"'
    + LONE_HI
    + '":1,"'
    + BS
    + 'ud801":2,"z":3}}]}]}',
)
add(
    RESP,
    "unicode-lone-surrogate-in-text",
    1,
    "unicode",
    "A lone surrogate in a Responses input_text.",
    raw='{"model":"m","input":[{"type":"message","role":"user","content":[{"type":"input_text",'
    '"text":"a' + LONE_LO + 'b"}]}]}',
)
GROUPS.append(["openai.chat/unicode-lone-surrogate-high", "openai.chat/unicode-lone-surrogate-low"])

# ============================================================ duplicate keys on the wire
add(
    CHAT,
    "duplicate-keys-message",
    1,
    "duplicate-keys",
    "A duplicate member in the request itself: the last value wins.",
    raw='{"model":"m","messages":[{"role":"user","content":"first","content":"second"}]}',
)
add(
    CHAT,
    "unicode-last-content-literal",
    1,
    "duplicate-keys",
    "The same message with only the last value.",
    chat([usr("second")]),
)
relate(
    "openai.chat/duplicate-keys-message", "msgs", "openai.chat/unicode-last-content-literal", True
)
add(
    ANTH,
    "duplicate-keys-tool-input",
    1,
    "duplicate-keys",
    "Duplicate members inside a tool_use input object.",
    raw='{"model":"m","max_tokens":1,"messages":[{"role":"user","content":"x"},{"role":"assistant",'
    '"content":[{"type":"tool_use","id":"t1","name":"f","input":{"a":1,"b":2,"a":3}}]}]}',
)
add(
    RESP,
    "duplicate-keys-item",
    1,
    "duplicate-keys",
    "A duplicate `role` in an item: the last wins.",
    raw='{"model":"m","input":[{"type":"message","role":"assistant","role":"user","content":"hi"}]}',
)


# ============================================================ chat media
def chat_img(url):
    return chat([usr([{"type": "image_url", "image_url": {"url": url}}])])


add(
    CHAT,
    "media-data-url-wrapped",
    1,
    "media",
    "Line-wrapped base64 hashes the same as unwrapped.",
    chat(
        [
            usr(
                [
                    "Look at this",
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + "\r\n".join(b64(PNG)[i : i + 8] for i in range(0, len(b64(PNG)), 8))
                        },
                    },
                ]
            )
        ]
    ),
)
relate("openai.chat/media-data-url-wrapped", "msgs", "openai.chat/image-data-url", True)
add(
    CHAT,
    "media-data-url-percent",
    1,
    "media",
    "A non-base64 data URL is percent-decoded.",
    chat_img("data:text/plain,hello%20world%21"),
)
add(
    CHAT,
    "media-data-url-base64-twin",
    1,
    "media",
    "The same bytes and MIME type as base64.",
    chat_img("data:text/plain;base64," + b64(b"hello world!")),
)
relate("openai.chat/media-data-url-percent", "msgs", "openai.chat/media-data-url-base64-twin", True)
add(
    CHAT,
    "media-data-url-no-mime",
    1,
    "media",
    "No MIME type in the header: mime is empty.",
    chat_img("data:;base64," + b64(PNG)),
)
add(
    CHAT,
    "media-data-url-flag-case-params",
    1,
    "media",
    "The base64 flag is case-insensitive; extra parameters are ignored; MIME is lowercased and trimmed.",
    chat_img("data: Image/PNG ;charset=x;BASE64," + b64(PNG)),
)
add(
    CHAT,
    "media-data-url-bad-base64",
    1,
    "media",
    "Invalid base64 in a data URL: the whole URL is hashed as a url reference.",
    chat_img("data:image/png;base64,@@@not-base64@@@"),
)
add(
    CHAT,
    "media-url",
    1,
    "media",
    "A remote URL is hashed as text (src url).",
    chat_img("https://example.test/a.png"),
)
add(
    CHAT,
    "media-url-vs-file-id",
    1,
    "media",
    "The same string as a URL and as a file id gives two different media parts.",
    chat(
        [
            usr(
                [
                    {"type": "image_url", "image_url": {"url": "abc123"}},
                    {"type": "file", "file": {"file_id": "abc123"}},
                ]
            )
        ]
    ),
)
add(
    CHAT,
    "media-file-data-base64",
    1,
    "media",
    "File data as bare base64: bytes, no MIME type.",
    chat([usr([{"type": "file", "file": {"file_data": b64(PDF), "filename": "a.pdf"}}])]),
)
add(
    CHAT,
    "media-input-audio",
    1,
    "media",
    "Audio input: bytes with mime audio/<format>.",
    chat(
        [
            usr(
                [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": b64(b"RIFFsynthetic"), "format": "wav"},
                    }
                ]
            )
        ]
    ),
)

# ============================================================ anthropic
add(
    ANTH,
    "system-string",
    1,
    "head",
    "A system string is one head message with one text part.",
    anth([usr("hi")], system="S"),
)
add(
    ANTH,
    "system-blocks",
    1,
    "head",
    "A system list of one block equals the string form.",
    anth([usr("hi")], system=[{"type": "text", "text": "S"}]),
)
relate("anthropic.messages/system-blocks", "head", "anthropic.messages/system-string", True)
add(
    ANTH,
    "system-empty",
    1,
    "head",
    "An empty system string or list adds no head message.",
    anth([usr("hi")], system=""),
)
add(
    ANTH,
    "cache-control-ignored",
    1,
    "cache-control",
    "cache_control on system, text blocks, an image and a tool is ignored.",
    anth(
        [
            {
                "role": "user",
                "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}],
            }
        ],
        system=[{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}],
        tools=[
            {
                "name": "ls",
                "description": "List",
                "input_schema": SCHEMA,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    ),
)
add(
    ANTH,
    "cache-control-absent",
    1,
    "cache-control",
    "The same request without any cache_control.",
    anth(
        [usr("hi")],
        system="S",
        tools=[{"name": "ls", "description": "List", "input_schema": SCHEMA}],
    ),
)
relate(
    "anthropic.messages/cache-control-ignored",
    "head",
    "anthropic.messages/cache-control-absent",
    True,
)
relate(
    "anthropic.messages/cache-control-ignored",
    "msgs",
    "anthropic.messages/cache-control-absent",
    True,
)
add(
    ANTH,
    "cache-control-opaque-top-level",
    1,
    "cache-control",
    "A block's own cache_control is dropped before an opaque block is hashed.",
    anth(
        [
            {
                "role": "user",
                "content": [{"type": "mystery", "v": 1, "cache_control": {"type": "ephemeral"}}],
            }
        ]
    ),
)
add(
    ANTH,
    "cache-control-opaque-plain",
    1,
    "cache-control",
    "The same opaque block without it.",
    anth([{"role": "user", "content": [{"type": "mystery", "v": 1}]}]),
)
relate(
    "anthropic.messages/cache-control-opaque-top-level",
    "msgs",
    "anthropic.messages/cache-control-opaque-plain",
    True,
)
add(
    ANTH,
    "cache-control-nested-kept",
    1,
    "cache-control",
    "A member named cache_control deeper inside a value is data and is kept.",
    anth([{"role": "user", "content": [{"type": "mystery", "v": {"cache_control": 1}}]}]),
)
relate(
    "anthropic.messages/cache-control-nested-kept",
    "msgs",
    "anthropic.messages/cache-control-opaque-plain",
    False,
)
add(
    ANTH,
    "citations-ignored",
    1,
    "parts",
    "citations on a text block are ignored.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "hi",
                        "citations": [{"type": "char_location", "cited_text": "x"}],
                    }
                ],
            }
        ]
    ),
)
relate("anthropic.messages/citations-ignored", "msgs", "anthropic.messages/system-string", True)
add(
    ANTH,
    "user-turn-split",
    1,
    "tool-refs",
    "A user turn [text, tool_result, text] is split into user, tool, user.",
    anth(
        [
            usr("go"),
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "ls", "input": {"path": "/"}}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "before"},
                    {"type": "tool_result", "tool_use_id": "t1", "content": "out"},
                    {"type": "text", "text": "after"},
                ],
            },
        ]
    ),
)
add(
    ANTH,
    "tool-result-error",
    1,
    "parts",
    "is_error true adds error: true; false adds nothing.",
    anth(
        [
            usr("go"),
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "ls", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "ls", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": "boom",
                        "is_error": True,
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": "fine",
                        "is_error": False,
                    },
                ],
            },
        ]
    ),
)
add(
    ANTH,
    "tool-result-blocks",
    1,
    "parts",
    "Tool result content as blocks, and with no content at all.",
    anth(
        [
            usr("go"),
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "ls", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "ls", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [
                            {"type": "text", "text": "a"},
                            {"type": "text", "text": ""},
                            {"type": "text", "text": "b"},
                        ],
                    },
                    {"type": "tool_result", "tool_use_id": "t2"},
                ],
            },
        ]
    ),
)
add(
    ANTH,
    "thinking-signature-ignored",
    1,
    "parts",
    "The thinking signature is not part of the conversation.",
    anth(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "hmm", "signature": "AAA"},
                    {"type": "text", "text": "ok"},
                ],
            },
        ]
    ),
)
add(
    ANTH,
    "thinking-other-signature",
    1,
    "parts",
    "The same turn with another signature.",
    anth(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "hmm", "signature": "BBB"},
                    {"type": "text", "text": "ok"},
                ],
            },
        ]
    ),
)
relate(
    "anthropic.messages/thinking-other-signature",
    "msgs",
    "anthropic.messages/thinking-signature-ignored",
    True,
)
add(
    ANTH,
    "redacted-and-server-blocks",
    1,
    "opaque",
    "redacted_thinking, server_tool_use and web_search_tool_result are opaque parts.",
    anth(
        [
            usr("x"),
            {
                "role": "assistant",
                "content": [
                    {"type": "redacted_thinking", "data": "ENC"},
                    {
                        "type": "server_tool_use",
                        "id": "s1",
                        "name": "web_search",
                        "input": {"query": "q"},
                    },
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "s1",
                        "content": [{"type": "x"}],
                    },
                    {"type": "text", "text": "done"},
                ],
            },
        ]
    ),
)
add(
    ANTH,
    "tool-types",
    1,
    "parts",
    "A custom tool, an explicit custom type, a server tool, and a tool without a schema.",
    anth(
        [usr("x")],
        tools=[
            {"name": "plain", "description": "d", "input_schema": {"type": "object"}},
            {"type": "custom", "name": "explicit", "input_schema": {}},
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
            {"name": "no_schema"},
        ],
    ),
)
add(
    ANTH,
    "empty-text-block-dropped",
    1,
    "parts",
    "Empty user content and empty text blocks leave no parts.",
    anth(
        [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": [{"type": "text", "text": ""}]},
            {"role": "user", "content": [{"type": "text", "text": ""}]},
        ]
    ),
)
add(
    ANTH,
    "media-base64-wrapped",
    1,
    "media",
    "Line-wrapped base64 equals unwrapped.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "\n".join(
                                b64(PNG)[i : i + 6] for i in range(0, len(b64(PNG)), 6)
                            ),
                        },
                    },
                ],
            }
        ]
    ),
)
relate("anthropic.messages/media-base64-wrapped", "msgs", "anthropic.messages/image-data-url", True)
add(
    ANTH,
    "media-base64-bad",
    1,
    "media",
    "Invalid base64 in an image source: the block is opaque.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "!!!"},
                    }
                ],
            }
        ]
    ),
)
add(
    ANTH,
    "media-url-and-file",
    1,
    "media",
    "url and file sources are references.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": "https://example.test/a.png"},
                    },
                    {"type": "image", "source": {"type": "file", "file_id": "file_123"}},
                ],
            }
        ]
    ),
)
add(
    ANTH,
    "media-document",
    1,
    "media",
    "A base64 PDF document and a text document.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64(PDF),
                        },
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "text",
                            "media_type": "text/plain",
                            "data": "plain " + EMOJI + " text",
                        },
                    },
                ],
            }
        ]
    ),
)
add(
    ANTH,
    "media-document-with-title",
    1,
    "media",
    "A document with a title is opaque: the model reads the title beside the file.",
    anth(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "title": "Report",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64(PDF),
                        },
                    }
                ],
            }
        ]
    ),
)

# ============================================================ responses
add(RESP, "input-string", 1, "basics", "A string input is one user message.", resp("Hello, world"))
relate("openai.responses/input-string", "msgs", "openai.responses/user-only", True)
add(
    RESP,
    "instructions-and-system-item",
    1,
    "head",
    "instructions come first in the head, then a leading system or developer item.",
    resp(
        [
            {"type": "message", "role": "developer", "content": "D"},
            {"type": "message", "role": "user", "content": "go"},
        ],
        instructions="I",
    ),
)
add(
    RESP,
    "instructions-non-string",
    1,
    "head",
    "A non-string instructions value is an opaque part of the head system message.",
    resp("go", instructions={"a": 1}),
)
add(
    RESP,
    "reasoning-summary-joined",
    1,
    "parts",
    "Summary texts are joined by a blank line (empty ones skipped).",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "reasoning",
                "id": "r1",
                "summary": [
                    {"type": "summary_text", "text": "one"},
                    {"type": "summary_text", "text": ""},
                    {"type": "summary_text", "text": "two"},
                ],
            },
        ]
    ),
)
add(
    RESP,
    "reasoning-text-preferred",
    1,
    "parts",
    "reasoning_text content wins over the summary.",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "reasoning",
                "id": "r1",
                "content": [{"type": "reasoning_text", "text": "raw"}],
                "summary": [{"type": "summary_text", "text": "sum"}],
            },
        ]
    ),
)
add(
    RESP,
    "reasoning-encrypted-opaque",
    1,
    "opaque",
    "A reasoning item with only encrypted_content is opaque.",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "reasoning",
                "id": "r1",
                "summary": [],
                "encrypted_content": "gAAAA-synthetic",
            },
        ]
    ),
)
add(
    RESP,
    "reasoning-empty-no-message",
    1,
    "parts",
    "A reasoning item with nothing in it opens no assistant message.",
    resp(
        [
            {"role": "user", "content": "x"},
            {"type": "reasoning", "id": "r1", "summary": []},
            {"role": "user", "content": "y"},
        ]
    ),
)
add(
    RESP,
    "assistant-items-grouped",
    1,
    "parts",
    "Reasoning, two assistant messages and a call are one assistant message (known non-equivalence 3).",
    resp(
        [
            {"role": "user", "content": "x"},
            {"type": "reasoning", "id": "r1", "summary": [{"type": "summary_text", "text": "t"}]},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "a"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "b"}],
            },
            {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c1", "output": "r"},
        ]
    ),
)
add(
    RESP,
    "server-tool-items-in-turn",
    1,
    "parts",
    "Server-side tool items are opaque parts inside the assistant turn, in item order.",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "web_search_call",
                "id": "ws1",
                "status": "completed",
                "action": {"type": "search", "query": "q"},
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "a"}],
            },
            {"type": "mcp_call", "id": "m1", "name": "t", "arguments": "{}", "server_label": "s"},
            {"type": "file_search_call", "id": "f1", "queries": ["q"]},
            {"role": "user", "content": "more"},
        ]
    ),
)
add(
    RESP,
    "other-item-kinds",
    1,
    "opaque",
    "item_reference, unknown items and non-object items are role-less opaque messages.",
    resp(
        [
            {"type": "item_reference", "id": "msg_1"},
            {"type": "future_thing", "x": 1},
            5,
            {"role": "user", "content": "x"},
        ]
    ),
)
add(
    RESP,
    "custom-tool-call",
    1,
    "tool-refs",
    "custom_tool_call keeps its input raw; its output is a tool message.",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "custom_tool_call",
                "call_id": "k1",
                "name": "patch",
                "input": "*** Begin ***",
            },
            {"type": "custom_tool_call_output", "call_id": "k1", "output": "applied"},
        ]
    ),
)
add(
    RESP,
    "output-list",
    1,
    "parts",
    "function_call_output with a list output.",
    resp(
        [
            {"role": "user", "content": "x"},
            {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"},
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": [
                    {"type": "input_text", "text": "a"},
                    {"type": "input_text", "text": "b"},
                ],
            },
        ]
    ),
)
add(
    RESP,
    "refusal-part",
    1,
    "opaque",
    "A refusal content part is opaque in place.",
    resp(
        [
            {"role": "user", "content": "x"},
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "a"},
                    {"type": "refusal", "refusal": "no"},
                ],
            },
        ]
    ),
)
add(
    RESP,
    "tools-strict-ignored",
    1,
    "parts",
    "`strict` on a function tool is ignored; other tools are {type, def}.",
    resp(
        "go",
        tools=[
            {
                "type": "function",
                "name": "noop",
                "description": "",
                "parameters": {"type": "object"},
                "strict": True,
            },
            {"type": "web_search_preview", "search_context_size": "low"},
        ],
    ),
)
add(
    RESP,
    "media-items",
    1,
    "media",
    "input_image by URL and by file id, input_file by file id and URL.",
    resp(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "https://example.test/a.png"},
                    {"type": "input_image", "file_id": "file_1"},
                    {"type": "input_file", "file_id": "file_2"},
                    {"type": "input_file", "file_url": "https://example.test/a.pdf"},
                    {"type": "input_image"},
                ],
            }
        ]
    ),
)
add(
    RESP,
    "media-input-file-data",
    1,
    "media",
    "input_file data as a data URL and as bare base64.",
    resp(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_data": dataurl(PDF, "application/pdf")},
                    {"type": "input_file", "file_data": b64(PDF)},
                ],
            }
        ]
    ),
)
add(RESP, "input-not-list-or-string", 1, "basics", "An input that is a number: no ids.", resp(5))

# stateful requests
for _slug, _extra, _d in [
    (
        "stateful-previous-response",
        {"previous_response_id": "resp_synthetic_1"},
        "previous_response_id: message and head ids, no prefix or conversation ids.",
    ),
    (
        "stateful-conversation-string",
        {"conversation": "conv_synthetic_1"},
        "A conversation string makes the request stateful.",
    ),
    (
        "stateful-conversation-object",
        {"conversation": {"id": "conv_synthetic_1"}},
        "A conversation object makes the request stateful.",
    ),
    (
        "stateful-with-instructions",
        {
            "previous_response_id": "resp_synthetic_1",
            "instructions": "I",
            "tools": [{"type": "function", "name": "f", "parameters": {}}],
        },
        "Instructions and tools still give head, sys and tools ids.",
    ),
    (
        "not-stateful-null-previous",
        {"previous_response_id": None, "conversation": None},
        "Null previous_response_id and conversation: an ordinary stateless request.",
    ),
]:
    add(
        RESP,
        _slug,
        1,
        "stateful",
        _d,
        resp(
            [{"role": "user", "content": "continue"}, {"role": "assistant", "content": "ok"}],
            **_extra,
        ),
    )

# ============================================================ conversation and relations
_BASE = [u("What is the capital of France?"), a(text="Paris."), u("And Spain?")]
neutral(
    "conv-base",
    2,
    "conv-tools-free",
    "Reference conversation for the relations below.",
    _BASE,
    system="You answer geography questions.",
    tools=[LS_TOOL],
    dialects=ALL3,
)
neutral(
    "conv-other-tools",
    2,
    "conv-tools-free",
    "Same system and messages, different tools: same conversation id, different head.",
    _BASE,
    system="You answer geography questions.",
    tools=[LS_TOOL, CALC_TOOL],
    dialects=ALL3,
)
neutral(
    "conv-other-system",
    2,
    "conv-tools-free",
    "A different system prompt: a different conversation.",
    _BASE,
    system="You answer history questions.",
    tools=[LS_TOOL],
)
neutral(
    "conv-longer",
    2,
    "conv-tools-free",
    "Later messages do not change the conversation id.",
    _BASE + [a(text="Madrid."), u("Thanks")],
    system="You answer geography questions.",
    tools=[LS_TOOL],
)
neutral(
    "conv-other-opener",
    2,
    "conv-tools-free",
    "A different first message: a different conversation.",
    [u("What is the capital of Italy?")] + _BASE[1:],
    system="You answer geography questions.",
    tools=[LS_TOOL],
)
neutral(
    "conv-spacing-insensitive",
    2,
    "conv-tools-free",
    "Extra whitespace in the first message: same conversation id, different exact ids.",
    [u("  What is the capital  of France?\n")] + _BASE[1:],
    system="You answer geography questions.",
    tools=[LS_TOOL],
)
for d in ALL3:
    p = d + "/"
    relate(p + "conv-other-tools", "conv", p + "conv-base", True)
    for f in ("loose_sys", "sys"):
        relate(p + "conv-other-tools", f, p + "conv-base", True)
    for f in ("loose_tools", "head", "loose_head"):
        relate(p + "conv-other-tools", f, p + "conv-base", False)
p = CHAT + "/"
for o in ("conv-longer", "conv-spacing-insensitive"):
    relate(p + o, "conv", p + "conv-base", True)
for o in ("conv-other-system", "conv-other-opener"):
    relate(p + o, "conv", p + "conv-base", False)
relate(p + "conv-other-system", "sys", p + "conv-base", False)
relate(p + "conv-spacing-insensitive", "msgs", p + "conv-base", False)
relate(p + "conv-longer", "msgs", p + "conv-base", False)

neutral(
    "conv-no-opener",
    2,
    "conv-anchor",
    "The same conversation without the volatile opener.",
    [a(text="Understood"), u("real first question")],
    system="S",
    dialects=(CHAT,),
)
relate("openai.chat/conv-no-opener", "conv", "openai.chat/conv-anchor-skips-opener", True)
relate("openai.chat/conv-no-opener", "msgs", "openai.chat/conv-anchor-skips-opener", False)

# scopes
_SC = "Hello, world"
for _slug, _sc, _d, _same in [
    ("scope-cache-salt", {"cache_salt": "tenant-a"}, "A cache_salt scopes the ids.", False),
    ("scope-tenant", {"tenant": b"tenant-42"}, "A tenant scopes the ids.", False),
    ("scope-both", {"cache_salt": "tenant-a", "tenant": b"tenant-42"}, "Both members.", False),
    (
        "scope-empty-values",
        {"cache_salt": "", "tenant": b""},
        "Empty salt and empty tenant are left out: the empty scope, ids as without a scope.",
        True,
    ),
]:
    add(CHAT, _slug, 1, "scope", _d, chat([usr(_SC)]), scope=_sc)
    relate("openai.chat/" + _slug, "head", "openai.chat/user-only", _same)
    relate("openai.chat/" + _slug, "msgs", "openai.chat/user-only", _same)
    if _same:
        relate("openai.chat/" + _slug, "conv", "openai.chat/user-only", True)
relate("openai.chat/scope-both", "msgs", "openai.chat/scope-tenant", False)
add(
    CHAT,
    "scope-conv",
    2,
    "scope",
    "A scope changes the conversation id too.",
    chat([usr(_SC)]),
    scope={"cache_salt": "tenant-a"},
)
relate("openai.chat/scope-conv", "conv", "openai.chat/user-only", False)

# loose twins: a rewritten text that the loose profile makes equal
_TWINS = [
    ("loose-reasoning-dropped", "reasoning-absent", [u("hi"), a(text="answer"), u("ok")]),
    ("loose-system-reminder", "reminder-absent", [u("before middle after")]),
    ("loose-whitespace-unicode", "whitespace-unicode-collapsed", [u("a b c d e f g")]),
]
for _base, _slug, _turns in _TWINS:
    neutral(
        _slug,
        2,
        "loose",
        f"The text after the rule of {_base}: the loose ids are equal.",
        _turns,
        dialects=(CHAT,),
    )
    relate("openai.chat/" + _slug, "loose_msgs", "openai.chat/" + _base, True)
    relate("openai.chat/" + _slug, "msgs", "openai.chat/" + _base, False)

# system prompt shapes (decision 0005): one system prompt sent as Responses
# `instructions`, as a leading Responses `developer` item, and as a Chat
# `system` or `developer` message. Under loose/1 the role is kept, so the
# instructions shape and the developer shapes are different heads and
# different conversations; each pairs with its Chat twin.
_SP = "You are a coding agent.\n\nAnswer briefly."
_SP_RESP_TOOLS = [
    {"type": "function", "name": "ls", "description": "List a directory", "parameters": SCHEMA}
]
_SP_CHAT_TOOLS = [
    {
        "type": "function",
        "function": {"name": "ls", "description": "List a directory", "parameters": SCHEMA},
    }
]
_SP_USER = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}
add(
    RESP,
    "system-as-instructions",
    2,
    "head",
    "The system prompt in instructions: a head system message.",
    resp([_SP_USER], instructions=_SP, tools=_SP_RESP_TOOLS),
)
add(
    RESP,
    "system-as-developer-item",
    2,
    "head",
    "The same system prompt as a leading developer item: a head developer message. "
    "The role is kept in the exact and loose/1 forms, so sys, head and conv differ "
    "from system-as-instructions.",
    resp(
        [{"type": "message", "role": "developer", "content": _SP}, _SP_USER],
        tools=_SP_RESP_TOOLS,
    ),
)
add(
    CHAT,
    "system-as-system-message",
    2,
    "head",
    "The same system prompt as a Chat system message.",
    chat([{"role": "system", "content": _SP}, usr("hi")], tools=_SP_CHAT_TOOLS),
)
add(
    CHAT,
    "system-as-developer-message",
    2,
    "head",
    "The same system prompt as a Chat developer message.",
    chat([{"role": "developer", "content": _SP}, usr("hi")], tools=_SP_CHAT_TOOLS),
)
_r, _c = RESP + "/", CHAT + "/"
for f in ("msgs", "tools", "loose_msgs", "loose_tools"):
    relate(_r + "system-as-developer-item", f, _r + "system-as-instructions", True)
for f in ("sys", "head", "nodes", "loose_sys", "loose_head", "loose_nodes", "conv"):
    relate(_r + "system-as-developer-item", f, _r + "system-as-instructions", False)
for f in ("sys", "head", "nodes", "loose_sys", "loose_head", "conv"):
    relate(_r + "system-as-developer-item", f, _c + "system-as-developer-message", True)
    relate(_r + "system-as-instructions", f, _c + "system-as-system-message", True)
