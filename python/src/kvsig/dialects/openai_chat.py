"""OpenAI Chat Completions request and response bodies to the canonical form."""

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
    media_from_url,
    media_ref,
    opaque,
    text_part,
    tool_args,
)

_TEXT_TYPES = ("text", "input_text", "output_text")


def _file(p: dict[str, Any], budget: Budget) -> Part:
    f = p.get("file")
    if isinstance(f, dict):
        data = f.get("file_data")
        if isinstance(data, str) and data:
            if data.startswith("data:"):
                return media_from_url(data)
            try:
                return media_bytes(b64decode(data), "")
            except (binascii.Error, ValueError):
                return opaque(p, budget)
        fid = f.get("file_id")
        if isinstance(fid, str) and fid:
            return media_ref(fid, "file_id")
    return opaque(p, budget)


def _content_parts(content: Any, budget: Budget) -> list[Part]:
    out: list[Part] = []

    def add(part: Part | None) -> None:
        if part is not None:
            out.append(part)

    if content is None:
        return out
    if isinstance(content, str):
        add(text_part(content, budget))
        return out
    if not isinstance(content, list):
        out.append(opaque(content, budget, "content"))
        return out
    for p in content:
        if isinstance(p, str):
            add(text_part(p, budget))
            continue
        if not isinstance(p, dict):
            out.append(opaque(p, budget, "part"))
            continue
        t = p.get("type")
        if t in _TEXT_TYPES or ("type" not in p and isinstance(p.get("text"), str)):
            v = p.get("text")
            add(text_part(v if isinstance(v, str) else "", budget))
        elif t == "image_url":
            iu = p.get("image_url")
            out.append(media_from_url(iu.get("url") if isinstance(iu, dict) else iu))
        elif t == "video_url":
            vu = p.get("video_url")
            out.append(media_from_url(vu.get("url") if isinstance(vu, dict) else vu))
        elif t == "input_audio" and isinstance(p.get("input_audio"), dict):
            a = p["input_audio"]
            fmt = a.get("format")
            try:
                data = b64decode(a.get("data") or "")
            except (binascii.Error, ValueError, TypeError):
                out.append(opaque(p, budget))
                continue
            out.append(media_bytes(data, f"audio/{fmt}" if isinstance(fmt, str) and fmt else ""))
        elif t == "file":
            out.append(_file(p, budget))
        elif t == "input_image":
            url = p.get("image_url")
            fid = p.get("file_id")
            if isinstance(url, str) and url:
                out.append(media_from_url(url))
            elif isinstance(fid, str) and fid:
                out.append(media_ref(fid, "file_id"))
            else:
                out.append(opaque(p, budget))
        else:
            out.append(opaque(p, budget))
    return out


def _call(name: Any, k: str, v: str, ref: int, budget: Budget) -> Part:
    name = name if isinstance(name, str) else ""
    budget.charge(len(name))
    return {"t": "tool_call", "name": name, k: v, "ref": ref}


def _tool_call(call: Any, ref: int, budget: Budget) -> Part:
    if not isinstance(call, dict):
        return opaque(call, budget, "tool_call")
    fn = call.get("function")
    if isinstance(fn, dict):
        k, v = tool_args(fn.get("arguments"), budget)
        return _call(fn.get("name"), k, v, ref, budget)
    custom = call.get("custom")
    if isinstance(custom, dict):
        raw = custom.get("input")
        raw = raw if isinstance(raw, str) else ""
        budget.charge(len(raw))
        return _call(custom.get("name"), "args_raw", raw, ref, budget)
    return opaque(call, budget, "tool_call")


def message(m: Any, seen: dict[str, int], budget: Budget) -> Message:
    """One chat message. ``seen`` maps tool-call id to its index in the nearest
    preceding assistant message, and is updated by assistant messages."""
    if not isinstance(m, dict):
        return {"role": "", "parts": [opaque(m, budget, "message")]}
    role = m.get("role")
    role = role if isinstance(role, str) else ""
    budget.charge(len(role))
    out: Message = {"role": role}
    name = m.get("name")
    if isinstance(name, str) and name:
        budget.charge(len(name))
        out["name"] = name

    if role == "tool" or role == "function":
        # A result. "function" is the deprecated form: it names the function
        # (kept in "name" above) and cannot reference a call.
        ref = -1
        cid = m.get("tool_call_id")
        if role == "tool" and isinstance(cid, str):
            ref = seen.get(cid, -1)
        result = {"t": "tool_result", "ref": ref, "parts": _content_parts(m.get("content"), budget)}
        out["parts"] = [result]
        return out

    parts: list[Part] = []
    if role == "assistant":
        for key in ("reasoning_content", "reasoning"):
            r = m.get(key)
            if isinstance(r, str) and r:
                budget.charge(len(r))
                parts.append({"t": "reasoning", "v": r})
                break
    parts.extend(_content_parts(m.get("content"), budget))
    if role == "assistant":
        refusal = m.get("refusal")
        if refusal is not None:
            parts.append(opaque({"refusal": refusal}, budget, "refusal"))
        audio = m.get("audio")
        if audio is not None:
            parts.append(opaque(audio, budget, "audio"))
        index = 0
        calls = m.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                parts.append(_tool_call(call, index, budget))
                if isinstance(call, dict) and isinstance(call.get("id"), str):
                    seen[call["id"]] = index
                index += 1
        fc = m.get("function_call")
        if fc is not None:
            if isinstance(fc, dict):
                k, v = tool_args(fc.get("arguments"), budget)
                parts.append(_call(fc.get("name"), k, v, index, budget))
            else:
                parts.append(opaque(fc, budget, "function_call"))
    out["parts"] = parts
    return out


def _tool(t: Any, budget: Budget) -> dict[str, Any]:
    fn = t.get("function") if isinstance(t, dict) and t.get("type") == "function" else None
    if isinstance(fn, dict):
        name, desc = fn.get("name"), fn.get("description")
        name = name if isinstance(name, str) else ""
        desc = desc if isinstance(desc, str) else ""
        budget.charge(len(name) + len(desc))
        return {"name": name, "desc": desc, "schema": json_text(fn.get("parameters"), budget)}
    t_type = t.get("type") if isinstance(t, dict) else None
    return {"type": t_type if isinstance(t_type, str) else "", "def": json_text(t, budget)}


def canonicalize(body: dict[str, Any], budget: Budget) -> Canon | None:
    msgs_in = body.get("messages")
    if not isinstance(msgs_in, list):
        return None
    tools_in = body.get("tools")
    if not isinstance(tools_in, list):
        legacy = body.get("functions")
        tools_in = (
            [{"type": "function", "function": f} for f in legacy]
            if isinstance(legacy, list)
            else []
        )
    tools = [_tool(t, budget) for t in tools_in]
    head: list[Message] = []
    body_msgs: list[Message] = []
    seen: dict[str, int] = {}
    for m in msgs_in:
        c = message(m, seen, budget)
        # The head is the leading run of system/developer messages only. A
        # later one stays in the body, in order, so prefixes stay prefixes.
        if not body_msgs and c["role"] in HEAD_ROLES:
            head.append(c)
        else:
            body_msgs.append(c)
    return Canon(head=head, tools=tools, messages=body_msgs)


def reply(m: dict[str, Any], budget: Budget) -> Message:
    """A response's assistant message, canonicalised alone."""
    return message(m, {}, budget)
