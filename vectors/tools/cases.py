# ruff: noqa: E501
"""Case definitions for the kvsig/1 test vectors.

Everything here is synthetic: hand-written inputs, never captured traffic.
``generate.py`` turns these cases into files. Unicode is built with ``chr()``
and JSON escapes with ``BS`` so the sources stay plain ASCII.
"""

from __future__ import annotations

import base64
import json
from typing import Any

BS = chr(92)  # backslash
CHAT, ANTH, RESP = "openai.chat", "anthropic.messages", "openai.responses"
ALL3 = (CHAT, ANTH, RESP)

NBSP, NEL, IDEO, LS, PS = chr(0xA0), chr(0x85), chr(0x3000), chr(0x2028), chr(0x2029)
EMOJI = chr(0x1F600)
ZWSP, BOM, RLO, LRM = chr(0x200B), chr(0xFEFF), chr(0x202E), chr(0x200E)
E_ACUTE, E_PLUS_ACUTE = chr(0xE9), "e" + chr(0x301)
I_DOT, SIGMA, FSIGMA, SHARP_S = chr(0x130), chr(0x3A3), chr(0x3C2), chr(0xDF)
FS, GS, RS, US = chr(0x1C), chr(0x1D), chr(0x1E), chr(0x1F)
FFFD = chr(0xFFFD)

SCHEMA = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
LS_TOOL = ("ls", "List a directory", SCHEMA)
CALC_TOOL = ("calc", "Evaluate", {"type": "object", "properties": {"x": {}}})


class RawJSON:
    """JSON text spliced verbatim into a wire body (for number forms and
    duplicate keys that a parsed object cannot hold)."""

    def __init__(self, text: str) -> None:
        self.text = text


def wire(o: Any) -> str:
    """Compact, ASCII-only JSON text of ``o`` with RawJSON spliced in."""
    if isinstance(o, RawJSON):
        return o.text
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(k) + ":" + wire(v) for k, v in o.items()) + "}"
    if isinstance(o, list):
        return "[" + ",".join(wire(v) for v in o) + "]"
    return json.dumps(o)


def has_raw(o: Any) -> bool:
    if isinstance(o, RawJSON):
        return True
    if isinstance(o, dict):
        return any(has_raw(v) for v in o.values())
    if isinstance(o, list):
        return any(has_raw(v) for v in o)
    return False


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


PNG = b"\x89PNG\r\n\x1a\nsynthetic-image-1"
PNG2 = b"\x89PNG\r\n\x1a\nsynthetic-image-2"
PDF = b"%PDF-1.4 synthetic document"

CASES: list[dict[str, Any]] = []
GROUPS: list[list[str]] = []  # ids that must share one canonical form


def add(
    dialect,
    slug,
    level,
    cat,
    desc,
    body=None,
    *,
    raw=None,
    scope=None,
    options=None,
    reply=None,
    relations=None,
):
    """One vector. ``raw`` is wire text (str) for input_raw_b64."""
    CASES.append(
        dict(
            id=f"{dialect}/{slug}",
            dialect=dialect,
            level=level,
            category=cat,
            description=desc,
            body=body,
            raw=raw,
            scope=scope,
            options=options,
            reply=reply,
            relations=relations or [],
        )
    )
    return f"{dialect}/{slug}"


# ---------------------------------------------------------------- neutral conversations
def u(x):
    return {"u": x}


def a(think=None, text=None, calls=()):
    return {"a": {"think": think, "text": text, "calls": list(calls)}}


def r(call_id, out):
    return {"r": call_id, "out": out}


def img(mime="image/png", data=PNG):
    return {"image": (mime, data)}


def _url(i):
    return f"data:{i['image'][0]};base64,{b64(i['image'][1])}"


def _chat_parts(x):
    if isinstance(x, str):
        return x
    return [
        {"type": "text", "text": p}
        if isinstance(p, str)
        else {"type": "image_url", "image_url": {"url": _url(p)}}
        for p in x
    ]


