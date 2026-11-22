// The loose profile: the canonical form without harness noise (decision 0002,
// "Loose profile loose/1"; decision 0005 for loose/2). The table is data, and
// its version is part of every loose id label.

import { encode } from "./cbor.js";
import { canonicalJson, parseJson, MAX_DEPTH } from "./json.js";
import type { Canon, Message, Part, Tool } from "./model.js";
import { sha256 } from "./sha256.js";

export interface LooseProfile {
  /** The profile label, for example "loose/1". Hashed into every loose label. */
  readonly version: string;
  /** (open, close) tag pairs whose blocks are removed, ASCII case-insensitively. */
  readonly blockTags: readonly (readonly [string, string])[];
  /** The code points that collapse to one space. */
  readonly whitespace: ReadonlySet<number>;
  /** (from, to) roles renamed in the loose form. Empty in loose/1. */
  readonly roleMap: readonly (readonly [string, string])[];
}

/** Unicode White_Space plus U+001C..U+001F. */
export const WHITESPACE_V1: ReadonlySet<number> = new Set([
  0x0009, 0x000a, 0x000b, 0x000c, 0x000d, 0x001c, 0x001d, 0x001e, 0x001f, 0x0020, 0x0085, 0x00a0,
  0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
]);

const BLOCK_TAGS_V1 = [
  ["<system-reminder>", "</system-reminder>"],
  ["<environment_context>", "</environment_context>"],
] as const;

/** The default profile, pinned by vectors/v1. */
export const LOOSE_V1: LooseProfile = Object.freeze({
  version: "loose/1",
  blockTags: BLOCK_TAGS_V1,
  whitespace: WHITESPACE_V1,
  roleMap: [],
});

/** loose/1 plus: a `developer` message reads as `system`. Experimental (decision 0005). */
export const LOOSE_V2: LooseProfile = Object.freeze({
  version: "loose/2",
  blockTags: BLOCK_TAGS_V1,
  whitespace: WHITESPACE_V1,
  roleMap: [["developer", "system"]] as const,
});

/** Throws a TypeError when `p` is not a valid profile table. */
export function validateProfile(p: LooseProfile): void {
  if (!p.version || p.version.includes("\0") || p.version.includes(":")) {
    throw new TypeError("version must be a non-empty label without NUL or ':'");
  }
  for (const [o, c] of p.blockTags) {
    if (typeof o !== "string" || typeof c !== "string" || !o || !c) {
      throw new TypeError("blockTags must be (open, close) pairs of non-empty strings");
    }
  }
  if (p.whitespace.size === 0) throw new TypeError("whitespace must not be empty");
  for (const c of p.whitespace) {
    if (!Number.isInteger(c) || c < 0 || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff)) {
      throw new TypeError("whitespace must hold Unicode scalar values");
    }
  }
  const from = new Set<string>();
  for (const [f, t] of p.roleMap) {
    if (!f || !t) throw new TypeError("roleMap must be (from, to) pairs of non-empty strings");
    if (from.has(f)) throw new TypeError("roleMap must map each role at most once");
    from.add(f);
  }
}

/** 8 bytes that change with any part of the table (for keying caches). */
export function profileFingerprint(p: LooseProfile): Uint8Array {
  const table: Record<string, unknown> = {
    version: p.version,
    block_tags: p.blockTags.map((t) => [t[0], t[1]]),
    whitespace: [...p.whitespace].sort((a, b) => a - b),
  };
  if (p.roleMap.length > 0) table.role_map = p.roleMap.map((t) => [t[0], t[1]]);
  return sha256(encode(table as never)).slice(0, 8);
}

function asciiLower(s: string): string {
  return s.replace(/[A-Z]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 32));
}

function stripBlocks(v: string, open: string, close: string): string {
  const low = asciiLower(v);
  const o = asciiLower(open);
  const c = asciiLower(close);
  let out = "";
  let pos = 0;
  for (;;) {
    const a = low.indexOf(o, pos);
    if (a < 0) break;
    const b = low.indexOf(c, a + o.length);
    if (b < 0) break;
    out += v.slice(pos, a);
    pos = b + c.length;
  }
  return pos === 0 ? v : out + v.slice(pos);
}

// A line holding only an ISO date or date-time; lines end at LF only.
const DATE_LINE =
  /^[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]+)?)?(?:Z|[+-][0-9]{2}:?[0-9]{2})?)?[ \t]*$/;
const DATE_HINT = /(?:^|\n)[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}/;

function collapse(v: string, ws: ReadonlySet<number>): string {
  const words: string[] = [];
  let cur = "";
  for (const ch of v) {
    if (ws.has(ch.codePointAt(0)!)) {
      if (cur) words.push(cur);
      cur = "";
    } else cur += ch;
  }
  if (cur) words.push(cur);
  return words.join(" ");
}

/** One text in its loose form ("" means the text is dropped). */
export function looseText(v: string, profile: LooseProfile = LOOSE_V1): string {
  if (v.includes("<")) {
    for (const [o, c] of profile.blockTags) v = stripBlocks(v, o, c);
  }
  if (DATE_HINT.test(v)) {
    v = v
      .split("\n")
      .map((line) => (DATE_LINE.test(line) ? "" : line))
      .join("\n");
  }
  return collapse(v, profile.whitespace);
}

function resort(text: string): string {
  return canonicalJson(parseJson(text, MAX_DEPTH), true);
}

function looseParts(parts: readonly Part[], p: LooseProfile): Part[] {
  const out: Part[] = [];
  for (const part of parts) {
    if (part.t === "reasoning") continue;
    if (part.t === "text") {
      const v = looseText(part.v, p);
      if (v) out.push({ t: "text", v });
    } else if (part.t === "tool_result") {
      out.push({ ...part, parts: looseParts(part.parts, p) });
    } else if (part.t === "tool_call" && part.args !== undefined) {
      out.push({ ...part, args: resort(part.args) });
    } else {
      out.push(part);
    }
  }
  return out;
}

/** One message in its loose form. */
export function looseMessage(m: Message, profile: LooseProfile = LOOSE_V1): Message {
  const out: { role: string; parts: Part[]; name?: string } = { ...m, parts: looseParts(m.parts, profile) };
  for (const [from, to] of profile.roleMap) {
    if (m.role === from) {
      out.role = to;
      break;
    }
  }
  return out;
}

function looseTool(t: Tool): Tool {
  return "schema" in t ? { ...t, schema: resort(t.schema) } : { ...t, def: resort(t.def) };
}

/** `canon` in its loose form. Never mutates its input. */
export function loose(canon: Canon, profile: LooseProfile = LOOSE_V1): Canon {
  return {
    head: canon.head.map((m) => looseMessage(m, profile)),
    tools: canon.tools.map(looseTool),
    messages: canon.messages.map((m) => looseMessage(m, profile)),
    stateful: canon.stateful,
  };
}
