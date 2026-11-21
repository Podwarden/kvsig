"""OpenAI Responses request and response bodies to the canonical form.

The mapping is chosen so that a conversation sent through Chat Completions and
through Responses gives the same canonical form:

- ``instructions`` is the head's first system message; a leading run of
  ``system``/``developer`` message items follows it in the head.
- A run of consecutive assistant-side items (``reasoning``, assistant
  ``message``, ``function_call``, ``custom_tool_call``) is one assistant
  message, in item order: Chat Completions carries a whole turn in one message.
- ``function_call_output`` / ``custom_tool_call_output`` are ``tool`` messages.
- A ``reasoning`` item is a reasoning part made of its ``reasoning_text``
  content, or else its summary texts, joined by a blank line. An item that
  carries only ``encrypted_content`` is opaque.
- ``previous_response_id`` or ``conversation`` makes the request stateful:
  the body is not the whole conversation, so it gets no prefix or
  conversation ids.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from kvsig.model import (
    HEAD_ROLES,
    Budget,
    Canon,
    Message,
    Part,
    json_text,
    media_bytes,
    media_from_url,
    media_ref,
    opaque,
    text_part,
    tool_args,
)

_TEXT_TYPES = ("input_text", "output_text", "text")
_ASSISTANT_SIDE = ("reasoning", "function_call", "custom_tool_call")
_OUTPUTS = ("function_call_output", "custom_tool_call_output")


def _file(p: dict[str, Any], budget: Budget) -> Part:
    data = p.get("file_data")
    if isinstance(data, str) and data:
        if data.startswith("data:"):
            return media_from_url(data)
        try:
            return media_bytes(base64.b64decode(data, validate=True), "")
        except (binascii.Error, ValueError):
            return opaque(p, budget)
    for key, src in (("file_id", "file_id"), ("file_url", "url")):
        v = p.get(key)
        if isinstance(v, str) and v:
            return media_ref(v, src)
    return opaque(p, budget)


def _content(content: Any, budget: Budget) -> list[Part]:
    if content is None:
        return []
    if isinstance(content, str):
        p = text_part(content, budget)
        return [p] if p else []
    if not isinstance(content, list):
        return [opaque(content, budget, "content")]
    out: list[Part] = []
    for p in content:
        if isinstance(p, str):
            tp = text_part(p, budget)
            if tp:
                out.append(tp)
            continue
        if not isinstance(p, dict):
            out.append(opaque(p, budget, "part"))
            continue
        t = p.get("type")
        if t in _TEXT_TYPES:
            tp = text_part(p.get("text") if isinstance(p.get("text"), str) else "", budget)
            if tp:
                out.append(tp)
        elif t == "input_image":
            url, fid = p.get("image_url"), p.get("file_id")
            if isinstance(url, str) and url:
                out.append(media_from_url(url))
            elif isinstance(fid, str) and fid:
                out.append(media_ref(fid, "file_id"))
            else:
                out.append(opaque(p, budget))
        elif t == "input_file":
            out.append(_file(p, budget))
        elif t == "refusal":
            # the same value Chat Completions carries in a message's "refusal"
            out.append(opaque({"refusal": p.get("refusal")}, budget, "refusal"))
        else:
            out.append(opaque(p, budget))
    return out


def _reasoning(item: dict[str, Any], budget: Budget) -> Part | None:
    def texts(key: str, kind: str) -> list[str]:
        v = item.get(key)
        if not isinstance(v, list):
            return []
        return [
            x["text"]
            for x in v
            if isinstance(x, dict) and x.get("type") == kind and isinstance(x.get("text"), str)
        ]

    parts = texts("content", "reasoning_text") or texts("summary", "summary_text")
    v = "\n\n".join(t for t in parts if t)
    if v:
        budget.charge(len(v))
        return {"t": "reasoning", "v": v}
    if item.get("encrypted_content"):
        return opaque({"encrypted_content": item["encrypted_content"]}, budget, "reasoning")
    return None


def _is_assistant_side(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    t = item.get("type")
    if t in _ASSISTANT_SIDE:
        return True
    return t in (None, "message") and item.get("role") == "assistant"


class _Builder:
    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.msgs: list[Message] = []
        self.seen: dict[str, int] = {}
        self.group: Message | None = None  # the open assistant message
        self.calls = 0

    def _assistant(self) -> Message:
        if self.group is None:
            self.group = {"role": "assistant", "parts": []}
            self.msgs.append(self.group)
            self.calls = 0
        return self.group

    def item(self, it: Any) -> None:
        b = self.budget
        if not _is_assistant_side(it):
            self.group = None
        if not isinstance(it, dict):
            self.msgs.append({"role": "", "parts": [opaque(it, b, "item")]})
            return
        t = it.get("type")
        if _is_assistant_side(it):
            g = self._assistant()
            if t == "reasoning":
                p = _reasoning(it, b)
                if p is not None:
                    g["parts"].append(p)
            elif t in ("function_call", "custom_tool_call"):
                name = it.get("name")
                name = name if isinstance(name, str) else ""
                b.charge(len(name))
                if t == "function_call":
                    k, v = tool_args(it.get("arguments"), b)
                else:
                    raw = it.get("input")
                    k, v = "args_raw", raw if isinstance(raw, str) else ""
                    b.charge(len(v))
                g["parts"].append({"t": "tool_call", "name": name, k: v, "ref": self.calls})
                cid = it.get("call_id")
                if isinstance(cid, str):
                    self.seen[cid] = self.calls
                self.calls += 1
            else:
                g["parts"].extend(_content(it.get("content"), b))
            return
        if t in _OUTPUTS:
            cid = it.get("call_id")
            ref = self.seen.get(cid, -1) if isinstance(cid, str) else -1
            result = {"t": "tool_result", "ref": ref, "parts": _content(it.get("output"), b)}
            self.msgs.append({"role": "tool", "parts": [result]})
            return
        if t in (None, "message"):
            role = it.get("role")
            role = role if isinstance(role, str) else ""
            b.charge(len(role))
            self.msgs.append({"role": role, "parts": _content(it.get("content"), b)})
            return
        # web_search_call, file_search_call, computer_call, mcp_*, item_reference, ...
        self.msgs.append({"role": "", "parts": [opaque(it, b)]})


def _tool(t: Any, budget: Budget) -> dict[str, Any]:
    if isinstance(t, dict) and t.get("type") == "function":
        name, desc = t.get("name"), t.get("description")
        name = name if isinstance(name, str) else ""
        desc = desc if isinstance(desc, str) else ""
        budget.charge(len(name) + len(desc))
        return {"name": name, "desc": desc, "schema": json_text(t.get("parameters"), budget)}
    t_type = t.get("type") if isinstance(t, dict) else None
    return {"type": t_type if isinstance(t_type, str) else "", "def": json_text(t, budget)}


def canonicalize(body: dict[str, Any], budget: Budget) -> Canon | None:
    inp = body.get("input")
    if isinstance(inp, str):
        items: list[Any] = [{"type": "message", "role": "user", "content": inp}]
    elif isinstance(inp, list):
        items = inp
    else:
        return None
    tools_in = body.get("tools")
    tools = [_tool(t, budget) for t in tools_in] if isinstance(tools_in, list) else []
    head: list[Message] = []
    instr = body.get("instructions")
    if isinstance(instr, str) and instr:
        tp = text_part(instr, budget)
        head.append({"role": "system", "parts": [tp] if tp else []})
    bld = _Builder(budget)
    for it in items:
        bld.item(it)
    body_msgs: list[Message] = []
    for m in bld.msgs:
        if not body_msgs and m["role"] in HEAD_ROLES:
            head.append(m)
        else:
            body_msgs.append(m)
    stateful = bool(body.get("previous_response_id")) or bool(body.get("conversation"))
    return Canon(head=head, tools=tools, messages=body_msgs, stateful=stateful)


def reply(resp: dict[str, Any], budget: Budget) -> Message:
    """A Responses response: its ``output`` items, canonicalised alone as one
    assistant message (what the next request carries back as input items)."""
    out = resp.get("output")
    bld = _Builder(budget)
    g = bld._assistant()
    for it in out if isinstance(out, list) else []:
        if _is_assistant_side(it):
            bld.group = g
            bld.item(it)
    return g