def _anth_blocks(x):
    if isinstance(x, str):
        return x
    return [
        {"type": "text", "text": p}
        if isinstance(p, str)
        else {
            "type": "image",
            "source": {"type": "base64", "media_type": p["image"][0], "data": b64(p["image"][1])},
        }
        for p in x
    ]


def _resp_parts(x, role):
    if isinstance(x, str):
        return x
    t = "input_text" if role == "user" else "output_text"
    return [
        {"type": t, "text": p}
        if isinstance(p, str)
        else {"type": "input_image", "image_url": _url(p)}
        for p in x
    ]


def render_chat(system, tools, turns):
    m = []
    if system is not None:
        m.append({"role": "system", "content": system})
    for t in turns:
        if "u" in t:
            m.append({"role": "user", "content": _chat_parts(t["u"])})
        elif "a" in t:
            x = t["a"]
            d: dict[str, Any] = {"role": "assistant", "content": x["text"] or None}
            if x["think"]:
                d["reasoning_content"] = x["think"]
            if x["calls"]:
                d["tool_calls"] = [
                    {"id": i, "type": "function", "function": {"name": n, "arguments": g}}
                    for i, n, g in x["calls"]
                ]
            m.append(d)
        else:
            m.append({"role": "tool", "tool_call_id": t["r"], "content": _chat_parts(t["out"])})
    body: dict[str, Any] = {"model": "m", "messages": m}
    if tools:
        body["tools"] = [
            {"type": "function", "function": {"name": n, "description": d, "parameters": s}}
            for n, d, s in tools
        ]
    return body


def render_anth(system, tools, turns, raw_args):
    m: list[dict[str, Any]] = []
    for t in turns:
        if "a" in t:
            x = t["a"]
            c: list[Any] = []
            if x["think"]:
                c.append({"type": "thinking", "thinking": x["think"], "signature": "sig"})
            if x["text"]:
                c.append({"type": "text", "text": x["text"]})
            for i, n, g in x["calls"]:
                c.append(
                    {
                        "type": "tool_use",
                        "id": i,
                        "name": n,
                        "input": RawJSON(g) if raw_args else json.loads(g),
                    }
                )
            m.append({"role": "assistant", "content": c})
            continue
        if "u" in t:
            blocks = _anth_blocks(t["u"])
            blocks = [{"type": "text", "text": blocks}] if isinstance(blocks, str) else blocks
        else:
            out = _anth_blocks(t["out"])
            blocks = [{"type": "tool_result", "tool_use_id": t["r"], "content": out}]
        if m and m[-1]["role"] == "user":
            if isinstance(m[-1]["content"], str):
                m[-1]["content"] = [{"type": "text", "text": m[-1]["content"]}]
            m[-1]["content"].extend(blocks)
        else:
            m.append({"role": "user", "content": blocks})
    for x in m:  # a lone text block reads better as a string
        c = x["content"]
        if x["role"] == "user" and len(c) == 1 and c[0]["type"] == "text":
            x["content"] = c[0]["text"]
    body: dict[str, Any] = {"model": "m", "max_tokens": 64, "messages": m}
    if system is not None:
        body["system"] = system
    if tools:
        body["tools"] = [{"name": n, "description": d, "input_schema": s} for n, d, s in tools]
    return body


def render_resp(system, tools, turns):
    items: list[Any] = []
    for t in turns:
        if "u" in t:
            items.append(
                {"type": "message", "role": "user", "content": _resp_parts(t["u"], "user")}
            )
        elif "a" in t:
            x = t["a"]
            if x["think"]:
                items.append(
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [{"type": "summary_text", "text": x["think"]}],
                    }
                )
            if x["text"]:
                items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": x["text"]}],
                    }
                )
            for i, n, g in x["calls"]:
                items.append({"type": "function_call", "call_id": i, "name": n, "arguments": g})
        else:
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": t["r"],
                    "output": _resp_parts(t["out"], "user"),
                }
            )
    body: dict[str, Any] = {"model": "m", "input": items}
    if system is not None:
        body["instructions"] = system
    if tools:
        body["tools"] = [
            {"type": "function", "name": n, "description": d, "parameters": s, "strict": False}
            for n, d, s in tools
        ]
    return body


