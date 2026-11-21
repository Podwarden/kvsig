"""Anthropic Messages request and response bodies to the canonical form.

The mapping is chosen so that a conversation sent through OpenAI Chat
Completions and through Anthropic Messages gives the same canonical form:

- ``system`` (a string or text blocks) is the head's one system message.
- A user turn's ``tool_result`` blocks each become their own ``tool`` message,
  in place; the other blocks of the turn stay together as user messages. That
  is how Chat Completions expresses the same turn.
- ``thinking`` blocks are reasoning parts, at their position; the signature
  is not part of the conversation. ``redacted_thinking`` is opaque.
- ``cache_control`` and ``citations`` are ignored everywhere.
"""

from __future__ import annotations

import binascii
from typing import Any

from kvsig.model import (
    HEAD_ROLES,
    Budget,
    Canon,
    Message,
    Part,
    b64decode,
    json_text,
    media_bytes,
    media_ref,
    opaque,
    text_part,
    without_cache_control,
)


def _source(block: dict[str, Any], budget: Budget) -> Part:
    """An ``image`` or ``document`` block with a plain source."""
    src = block.get("source")
    if not isinstance(src, dict):
        return opaque(block, budget)
    kind = src.get("type")
    mime = src.get("media_type")
    mime = mime if isinstance(mime, str) else ""
    if kind == "base64":
        data = src.get("data")
        try:
            return media_bytes(b64decode(data), mime)
        except (binascii.Error, ValueError):
            return opaque(block, budget)
    if kind == "text" and isinstance(src.get("data"), str):
        return media_bytes(src["data"].encode("utf-8", "surrogatepass"), mime)
    if kind == "url" and isinstance(src.get("url"), str):
        return media_ref(src["url"], "url")
    if kind == "file" and isinstance(src.get("file_id"), str):
        return media_ref(src["file_id"], "file_id")
    return opaque(block, budget)


def _content_block(b: Any, budget: Budget) -> Part | None:
    """A user or tool-result block other than ``tool_result``. None means an
    empty text, which is dropped."""
    if isinstance(b, str):
        return text_part(b, budget)
    if not isinstance(b, dict):
        return opaque(b, budget, "block")
    t = b.get("type")
    if t == "text":
        v = b.get("text")
        return text_part(v if isinstance(v, str) else "", budget)
    if t == "image":
        return _source(b, budget)
    if t == "document" and not any(k in b for k in ("title", "context")):
        # A document with a title or context carries text the model reads
        # beside the file: keep all of it, as opaque.
        return _source(b, budget)
    return opaque(b, budget)


def _blocks(content: Any, budget: Budget) -> list[Part]:
    if content is None:
        return []
    if isinstance(content, str):
        p = text_part(content, budget)
        return [p] if p else []
    if not isinstance(content, list):
        return [opaque(content, budget, "content")]
    out: list[Part] = []
    for b in content:
        p = _content_block(b, budget)
        if p is not None:
            out.append(p)
    return out


def _user_turn(role: str, content: Any, seen: dict[str, int], budget: Budget) -> list[Message]:
    """One user turn, split so each ``tool_result`` is its own message."""
    if not isinstance(content, list):
        return [{"role": role, "parts": _blocks(content, budget)}]
    out: list[Message] = []
    pending: list[Part] = []
    pending_open = False  # a user message has started (even if all its texts were empty)

    def flush() -> None:
        nonlocal pending, pending_open
        if pending_open:
            out.append({"role": role, "parts": pending})
        pending, pending_open = [], False

    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            flush()
            tid = b.get("tool_use_id")
            ref = seen.get(tid, -1) if isinstance(tid, str) else -1
            result: Part = {
                "t": "tool_result",
                "ref": ref,
                "parts": _blocks(b.get("content"), budget),
            }
            if b.get("is_error") is True:
                result["error"] = True
            out.append({"role": "tool", "parts": [result]})
        else:
            pending_open = True
            p = _content_block(b, budget)
            if p is not None:
                pending.append(p)
    flush()
    if not out:
        out.append({"role": role, "parts": []})
    return out


def _assistant_turn(role: str, content: Any, seen: dict[str, int], budget: Budget) -> Message:
    if not isinstance(content, list):
        return {"role": role, "parts": _blocks(content, budget)}
    parts: list[Part] = []
    index = 0
    for b in content:
        if not isinstance(b, dict):
            parts.append(opaque(b, budget, "block"))
            continue
        t = b.get("type")
        if t == "thinking":
            v = b.get("thinking")
            if isinstance(v, str) and v:
                budget.charge(len(v))
                parts.append({"t": "reasoning", "v": v})
        elif t == "text":
            p = text_part(b.get("text") if isinstance(b.get("text"), str) else "", budget)
            if p is not None:
                parts.append(p)
        elif t == "tool_use":
            name = b.get("name")
            name = name if isinstance(name, str) else ""
            budget.charge(len(name))
            parts.append(
                {
                    "t": "tool_call",
                    "name": name,
                    "args": json_text(b.get("input"), budget),
                    "ref": index,
                }
            )
            tid = b.get("id")
            if isinstance(tid, str):
                seen[tid] = index
            index += 1
        else:
            # redacted_thinking, server_tool_use, *_tool_result, and anything newer
            parts.append(opaque(b, budget))
    return {"role": role, "parts": parts}


def message(m: Any, seen: dict[str, int], budget: Budget) -> list[Message]:
    if not isinstance(m, dict):
        return [{"role": "", "parts": [opaque(m, budget, "message")]}]
    role = m.get("role")
    role = role if isinstance(role, str) else ""
    budget.charge(len(role))
    if role == "assistant":
        return [_assistant_turn(role, m.get("content"), seen, budget)]
    return _user_turn(role, m.get("content"), seen, budget)


def _system(system: Any, budget: Budget) -> list[Message]:
    if system is None or system == "" or system == []:
        return []
    return [{"role": "system", "parts": _blocks(system, budget)}]


def _tool(t: Any, budget: Budget) -> dict[str, Any]:
    if isinstance(t, dict) and t.get("type") in (None, "custom") and isinstance(t.get("name"), str):
        name, desc = t["name"], t.get("description")
        desc = desc if isinstance(desc, str) else ""
        budget.charge(len(name) + len(desc))
        return {"name": name, "desc": desc, "schema": json_text(t.get("input_schema"), budget)}
    t_type = t.get("type") if isinstance(t, dict) else None
    return {
        "type": t_type if isinstance(t_type, str) else "",
        "def": json_text(without_cache_control(t), budget),
    }


def canonicalize(body: dict[str, Any], budget: Budget) -> Canon | None:
    msgs_in = body.get("messages")
    if not isinstance(msgs_in, list):
        return None
    tools_in = body.get("tools")
    tools = [_tool(t, budget) for t in tools_in] if isinstance(tools_in, list) else []
    head = _system(body.get("system"), budget)
    body_msgs: list[Message] = []
    seen: dict[str, int] = {}
    for m in msgs_in:
        for c in message(m, seen, budget):
            if not body_msgs and c["role"] in HEAD_ROLES:
                head.append(c)
            else:
                body_msgs.append(c)
    return Canon(head=head, tools=tools, messages=body_msgs)


def reply(m: dict[str, Any], budget: Budget) -> Message:
    """A Messages response (or its assistant message), canonicalised alone."""
    role = m.get("role") if isinstance(m.get("role"), str) else "assistant"
    return _assistant_turn(role, m.get("content"), {}, budget)
