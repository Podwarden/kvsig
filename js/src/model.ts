// The canonical data model (decision 0002) and the helpers every dialect
// mapping shares.

import { encode, type CborValue } from "./cbor.js";
import { canonicalJson, isObject, NoIds, parseJson, MAX_DEPTH, type JsonValue } from "./json.js";
import { sha256 } from "./sha256.js";
import { fromBase64Strict, utf8 } from "./text.js";

export interface TextPart {
  readonly t: "text";
  readonly v: string;
}
export interface ReasoningPart {
  readonly t: "reasoning";
  readonly v: string;
}
export interface MediaPart {
  readonly t: "media";
  /** 32 raw bytes: SHA-256 of the decoded data, the URL or the file id. */
  readonly sha256: Uint8Array;
  readonly mime: string;
  readonly src: "bytes" | "url" | "file_id";
}
export interface ToolCallPart {
  readonly t: "tool_call";
  readonly name: string;
  /** Canonical JSON text of the arguments, when they parse. */
  readonly args?: string;
  /** The arguments exactly as sent, when they do not parse. */
  readonly args_raw?: string;
  readonly ref: number;
}
export interface ToolResultPart {
  readonly t: "tool_result";
  readonly ref: number;
  readonly parts: readonly Part[];
  readonly error?: true;
}
export interface OpaquePart {
  readonly t: "opaque";
  readonly type: string;
  readonly sha256: Uint8Array;
}
export type Part = TextPart | ReasoningPart | MediaPart | ToolCallPart | ToolResultPart | OpaquePart;

export interface Message {
  readonly role: string;
  readonly parts: readonly Part[];
  /** Present only when the request gives a non-empty name. */
  readonly name?: string;
}

export interface FunctionTool {
  readonly name: string;
  readonly desc: string;
  /** Canonical JSON text of the parameter schema ("null" when absent). */
  readonly schema: string;
}
export interface OtherTool {
  readonly type: string;
  /** Canonical JSON text of the whole definition. */
  readonly def: string;
}
export type Tool = FunctionTool | OtherTool;

/** The canonical form of one request. */
export interface Canon {
  readonly head: readonly Message[];
  readonly tools: readonly Tool[];
  readonly messages: readonly Message[];
  /** True for a Responses request that continues server-side history. */
  readonly stateful: boolean;
}

export const HEAD_ROLES: ReadonlySet<string> = new Set(["system", "developer"]);
/** The default size cap: 2 MiB of canonical CBOR (decision 0002). */
export const DEFAULT_MAX_BYTES = 2 * 1024 * 1024;

export function asCbor(v: unknown): CborValue {
  return v as CborValue;
}

export function headPayload(c: Pick<Canon, "head" | "tools">): CborValue {
  return asCbor({ head: c.head, tools: c.tools });
}

/** `c`, or null when its canonical CBOR is over `maxBytes`. */
export function finish(c: Canon, maxBytes: number): Canon | null {
  let total = encode(headPayload(c)).length;
  if (total > maxBytes) return null;
  for (const m of c.messages) {
    total += encode(asCbor(m)).length;
    if (total > maxBytes) return null;
  }
  return c;
}

export function textPart(v: string): TextPart | null {
  return v === "" ? null : { t: "text", v };
}

export function opaque(v: JsonValue, type: string): OpaquePart {
  return { t: "opaque", type, sha256: sha256(utf8(canonicalJson(withoutCacheControl(v)))) };
}

export function mediaBytes(data: Uint8Array, mime: string): MediaPart {
  return { t: "media", sha256: sha256(data), mime, src: "bytes" };
}

export function mediaRef(ref: string, src: "url" | "file_id", mime = ""): MediaPart {
  return { t: "media", sha256: sha256(utf8(ref)), mime, src };
}

export function str(v: JsonValue | undefined): string | undefined {
  return typeof v === "string" ? v : undefined;
}

export function get(o: JsonValue | undefined, k: string): JsonValue | undefined {
  return isObject(o) ? o.get(k) : undefined;
}

/** `o` without its own top-level `cache_control` member. */
export function withoutCacheControl(o: JsonValue): JsonValue {
  if (!isObject(o) || !o.has("cache_control")) return o;
  const m = new Map(o);
  m.delete("cache_control");
  return m;
}