def neutral(
    slug,
    level,
    cat,
    desc,
    turns,
    *,
    system=None,
    tools=None,
    dialects=(CHAT,),
    raw_args=False,
    scope=None,
    options=None,
    equivalent=True,
):
    ids_ = []
    for d in dialects:
        if d == CHAT:
            body = render_chat(system, tools, turns)
        elif d == ANTH:
            body = render_anth(system, tools, turns, raw_args)
        else:
            body = render_resp(system, tools, turns)
        raw = None
        if has_raw(body):
            raw, body = wire(body), None
        ids_.append(add(d, slug, level, cat, desc, body, raw=raw, scope=scope, options=options))
    if equivalent and len(ids_) > 1:
        GROUPS.append(ids_)


def call(args, name="calc", cid="c1"):
    return a(calls=[(cid, name, args)])


def args_case(slug, cat, desc, args, *, dialects=(CHAT,), raw_args=True, level=1):
    neutral(
        slug,
        level,
        cat,
        desc,
        [u("compute"), call(args), r("c1", "done")],
        tools=[CALC_TOOL],
        dialects=dialects,
        raw_args=raw_args,
    )


# ================================================================ basics (triples)
neutral(
    "user-only",
    1,
    "basics",
    "A single user message, no system prompt, no tools.",
    [u("Hello, world")],
    dialects=ALL3,
)
neutral(
    "system-user",
    1,
    "basics",
    "A system prompt and one user message.",
    [u("What is 2+2?")],
    system="You are a terse assistant.",
)
neutral(
    "multi-turn",
    1,
    "basics",
    "Alternating user and assistant text.",
    [u("Hi"), a(text="Hello! How can I help?"), u("Name a colour"), a(text="Blue"), u("Another")],
    system="Be brief.",
)
neutral(
    "tool-roundtrip",
    1,
    "basics",
    "System, tool, reasoning, text, one tool call and its result.",
    [
        u("List /tmp"),
        a(think="I should call ls", text="Listing now.", calls=[("c1", "ls", '{"path": "/tmp"}')]),
        r("c1", "a.txt\nb.txt"),
        u("thanks"),
    ],
    system="You can use tools.",
    tools=[LS_TOOL],
    dialects=ALL3,
)
neutral(
    "tools-no-description",
    1,
    "basics",
    "A tool whose description is the empty string.",
    [u("go")],
    tools=[("noop", "", {"type": "object"})],
)

