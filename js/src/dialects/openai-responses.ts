// OpenAI Responses (`openai.responses`).

import { isObject, type JsonValue } from "../json.js";
import { fromBase64Strict } from "../text.js";
import {
  functionTool,
  get,
  mediaBytes,
  mediaFromUrl,
  mediaRef,
  opaque,
  otherTool,
  parseDataUrl,
  RefTracker,
  splitHead,
  str,
  textPart,
  toolArgs,
  truthy,
  type Canon,
  type Message,
  type Part,
  type Tool,
} from "../model.js";

const TEXT_TYPES = new Set(["input_text", "output_text", "text"]);
const ASSISTANT_SIDE = new Set(["reasoning", "function_call", "custom_tool_call"]);
/** Server-side tool items: opaque parts of the assistant turn they appear in. */
const SERVER_ITEMS = new Set([
  "web_search_call",
  "file_search_call",
  "computer_call",
  "code_interpreter_call",
  "image_generation_call",
  "local_shell_call",
  "mcp_call",
  "mcp_list_tools",
  "mcp_approval_request",
]);
const OUTPUTS = new Set(["function_call_output", "custom_tool_call_output"]);

function fileData(data: string): Part | null {
  const d = parseDataUrl(data);
  if (d !== null) return mediaBytes(d.data, d.mime);
  const b = fromBase64Strict(data);
  return b === null ? null : mediaBytes(b, "");
}

function contentPart(p: JsonValue): Part | null {
  if (typeof p === "string") return textPart(p);
  if (!isObject(p)) return opaque(p, "part");
  const t = str(p.get("type")) ?? "";
  if (TEXT_TYPES.has(t)) {
    return textPart(str(p.get("text")) ?? "");
  } else if (t === "input_image") {
    const url = str(p.get("image_url"));
    const id = str(p.get("file_id"));
    if (url !== undefined) return mediaFromUrl(url);
    if (id !== undefined) return mediaRef(id, "file_id");
  } else if (t === "input_file") {
    const data = str(p.get("file_data"));
    const id = str(p.get("file_id"));
    const url = str(p.get("file_url"));
    if (data !== undefined) {
      const m = fileData(data);
      if (m !== null) return m;
    } else if (id !== undefined) return mediaRef(id, "file_id");
    else if (url !== undefined) return mediaFromUrl(url);
  } else if (t === "refusal") {
    return opaque(new Map([["refusal", p.get("refusal") ?? null]]), "refusal");
  }
  return opaque(p, t);
}

