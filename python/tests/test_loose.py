import time

import pytest

from kvsig import LOOSE_V1, canonicalize, loose
from kvsig.loose import WHITESPACE_V1, LooseProfile, loose_text


def test_whitespace_table_matches_python_isspace():
    assert WHITESPACE_V1 == frozenset(c for c in range(0x110000) if chr(c).isspace())


def test_strips_reminders_case_insensitively():
    assert loose_text("a <System-Reminder>x</SYSTEM-REMINDER> b") == "a b"
    assert loose_text("<environment_context>cwd</environment_context>hi") == "hi"


def test_unclosed_tag_keeps_the_rest_and_is_linear():
    assert loose_text("a <system-reminder> b") == "a <system-reminder> b"
    t0 = time.perf_counter()
    loose_text("<system-reminder>" * 100_000)
    assert time.perf_counter() - t0 < 1.0


def test_non_ascii_case_folding_does_not_shift_offsets():
    # "İ".lower() is two characters; ASCII-only matching must not be confused by it
    assert loose_text("İİ<system-reminder>x</system-reminder>y") == "İİy"


def test_date_lines_only():
    assert loose_text("2026-11-20\nhello") == "hello"
    assert loose_text("x\n  2026-11-20T10:00:00Z  \ny") == "x y"
    assert loose_text("on 2026-11-20 we") == "on 2026-11-20 we"
    # non-ASCII digits are not dates
    assert loose_text("٢٠٢٦-11-20") == "٢٠٢٦-11-20"


def test_whitespace_collapses_and_trims():
    assert loose_text("  a \u00a0\t b\u3000\n") == "a b"


def test_no_harness_specific_preambles():
    # loose/1 keeps ordinary text, whatever it starts with
    assert (
        loose_text("I switched to a new code base today") == "I switched to a new code base today"
    )


def test_drops_reasoning_and_sorts_args_and_schema():
    body = {
        "tools": [{"type": "function", "function": {"name": "f", "parameters": {"b": 1, "a": 2}}}],
        "messages": [
            {
                "role": "assistant",
                "reasoning": "hmm",
                "tool_calls": [
                    {
                        "id": "x",
                        "type": "function",
                        "function": {"name": "f", "arguments": '{"b":1,"a":2}'},
                    }
                ],
            }
        ],
    }
    c = canonicalize(body)
    assert c is not None
    lc = loose(c)
    assert lc.tools[0]["schema"] == '{"a":2,"b":1}'
    assert lc.messages[0]["parts"] == [
        {"t": "tool_call", "name": "f", "args": '{"a":2,"b":1}', "ref": 0}
    ]
    # the input is not mutated
    assert c.messages[0]["parts"][0]["t"] == "reasoning"


def test_profile_version_is_named():
    assert LOOSE_V1.version == "loose/1"


@pytest.mark.parametrize(
    "kw",
    [
        {"version": ""},
        {"version": "loose:2"},
        {"version": "a\x00b"},
        {"whitespace": frozenset()},
        {"whitespace": frozenset({0xD800})},
        {"block_tags": (("<a>",),)},
        {"block_tags": (("", "</a>"),)},
    ],
)
def test_profiles_are_validated(kw):
    args = {"version": "x/1", "block_tags": LOOSE_V1.block_tags, "whitespace": WHITESPACE_V1}
    with pytest.raises(ValueError):
        LooseProfile(**{**args, **kw})


def test_fingerprint_changes_with_the_table_not_just_the_version():
    other = LooseProfile("loose/1", (("<x>", "</x>"),), WHITESPACE_V1)
    assert other.version == LOOSE_V1.version
    assert other.fingerprint != LOOSE_V1.fingerprint


def test_custom_whitespace_set():
    p = LooseProfile("t/1", (), frozenset({ord(" "), ord("_")}))
    assert loose_text("a__b  c\td", p) == "a b c\td"


def test_loose_keeps_the_message_name():
    c = canonicalize(
        {
            "messages": [
                {"role": "user", "name": "alice", "content": " hi  there "},
                {"role": "user", "content": "hi there"},
            ]
        }
    )
    named, plain = loose(c).messages
    assert named == {"role": "user", "name": "alice", "parts": [{"t": "text", "v": "hi there"}]}
    assert plain == {"role": "user", "parts": [{"t": "text", "v": "hi there"}]}