# ================================================================ tool refs (triples)
neutral(
    "results-out-of-order",
    1,
    "tool-refs",
    "Results arrive in the opposite order to the calls; refs are call indexes.",
    [
        u("both"),
        a(calls=[("c1", "ls", '{"path":"/a"}'), ("c2", "ls", '{"path":"/b"}')]),
        r("c2", "B"),
        r("c1", "A"),
    ],
    tools=[LS_TOOL],
    dialects=ALL3,
)
neutral(
    "result-missing-call",
    1,
    "tool-refs",
    "A result whose call id matches no call gets ref -1.",
    [u("go"), a(calls=[("c1", "ls", '{"path":"/a"}')]), r("zzz", "orphan"), r("c1", "A")],
    tools=[LS_TOOL],
    dialects=ALL3,
)
neutral(
    "result-before-call",
    1,
    "tool-refs",
    "A result that precedes the call with its id gets ref -1; the later one gets 0.",
    [u("go"), r("c1", "too early"), a(calls=[("c1", "ls", '{"path":"/a"}')]), r("c1", "on time")],
    tools=[LS_TOOL],
)
neutral(
    "repeated-id-in-message",
    1,
    "tool-refs",
    "Two calls in one turn share an id; a result takes the index of the last one.",
    [
        u("go"),
        a(calls=[("c1", "ls", '{"path":"/a"}'), ("c1", "ls", '{"path":"/b"}')]),
        r("c1", "out"),
    ],
    tools=[LS_TOOL],
)
neutral(
    "id-reused-across-turns",
    1,
    "tool-refs",
    "An id is reused in a later turn: each result refs the nearest preceding holder.",
    [
        u("go"),
        a(calls=[("c1", "ls", '{"path":"/a"}')]),
        r("c1", "first"),
        a(calls=[("c0", "ls", '{"path":"/x"}'), ("c1", "ls", '{"path":"/b"}')]),
        r("c1", "second"),
    ],
    tools=[LS_TOOL],
    dialects=ALL3,
)
neutral(
    "empty-assistant-text",
    1,
    "parts",
    "An assistant turn with an empty text and a call: the empty text is dropped.",
    [u("go"), a(text="", calls=[("c1", "ls", '{"path":"/"}')]), r("c1", "x")],
    tools=[LS_TOOL],
)

# ================================================================ media (triples)
neutral(
    "image-data-url",
    1,
    "media",
    "An inline PNG, sent as base64 in each dialect.",
    [u(["Look at this", img()])],
    dialects=ALL3,
)
neutral(
    "tool-result-with-image",
    1,
    "media",
    "An image inside a tool result stays inside it.",
    [u("shot"), a(calls=[("c1", "screenshot", "{}")]), r("c1", ["Captured", img(data=PNG2)])],
    tools=[("screenshot", "Take a screenshot", {"type": "object"})],
    dialects=ALL3,
)

# ================================================================ unicode (triples)
neutral(
    "unicode-astral",
    1,
    "unicode",
    "Astral characters and a ZWJ sequence, kept verbatim.",
    [u("x" + EMOJI + "y"), a(text=chr(0x1F468) + chr(0x200D) + chr(0x1F4BB) + chr(0x10348))],
    dialects=ALL3,
)
neutral(
    "unicode-no-normalisation",
    1,
    "unicode",
    "NFC and NFD forms stay different; no case folding.",
    [u(E_ACUTE), a(text=E_PLUS_ACUTE), u(I_DOT + SIGMA + FSIGMA + SHARP_S)],
)
neutral(
    "unicode-nbsp-exact",
    1,
    "unicode",
    "NBSP and ideographic space are kept in the exact form.",
    [u("a" + NBSP + "b" + IDEO + "c")],
)
neutral(
    "unicode-separators-1c-1f",
    1,
    "unicode",
    "U+001C to U+001F inside text: kept in the exact form, JSON-escaped in args.",
    [u("a" + FS + "b" + GS + "c" + RS + "d" + US + "e")],
)

# ================================================================ numbers (triples; raw args)
args_case(
    "numbers-floats",
    "numbers",
    "Floats print as the shortest ECMAScript number.",
    '{"x":[0.1,1.5,3.14159,2.5e-5,100.0,1.0e2,0.30000000000000004]}',
    dialects=ALL3,
)
args_case("numbers-negative-zero", "numbers", "-0 and -0.0 print as 0.", '{"x":[-0,-0.0,0,-0e5]}')
args_case(
    "numbers-int-limits",
    "numbers",
    "Integers above 2^53 are rounded to a double first.",
    '{"x":[9007199254740991,9007199254740992,9007199254740993,-9007199254740993,'
    "123456789012345678901234567890]}",
)
args_case(
    "numbers-exponent-forms",
    "numbers",
    "The 1e21 boundary and small exponents.",
    '{"x":[1e20,1e21,1e22,1e-6,1e-7,1E+2,1.5E-10,123456789e-15,5e-324]}',
)
args_case(
    "numbers-overflow-null",
    "numbers",
    "A number too large for a double prints as null.",
    '{"x":[1e999,-1e999,1.7976931348623157e308,1' + "0" * 400 + "]}",
)

