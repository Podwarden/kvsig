// Anthropic Messages (`anthropic.messages`).

import { canonicalJson, isObject, type JsonValue } from "../json.js";
import { fromBase64Strict, utf8 } from "../text.js";
import {
  functionTool,
  get,
  mediaBytes,
  mediaRef,
  message,
  opaque,
  otherTool,
  RefTracker,
  splitHead,
  str,
  textPart,
  withoutCacheControl,
  type Canon,
  type Message,
  type Part,
  type Tool,
} from "../model.js";

function blockOpaque(b: JsonValue): Part {
  return opaque(withoutCacheControl(b), str(get(b, "type")) ?? "");
}

function media(b: JsonValue): Part {
  const t = str(get(b, "type"));
  if (t === "document" && (get(b, "title") !== undefined || get(b, "context") !== undefined)) {
    return blockOpaque(b);
  }
  const src = get(b, "source");
  const st = str(get(src, "type"));
  const mime = str(get(src, "media_type")) ?? "";
  if (st === "base64") {
    const data = str(get(src, "data"));
    const bytes = data === undefined ? null : fromBase64Strict(data);
    if (bytes !== null) return mediaBytes(bytes, mime);
  } else if (st === "text") {
    const data = str(get(src, "data"));
    if (data !== undefined) return mediaBytes(utf8(data), mime);
  } else if (st === "url") {
    const url = str(get(src, "url"));
    if (url !== undefined) return mediaRef(url, "url");
  } else if (st === "file") {
    const id = str(get(src, "file_id"));
    if (id !== undefined) return mediaRef(id, "file_id");
  }
  return blockOpaque(b);
}

/** A content block that is not a tool_use or tool_result. */
function block(b: JsonValue, assistant: boolean): Part | null {
  if (typeof b === "string" && !assistant) return textPart(b);
  if (!isObject(b)) return opaque(b, "block");
  const t = str(b.get("type"));
  if (t === "text") return textPart(str(b.get("text")) ?? "");
  if (t === "image" || t === "document") return media(b);
  if (t === "thinking" && assistant) {
    const v = str(b.get("thinking")) ?? "";
    return v === "" ? null : { t: "reasoning", v };
  }
  return blockOpaque(b);
}

function resultParts(c: JsonValue | undefined): Part[] {
  if (c === undefined || c === null) return [];
  if (typeof c === "string") {
    const p = textPart(c);
    return p ? [p] : [];
  }
  if (Array.isArray(c)) {
    const out: Part[] = [];
    for (const b of c) {
      const p = block(b, false);
      if (p) out.push(p);
    }
    return out;
  }
  return [opaque(c, "content")];
}

function assistantMessage(content: JsonValue | undefined, refs: RefTracker, role = "assistant"): Message {
  const parts: Part[] = [];
  const ids: (string | undefined)[] = [];
  if (typeof content === "string") {
    const p = textPart(content);
    if (p) parts.push(p);
  } else if (Array.isArray(content)) {
    for (const b of content) {
      if (isObject(b) && b.get("type") === "tool_use") {
        parts.push({
          t: "tool_call",
          name: str(b.get("name")) ?? "",
          args: canonicalJson(b.has("input") ? b.get("input")! : null),
          ref: ids.length,
        });
        ids.push(str(b.get("id")));
        continue;
      }
      const p = block(b, true);
      if (p) parts.push(p);
    }
  } else if (content !== undefined && content !== null) {
    parts.push(opaque(content, "content"));
  }
  refs.assistant(ids);
  return { role, parts };
}

function turn(m: JsonValue, refs: RefTracker): Message[] {
  if (!isObject(m)) return [{ role: "", parts: [opaque(m, "message")] }];
  const role = str(m.get("role")) ?? "";
  const content = m.get("content");
  if (role === "assistant") return [assistantMessage(content, refs)];
  if (!Array.isArray(content)) {
    const parts: Part[] = [];
    if (typeof content === "string") {
      const p = textPart(content);
      if (p) parts.push(p);
    } else if (content !== undefined && content !== null) parts.push(opaque(content, "content"));
    return [message(role, parts)];
  }
  // Each tool_result block is its own `tool` message, in place; the blocks
  // between them stay together as messages with the turn's role.
  const out: Message[] = [];
  let run: Part[] | null = null;
  for (const b of content) {
    if (isObject(b) && b.get("type") === "tool_result") {
      if (run !== null) out.push(message(role, run));
      run = null;
      const r: Part = b.get("is_error") === true
        ? { t: "tool_result", ref: refs.resolve(b.get("tool_use_id")), error: true, parts: resultParts(b.get("content")) }
        : { t: "tool_result", ref: refs.resolve(b.get("tool_use_id")), parts: resultParts(b.get("content")) };
      out.push({ role: "tool", parts: [r] });
      continue;
    }
    run ??= [];
    const p = block(b, false);
    if (p) run.push(p);
  }
  if (run !== null || out.length === 0) out.push(message(role, run ?? []));
  return out;
}

function anthropicTool(t: JsonValue): Tool {
  const type = get(t, "type");
  if (isObject(t) && (type === undefined || type === null || type === "custom") && typeof t.get("name") === "string") {
    return functionTool(t.get("name"), t.get("description"), t.get("input_schema"));
  }
  return otherTool(withoutCacheControl(t));
}

function systemMessage(s: JsonValue | undefined): Message | null {
  if (s === undefined || s === null) return null;
  if (typeof s === "string") return s === "" ? null : { role: "system", parts: [{ t: "text", v: s }] };
  if (Array.isArray(s)) {
    const parts: Part[] = [];
    for (const b of s) {
      const p = block(b, false);
      if (p) parts.push(p);
    }
    return s.length === 0 ? null : { role: "system", parts };
  }
  return { role: "system", parts: [opaque(s, "content")] };
}

export function canonicalize(body: JsonValue): Canon | null {
  if (!isObject(body)) return null;
  const msgs = body.get("messages");
  if (!Array.isArray(msgs)) return null;
  const refs = new RefTracker();
  const all: Message[] = [];
  const sys = systemMessage(body.get("system"));
  if (sys) all.push(sys);
  for (const m of msgs) all.push(...turn(m, refs));
  const tools: Tool[] = [];
  const ts = body.get("tools");
  if (Array.isArray(ts)) for (const t of ts) tools.push(anthropicTool(t));
  const { head, body: rest } = splitHead(all);
  return { head, tools, messages: rest, stateful: false };
}

/** A whole response: its `content` blocks as one assistant message. */
export function reply(resp: JsonValue): Message | null {
  if (!isObject(resp)) return null;
  return assistantMessage(resp.get("content"), new RefTracker(), str(resp.get("role")) ?? "assistant");
}
