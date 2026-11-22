// kvsig: keyed, content-derived ids for LLM chat conversations.
//
// An independent TypeScript implementation of the kvsig specification
// (`kvsig/1`, draft 0.1). Pure functions; the only runtime dependency is
// @noble/hashes. Hostile input never throws: it yields null.

import { encode as cborEncode, type CborValue } from "./cbor.js";
import * as anthropicMessages from "./dialects/anthropic-messages.js";
import * as openaiChat from "./dialects/openai-chat.js";
import * as openaiResponses from "./dialects/openai-responses.js";
import { fromJS, JsonSyntaxError, NoIds, parseJson, type JsonValue } from "./json.js";
import { asCbor, DEFAULT_MAX_BYTES, finish, type Canon, type Message } from "./model.js";

export { DEFAULT_MAX_BYTES, HEAD_ROLES } from "./model.js";
export type {
  Canon,
  FunctionTool,
  MediaPart,
  Message,
  OpaquePart,
  OtherTool,
  Part,
  ReasoningPart,
  TextPart,
  Tool,
  ToolCallPart,
  ToolResultPart,
} from "./model.js";
export {
  ids,
  idsAllEpochs,
  Key,
  KEY_BYTES,
  KeyRing,
  messageId,
  scopeFrom,
  SPEC_LABEL,
  TEST_KEY,
  type Ids,
  type IdsOptions,
  type MessageIdOptions,
} from "./ids.js";
export {
  loose,
  looseMessage,
  looseText,
  LOOSE_V1,
  LOOSE_V2,
  profileFingerprint,
  validateProfile,
  WHITESPACE_V1,
  type LooseProfile,
} from "./loose.js";
export { parseJson, canonicalJson, type JsonValue, type JsonObject } from "./json.js";
export { sha256, hmacSha256 } from "./sha256.js";

/** The library version; it matches the spec draft revision (0.1). */
export const VERSION = "0.1.0";

/** The dialects this release implements. */
export const SUPPORTED = ["openai.chat", "openai.responses", "anthropic.messages"] as const;
export type Dialect = (typeof SUPPORTED)[number];

interface Adapter {
  canonicalize(body: JsonValue): Canon | null;
  reply(msg: JsonValue): Message | null;
}

const ADAPTERS: Record<Dialect, Adapter> = {
  "openai.chat": openaiChat,
  "openai.responses": openaiResponses,
  "anthropic.messages": anthropicMessages,
};

function adapter(dialect: string): Adapter {
  const a = (ADAPTERS as Record<string, Adapter | undefined>)[dialect];
  if (a === undefined) throw new RangeError(`dialect ${JSON.stringify(dialect)} is not implemented in this release`);
  return a;
}

export interface CanonicalizeOptions {
  /** The size cap in bytes of canonical CBOR (default 2 MiB). */
  maxBytes?: number;
  /** Called with an unexpected internal error (a bug); the result is still null. */
  onError?: (error: unknown) => void;
}

/**
 * A request or response body: a parsed value (as from `JSON.parse`), or the
 * raw JSON text as a string or bytes. Pass the raw text when you have it:
 * JavaScript objects reorder integer-like keys (`{"b":1,"10":2}`), and the
 * exact form keeps the wire order of tool arguments and schemas.
 */
export type Body = unknown;

function toJson(body: Body): JsonValue {
  if (typeof body === "string" || body instanceof Uint8Array) return parseJson(body);
  return fromJS(body);
}

function failOpen<T>(fn: () => T | null, opts: CanonicalizeOptions): T | null {
  try {
    return fn();
  } catch (e) {
    if (e instanceof NoIds || e instanceof JsonSyntaxError || e instanceof RangeError) return null;
    if (opts.onError) opts.onError(e);
    else console.error("kvsig: unexpected error; returning no ids", e);
    return null;
  }
}

/**
 * The canonical form of a request body, or null when the request gets no ids:
 * not a chat body, over `maxBytes` of canonical CBOR, or nested too deep.
 * Throws only for an unknown dialect.
 */
export function canonicalize(body: Body, dialect: Dialect = "openai.chat", opts: CanonicalizeOptions = {}): Canon | null {
  const a = adapter(dialect);
  const max = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  return failOpen(() => {
    const c = a.canonicalize(toJson(body));
    return c === null ? null : finish(c, max);
  }, opts);
}

/**
 * A response's assistant message, canonicalised alone, so that its
 * {@link messageId} equals the id of the same message in the next request.
 *
 * `message` is the assistant message (`openai.chat`: `choices[i].message`),
 * the whole response (`anthropic.messages`), or the whole response with its
 * `output` items (`openai.responses`).
 */
export function canonicalizeReply(message: Body, dialect: Dialect = "openai.chat", opts: CanonicalizeOptions = {}): Message | null {
  const a = adapter(dialect);
  const max = opts.maxBytes ?? DEFAULT_MAX_BYTES;
  return failOpen(() => {
    const m = a.reply(toJson(message));
    return m !== null && cborEncode(asCbor(m)).length <= max ? m : null;
  }, opts);
}

/** The canonical CBOR encoding (decision 0001) of a canonical value. */
export function encode(v: unknown): Uint8Array {
  return cborEncode(v as CborValue);
}

/**
 * The canonical bytes of a whole request, as the test vectors give them: the
 * CBOR of `{"head": [...], "tools": [...], "messages": [...]}`.
 */
export function canonicalBytes(c: Canon): Uint8Array {
  return cborEncode(asCbor({ head: c.head, tools: c.tools, messages: c.messages }));
}

/** The conversation id of a set of ids (null when there is none). */
export function conversationId(i: { readonly conv: string | null }): string | null {
  return i.conv;
}