# ================================================================ duplicate keys, key order (triples)
args_case(
    "duplicate-keys-args",
    "duplicate-keys",
    "Duplicate keys: the last value wins, at the first key's position.",
    '{"b":1,"a":2,"b":3,"a":{"k":1,"k":2}}',
    dialects=ALL3,
)
args_case(
    "duplicate-keys-surrogate-merge",
    "duplicate-keys",
    "Keys that are equal only after surrogate repair merge.",
    '{"' + BS + 'ud800":1,"' + BS + 'ud801":2,"' + FFFD + '":3}',
)
args_case(
    "args-member-order",
    "args",
    "Member order is kept in the exact form (integer-like keys included) and sorted in loose.",
    '{"z":1,"10":2,"2":3,"b":{"y":1,"x":2},"a":[{"d":1,"c":2}],"' + E_ACUTE + '":4,"A":5}',
    raw_args=False,
    level=2,
)
args_case(
    "args-string-escapes",
    "args",
    "Canonical JSON text escapes only quote, backslash and controls (lowercase hex).",
    '{"s":"q'
    + BS
    + '"b'
    + BS
    + BS
    + "n"
    + BS
    + "n"
    + BS
    + "t"
    + BS
    + "u0001"
    + BS
    + "u007f"
    + BS
    + "u00e9"
    + BS
    + "u2028"
    + BS
    + "/"
    + BS
    + "b"
    + BS
    + "f"
    + BS
    + "r"
    + BS
    + 'u001F"}',
    raw_args=False,
)
args_case(
    "args-scalar-values",
    "args",
    "A scalar JSON value is valid arguments.",
    '"just a string"',
    raw_args=False,
)

# ================================================================ unparsable args (chat, responses)
for _slug, _txt, _d in [
    ("empty-string", "", "Empty arguments are not JSON: kept raw."),
    ("truncated", '{"a":', "Truncated JSON is kept raw."),
    ("trailing-garbage", '{"a":1} x', "Text after the value is not JSON."),
    ("nan-literal", '{"a":NaN}', "NaN is not a JSON literal."),
    ("raw-keeps-spaces", '  {"a" : 1  ', "Raw arguments keep every byte, spaces included."),
    ("leading-zero-number", '{"a":01}', "A leading zero is not JSON."),
]:
    neutral(
        "args-unparsable-" + _slug,
        1,
        "unparsable-args",
        _d,
        [u("go"), call(_txt), r("c1", "x")],
        tools=[CALC_TOOL],
        dialects=(CHAT, RESP) if _slug == "truncated" else (CHAT,),
    )
neutral(
    "args-raw-vs-valid",
    1,
    "unparsable-args",
    "Raw text that equals valid JSON text never collides with it: two calls, one parses.",
    [
        u("go"),
        a(calls=[("c1", "calc", '{"a":1}'), ("c2", "calc", '{"a":1')]),
        r("c1", "x"),
        r("c2", "y"),
    ],
    tools=[CALC_TOOL],
    dialects=(CHAT, RESP),
)
neutral(
    "args-huge-digit-string",
    1,
    "numbers",
    "An integer of 5000 digits is valid JSON and prints as null.",
    [u("go"), call('{"x":' + "9" * 5000 + "}"), r("c1", "x")],
    tools=[CALC_TOOL],
)

