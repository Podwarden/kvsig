// OpenAI Chat Completions (`openai.chat`).

import { isObject, type JsonValue } from "../json.js";
import {
  fromBase64Strict,
} from "../text.js";
import {
  functionTool,
  get,
  mediaBytes,
  mediaFromUrl,
  mediaRef,
  message,
  opaque,
  otherTool,
  parseDataUrl,
  RefTracker,
  splitHead,
  str,
  textPart,
  toolArgs,
  type Canon,
  type Message,
  type Part,
  type Tool,
} from "../model.js";

function partType(p: JsonValue): string {
  return str(get(p, "type")) ?? "";
}

function fileData(data: string): Part | null {
  const d = parseDataUrl(data);
  if (d !== null) return mediaBytes(d.data, d.mime);
  const b = fromBase64Strict(data);
  return b === null ? null : mediaBytes(b, "");
}

function contentPart(p: JsonValue): Part | null {
  if (typeof p === "string") return textPart(p);
  if (!isObject(p)) return opaque(p, "part");
  const t = partType(p);
  // A part without a type that carries a text string is a text part.
  if (!p.has("type") && typeof p.get("text") === "string") return textPart(p.get("text") as string);
  if (t === "text" || t === "input_text" || t === "output_text") {
    return textPart(str(get(p, "text")) ?? "");
  } else if (t === "input_image") {
    // The Responses image part, accepted here too.
    const url = str(get(p, "image_url"));
    const id = str(get(p, "file_id"));
    if (url !== undefined) return mediaFromUrl(url);
    if (id !== undefined) return mediaRef(id, "file_id");
  } else if (t === "image_url") {
    const iu = get(p, "image_url");
    return mediaFromUrl((typeof iu === "string" ? iu : str(get(iu, "url"))) ?? "");
  } else if (t === "input_audio") {
    const a = get(p, "input_audio");
    const data = str(get(a, "data"));
    const format = str(get(a, "format"));
    if (data !== undefined) {
      const b = fromBase64Strict(data);
      if (b !== null) return mediaBytes(b, format ? `audio/${format}` : "");
    }
  } else if (t === "file") {
    const f = get(p, "file");
    const data = str(get(f, "file_data"));
    const id = str(get(f, "file_id"));
    if (data !== undefined) {
      const m = fileData(data);
      if (m !== null) return m;
    } else if (id !== undefined) return mediaRef(id, "file_id");
  }
  return opaque(p, t);
}

export function contentParts(c: JsonValue | undefined): Part[] {
  const out: Part[] = [];
  if (c === undefined || c === null) return out;
  if (typeof c === "string") {
    const p = textPart(c);
    if (p) out.push(p);
    return out;
  }
  if (Array.isArray(c)) {
    for (const x of c) {
      const p = contentPart(x);
      if (p) out.push(p);
    }
    return out;
  }
  out.push(opaque(c, "content"));
  return out;
}

function toolCall(tc: JsonValue, index: number): { part: Part; id: string | undefined } {
  if (!isObject(tc)) return { part: opaque(tc, "tool_call"), id: undefined };
  const id = str(tc.get("id"));
  const t = str(tc.get("type")) ?? "function";
  if (t === "function" && isObject(tc.get("function"))) {
    const f = tc.get("function")!;
    return {
      part: { t: "tool_call", name: str(get(f, "name")) ?? "", ...toolArgs(get(f, "arguments")), ref: index },
      id,
    };
  }
  if (t === "custom" && isObject(tc.get("custom"))) {
    const c = tc.get("custom")!;
    const input = get(c, "input");
    return {
      part: {
        t: "tool_call",
        name: str(get(c, "name")) ?? "",
        args_raw: typeof input === "string" ? input : "",
        ref: index,
      },
      id,
    };
  }
  return { part: opaque(tc, "tool_call"), id };
}

function chatMessage(m: JsonValue, refs: RefTracker): Message {
  if (!isObject(m)) return { role: "", parts: [opaque(m, "message")] };
  const role = str(m.get("role")) ?? "";
  const name = m.get("name");
  if (role === "tool") {
    const parts = contentParts(m.get("content"));
    return message(role, [{ t: "tool_result", ref: refs.resolve(m.get("tool_call_id")), parts }], name);
  }
  if (role === "function") {
    const parts = contentParts(m.get("content"));
    return message(role, [{ t: "tool_result", ref: -1, parts }], name);
  }
  const parts: Part[] = [];
  if (role === "assistant") {
    let r = m.get("reasoning_content");
    if (typeof r !== "string" || r === "") r = m.get("reasoning");
    if (typeof r === "string" && r !== "") parts.push({ t: "reasoning", v: r });
  }
  parts.push(...contentParts(m.get("content")));
  if (role === "assistant") {
    const refusal = m.get("refusal");
    if (refusal !== undefined && refusal !== null) {
      parts.push(opaque(new Map([["refusal", refusal]]), "refusal"));
    }
    const audio = m.get("audio");
    if (audio !== undefined && audio !== null) parts.push(opaque(audio, "audio"));
    const ids: (string | undefined)[] = [];
    const calls = m.get("tool_calls");
    if (Array.isArray(calls)) {
      calls.forEach((tc, i) => {
        const { part, id } = toolCall(tc, i);
        parts.push(part);
        ids.push(id);
      });
    }
    const fc = m.get("function_call");
    if (isObject(fc)) {
      parts.push({
        t: "tool_call",
        name: str(fc.get("name")) ?? "",
        ...toolArgs(fc.get("arguments")),
        ref: ids.length,
      });
      ids.push(undefined);
    } else if (fc !== undefined && fc !== null) {
      parts.push(opaque(fc, "function_call"));
    }
    refs.assistant(ids);
  }
  return message(role, parts, name);
}

function chatTool(t: JsonValue): Tool {
  if (isObject(t) && t.get("type") === "function" && isObject(t.get("function"))) {
    const f = t.get("function")!;
    return functionTool(get(f, "name"), get(f, "description"), get(f, "parameters"));
  }
  return otherTool(t);
}

export function canonicalize(body: JsonValue): Canon | null {
  if (!isObject(body)) return null;
  const msgs = body.get("messages");
  if (!Array.isArray(msgs)) return null;
  const refs = new RefTracker();
  const all = msgs.map((m) => chatMessage(m, refs));
  const tools: Tool[] = [];
  const ts = body.get("tools");
  if (Array.isArray(ts)) for (const t of ts) tools.push(chatTool(t));
  // Deprecated `functions` count only when `tools` is not a list.
  const fs = body.get("functions");
  if (!Array.isArray(ts) && Array.isArray(fs)) {
    for (const f of fs) tools.push(chatTool(new Map<string, JsonValue>([["type", "function"], ["function", f]])));
  }
  const { head, body: rest } = splitHead(all);
  return { head, tools, messages: rest, stateful: false };
}

/** The assistant message of a response (`choices[i].message`), alone. */
export function reply(msg: JsonValue): Message | null {
  if (!isObject(msg)) return null;
  return chatMessage(msg, new RefTracker());
}