function contentParts(c: JsonValue | undefined): Part[] {
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

/** An item's type: "message" when it has none, "" when it is not a string. */
function itemType(it: JsonValue): string | undefined {
  if (!isObject(it)) return undefined;
  const t = it.get("type");
  if (t === undefined) return "message";
  return typeof t === "string" ? t : "";
}

function isAssistantSide(it: JsonValue): boolean {
  const t = itemType(it);
  if (t === undefined) return false;
  if (t === "message") return get(it, "role") === "assistant";
  return ASSISTANT_SIDE.has(t) || SERVER_ITEMS.has(t);
}

function reasoningPart(it: JsonValue): Part | null {
  const texts = (list: JsonValue | undefined, type: string): string[] =>
    Array.isArray(list)
      ? list.flatMap((p) => {
          const v = get(p, "text");
          return get(p, "type") === type && typeof v === "string" && v !== "" ? [v] : [];
        })
      : [];
  let t = texts(get(it, "content"), "reasoning_text");
  if (t.length === 0) t = texts(get(it, "summary"), "summary_text");
  if (t.length > 0) return { t: "reasoning", v: t.join("\n\n") };
  const enc = get(it, "encrypted_content");
  if (truthy(enc)) {
    return opaque(new Map([["encrypted_content", enc!]]), "reasoning");
  }
  return null;
}

/** One run of assistant-side items as one assistant message. */
function assistantGroup(items: readonly JsonValue[], refs: RefTracker): Message | null {
  const parts: Part[] = [];
  const ids: (string | undefined)[] = [];
  // Every item opens the message except a reasoning item with nothing in it.
  let opened = false;
  for (const it of items) {
    const t = itemType(it)!;
    if (t === "reasoning") {
      const p = reasoningPart(it);
      if (p) parts.push(p);
      opened ||= p !== null;
      continue;
    }
    opened = true;
    if (t === "message") {
      parts.push(...contentParts(get(it, "content")));
    } else if (t === "function_call" || t === "custom_tool_call") {
      const name = str(get(it, "name")) ?? "";
      const ref = ids.length;
      if (t === "function_call") {
        parts.push({ t: "tool_call", name, ...toolArgs(get(it, "arguments")), ref });
      } else {
        const input = get(it, "input");
        parts.push({ t: "tool_call", name, args_raw: typeof input === "string" ? input : "", ref });
      }
      ids.push(str(get(it, "call_id")));
    } else {
      parts.push(opaque(it, t));
    }
  }
  if (!opened) return null;
  refs.assistant(ids);
  return { role: "assistant", parts };
}

function items(input: readonly JsonValue[], refs: RefTracker): Message[] {
  const out: Message[] = [];
  let i = 0;
  while (i < input.length) {
    const it = input[i]!;
    if (isAssistantSide(it)) {
      let j = i;
      while (j < input.length && isAssistantSide(input[j]!)) j++;
      const m = assistantGroup(input.slice(i, j), refs);
      if (m) out.push(m);
      i = j;
      continue;
    }
    i++;
    const t = itemType(it);
    if (t === undefined) {
      out.push({ role: "", parts: [opaque(it, "item")] });
    } else if (t === "message") {
      out.push({ role: str(get(it, "role")) ?? "", parts: contentParts(get(it, "content")) });
    } else if (OUTPUTS.has(t)) {
      out.push({
        role: "tool",
        parts: [{ t: "tool_result", ref: refs.resolve(get(it, "call_id")), parts: contentParts(get(it, "output")) }],
      });
    } else {
      out.push({ role: "", parts: [opaque(it, t)] });
    }
  }
  return out;
}

function responsesTool(t: JsonValue): Tool {
  if (isObject(t) && t.get("type") === "function") {
    return functionTool(t.get("name"), t.get("description"), t.get("parameters"));
  }
  return otherTool(t);
}

export function canonicalize(body: JsonValue): Canon | null {
  if (!isObject(body)) return null;
  const input = body.get("input");
  let list: JsonValue[];
  if (typeof input === "string") list = [new Map<string, JsonValue>([["role", "user"], ["content", input]])];
  else if (Array.isArray(input)) list = input;
  else return null;
  const refs = new RefTracker();
  const msgs = items(list, refs);
  const head: Message[] = [];
  const ins = body.get("instructions");
  if (typeof ins === "string") {
    if (ins !== "") head.push({ role: "system", parts: [{ t: "text", v: ins }] });
  } else if (ins !== undefined && ins !== null) {
    head.push({ role: "system", parts: [opaque(ins, "instructions")] });
  }
  const split = splitHead(msgs);
  head.push(...split.head);
  const tools: Tool[] = [];
  const ts = body.get("tools");
  if (Array.isArray(ts)) for (const t of ts) tools.push(responsesTool(t));
  const prev = body.get("previous_response_id");
  const conv = body.get("conversation");
  const stateful = truthy(prev) || truthy(conv);
  return { head, tools, messages: split.body, stateful };
}

/** The `output` items of a whole response, as one assistant message. */
export function reply(resp: JsonValue): Message | null {
  if (!isObject(resp)) return null;
  const o = resp.get("output");
  const out = Array.isArray(o) ? o : [];
  // The reply is the response's assistant-side items as one assistant message.
  return assistantGroup(out.filter(isAssistantSide), new RefTracker()) ?? { role: "assistant", parts: [] };
}