# ================================================================ loose/1, each rule alone
REM = "<system-reminder>"
REM_END = "</system-reminder>"
neutral(
    "loose-reasoning-dropped",
    2,
    "loose",
    "Rule 1: reasoning parts are dropped in the loose form only.",
    [u("hi"), a(think="deep thoughts", text="answer"), u("ok")],
    dialects=ALL3,
)
neutral(
    "loose-system-reminder",
    2,
    "loose",
    "Rule 2: a system-reminder block is removed (several blocks, text around them).",
    [u("before " + REM + "one" + REM_END + " middle " + REM + "two" + REM_END + " after")],
    dialects=ALL3,
)
neutral(
    "loose-tag-case-insensitive",
    2,
    "loose",
    "Rule 2: tags match ASCII case-insensitively.",
    [u("a <System-Reminder>x</SYSTEM-REMINDER> b <ENVIRONMENT_CONTEXT>y</environment_context> c")],
)
neutral(
    "loose-unclosed-tag",
    2,
    "loose",
    "Rule 2: an unclosed tag leaves the rest of the text as it is.",
    [u("keep " + REM + " never closed " + "<environment_context>x</environment_context> end")],
)
neutral(
    "loose-date-line",
    2,
    "loose",
    "Rule 3: a line holding only an ISO date is removed.",
    [u("first\n2026-11-21\nsecond\n  2026-11-22  \nthird")],
)
neutral(
    "loose-datetime-lines",
    2,
    "loose",
    "Rule 3: ISO date-times (T or space, fraction, Z or offset) are removed.",
    [
        u(
            "a\n2026-11-21T10:30\n2026-11-21 10:30:15\n2026-11-21T10:30:15.123Z\n"
            "2026-11-21T10:30:15+01:00\n2026-11-21T10:30:15-0500\nb"
        )
    ],
)
neutral(
    "loose-date-in-sentence-kept",
    2,
    "loose",
    "Rule 3 does not touch dates inside sentences or non-ISO or non-ASCII-digit dates.",
    [
        u(
            "Today's date is 2026-11-21.\n2026-11-21 is a Saturday\n2026-13-45x\n"
            + "".join(chr(0x660 + d) for d in (2, 0, 2, 6))
            + "-11-21"
        )
    ],
)
neutral(
    "loose-whitespace-ascii",
    2,
    "loose",
    "Rule 4: runs of ASCII whitespace collapse to one space and the text is trimmed.",
    [u("  a \t\t b\n\n\nc\r\nd \x0b e\x0c f  ")],
)
neutral(
    "loose-whitespace-unicode",
    2,
    "loose",
    "Rule 4: Unicode White_Space and U+001C to U+001F collapse too.",
    [
        u(
            "a"
            + NBSP
            + NBSP
            + "b"
            + IDEO
            + "c"
            + NEL
            + "d"
            + LS
            + PS
            + "e"
            + FS
            + GS
            + RS
            + US
            + "f"
            + chr(0x2003)
            + chr(0x202F)
            + "g"
        )
    ],
    dialects=ALL3,
)
neutral(
    "loose-empty-after-collapse",
    2,
    "loose",
    "Rule 5: texts empty after the rules are dropped; the message stays.",
    [u("   "), a(text=REM + "only" + REM_END), u("real")],
)
neutral(
    "loose-args-sorted",
    2,
    "loose",
    "Rule 6: tool-call args are re-printed with members sorted by code point.",
    [u("go"), call('{"b":2,"a":{"y":1,"x":[{"d":1,"c":2}]},"10":0,"2":1}'), r("c1", "x")],
    tools=[CALC_TOOL],
    dialects=ALL3,
)
neutral(
    "loose-schema-sorted",
    2,
    "loose",
    "Rule 6: tool schemas are sorted in the loose head; the exact head keeps the order.",
    [u("hi")],
    tools=[
        (
            "t",
            "d",
            {
                "type": "object",
                "required": ["a"],
                "properties": {"b": {"type": "string"}, "a": {"type": "integer"}},
            },
        )
    ],
)
neutral(
    "loose-tool-result-text",
    2,
    "loose",
    "Loose rules apply inside tool results.",
    [
        u("go"),
        a(calls=[("c1", "ls", '{"path":"/"}')]),
        r("c1", ["  spaced   out ", REM + "x" + REM_END + " kept"]),
    ],
    tools=[LS_TOOL],
)
neutral(
    "loose-system-prompt",
    2,
    "loose",
    "Loose rules apply to the head too: a system text with a reminder and extra spaces.",
    [u("hi")],
    system="You are  helpful. " + REM + "volatile" + REM_END + "\n2026-11-21\n",
)