function percentDecode(s: string): Uint8Array {
  const raw = utf8(s);
  const out: number[] = [];
  const hex = (c: number) =>
    c >= 0x30 && c <= 0x39
      ? c - 0x30
      : c >= 0x41 && c <= 0x46
        ? c - 0x37
        : c >= 0x61 && c <= 0x66
          ? c - 0x57
          : -1;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i]!;
    if (c === 0x25 && i + 2 < raw.length) {
      const a = hex(raw[i + 1]!);
      const b = hex(raw[i + 2]!);
      if (a >= 0 && b >= 0) {
        out.push(a * 16 + b);
        i += 2;
        continue;
      }
    }
    out.push(c);
  }
  return Uint8Array.from(out);
}

/**
 * A data URL as decoded bytes and MIME type, or null when it is not a data
 * URL or its base64 does not decode.
 */
export function parseDataUrl(url: string): { data: Uint8Array; mime: string } | null {
  if (!url.startsWith("data:")) return null;
  const comma = url.indexOf(",");
  if (comma < 0) return null;
  const header = url.slice(5, comma).split(";");
  const mime = header[0]!.trim().toLowerCase();
  const isB64 = header.slice(1).some((p) => p.trim().toLowerCase() === "base64");
  const payload = url.slice(comma + 1);
  if (isB64) {
    const data = fromBase64Strict(payload);
    return data === null ? null : { data, mime };
  }
  return { data: percentDecode(payload), mime };
}

/** A media part for an image or file URL: inline data URLs are bytes. */
export function mediaFromUrl(url: string): MediaPart {
  const d = parseDataUrl(url);
  return d === null ? mediaRef(url, "url") : mediaBytes(d.data, d.mime);
}

/**
 * The `args`/`args_raw` member of a tool call from an arguments string: the
 * canonical JSON text when it parses, else the raw text.
 */
export function toolArgs(raw: JsonValue | undefined): { args: string } | { args_raw: string } {
  if (raw === undefined || raw === null) return { args: "null" };
  if (typeof raw !== "string") return { args: canonicalJson(raw) };
  let v: JsonValue;
  try {
    v = parseJson(raw, MAX_DEPTH);
  } catch (e) {
    if (e instanceof NoIds) throw e;
    return { args_raw: raw };
  }
  return { args: canonicalJson(v) };
}

/**
 * Resolves tool-result references (decision 0002): a result's ref is the index
 * of its call in the nearest preceding assistant message holding that id.
 */
export class RefTracker {
  private readonly turns: Map<string, number>[] = [];

  /** Record the call ids of one assistant message, by index. */
  assistant(ids: readonly (string | undefined)[]): void {
    const m = new Map<string, number>();
    ids.forEach((id, i) => {
      if (id !== undefined) m.set(id, i); // the last call with an id wins
    });
    this.turns.push(m);
  }

  resolve(id: JsonValue | undefined): number {
    if (typeof id !== "string") return -1;
    for (let i = this.turns.length - 1; i >= 0; i--) {
      const r = this.turns[i]!.get(id);
      if (r !== undefined) return r;
    }
    return -1;
  }
}

/** Split a message list into the head (leading system/developer run) and body. */
export function splitHead(msgs: readonly Message[]): { head: Message[]; body: Message[] } {
  let i = 0;
  while (i < msgs.length && HEAD_ROLES.has(msgs[i]!.role)) i++;
  return { head: msgs.slice(0, i), body: msgs.slice(i) };
}

export function message(role: string, parts: Part[], name?: JsonValue): Message {
  return typeof name === "string" && name !== "" ? { name, role, parts } : { role, parts };
}

export function functionTool(name: JsonValue | undefined, desc: JsonValue | undefined, params: JsonValue | undefined): FunctionTool {
  return {
    name: str(name) ?? "",
    desc: str(desc) ?? "",
    schema: canonicalJson(params === undefined ? null : params),
  };
}

export function otherTool(t: JsonValue): OtherTool {
  return { type: str(get(t, "type")) ?? "", def: canonicalJson(t) };
}

/** Python truthiness of a JSON value (null, false, 0, "", [] and {} are false). */
export function truthy(v: JsonValue | undefined): boolean {
  if (v === undefined || v === null || v === false || v === 0 || v === "") return false;
  if (Array.isArray(v)) return v.length > 0;
  if (v instanceof Map) return v.size > 0;
  return true;
}