# ================================================================ conversation anchor
neutral(
    "conv-anchor-skips-opener",
    2,
    "conv-anchor",
    "The first body message loosens to nothing (a reminder): the anchor is the next one.",
    [u(REM + "session context" + REM_END), a(text="Understood"), u("real first question")],
    system="S",
    dialects=ALL3,
)
neutral(
    "conv-none-all-empty",
    2,
    "conv-anchor",
    "No body message has content in the loose form: no conversation id.",
    [u(REM + "only this" + REM_END), a(think="just thinking"), u("   ")],
    system="S",
)
neutral(
    "conv-anchor-reasoning-only-skipped",
    2,
    "conv-anchor",
    "An assistant turn holding only reasoning is skipped as anchor.",
    [a(think="warming up"), u("the actual start")],
    system="S",
    dialects=(CHAT, RESP),
)
neutral(
    "conv-anchor-tool-call-counts",
    2,
    "conv-anchor",
    "A message with only a tool call has parts, so it can be the anchor.",
    [a(calls=[("c1", "ls", '{"path":"/"}')]), r("c1", "x")],
    tools=[LS_TOOL],
    dialects=(CHAT, RESP),
)


# ================================================================ depth and size caps
def nest(n):
    return "[" * n + "]" * n


neutral(
    "depth-128-ok",
    1,
    "depth-cap",
    "128 nested containers in tool args are allowed.",
    [u("go"), call(nest(128)), r("c1", "x")],
    tools=[CALC_TOOL],
)
neutral(
    "depth-129-none",
    1,
    "depth-cap",
    "A 129th nested container gives the request no ids.",
    [u("go"), call(nest(129)), r("c1", "x")],
    tools=[CALC_TOOL],
    dialects=ALL3,
)
neutral(
    "depth-scalars-do-not-count",
    1,
    "depth-cap",
    "128 containers holding scalars at the bottom: scalars never count.",
    [u("go"), call("[" * 126 + '{"a":[1,"x",null,true]}' + "]" * 126), r("c1", "x")],
    tools=[CALC_TOOL],
)
neutral(
    "depth-schema-129-none",
    1,
    "depth-cap",
    "Tool schemas have the same cap: 129 containers, no ids.",
    [u("hi")],
    tools=[("t", "d", json.loads('{"a":' * 129 + "1" + "}" * 129))],
)
neutral(
    "depth-5000-none",
    1,
    "depth-cap",
    "Very deep arguments (5000) must give no ids without crashing the implementation.",
    [u("go"), call(nest(5000)), r("c1", "x")],
    tools=[CALC_TOOL],
    dialects=(CHAT, RESP),
)

_SIZE_TURNS = [u("size probe " + "x" * 200), a(text="reply " + "y" * 200), u("again")]
neutral(
    "size-at-cap",
    1,
    "size-cap",
    "The size of head payload plus messages (CBOR) equals max_bytes: ids are produced.",
    _SIZE_TURNS,
    system="S",
    options={"max_bytes": "AT"},
)
neutral(
    "size-over-cap",
    1,
    "size-cap",
    "One byte over max_bytes: the request gets no ids.",
    _SIZE_TURNS,
    system="S",
    options={"max_bytes": "UNDER"},
)
neutral(
    "size-tiny-cap",
    1,
    "size-cap",
    "A cap smaller than the head payload alone.",
    [u("hi")],
    options={"max_bytes": 4},
)
