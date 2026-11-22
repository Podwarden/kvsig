// JSON values in member order, a strict parser, and the canonical JSON text of
// decision 0002 (used for tool arguments, tool schemas and opaque values).
//
// JavaScript objects reorder integer-like keys, so a parsed object is a Map:
// it keeps the order the members had on the wire, and setting an existing key
// keeps its first position (the duplicate-key rule of decision 0002).

import { compareCodePoints, decodeUtf8, wellFormed } from "./text.js";

/** A JSON value with objects as order-preserving Maps. */
export type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
export type JsonObject = Map<string, JsonValue>;

/** Thrown when a request gets no ids (size cap, depth cap, not a chat body). */
export class NoIds extends Error {
  constructor(why: string) {
    super(why);
    this.name = "NoIds";
  }
}

/** Thrown by the parser on text that is not JSON. */
export class JsonSyntaxError extends Error {
  constructor(why: string, at: number) {
    super(`${why} at offset ${at}`);
    this.name = "JsonSyntaxError";
  }
}

/** Nested containers allowed in a canonical JSON value (decision 0002). */
export const MAX_DEPTH = 128;
/** Nesting allowed while parsing or converting a whole request body. */
export const BODY_MAX_DEPTH = 1000;

export function isObject(v: unknown): v is JsonObject {
  return v instanceof Map;
}

class Parser {
  i = 0;
  constructor(
    readonly s: string,
    readonly maxDepth: number,
  ) {}

  fail(why: string): never {
    throw new JsonSyntaxError(why, this.i);
  }

  ws(): void {
    const s = this.s;
    for (;;) {
      const c = s.charCodeAt(this.i);
      if (c === 0x20 || c === 0x0a || c === 0x0d || c === 0x09) this.i++;
      else return;
    }
  }

  value(depth: number): JsonValue {
    this.ws();
    const c = this.s[this.i];
    switch (c) {
      case "{":
        return this.object(depth + 1);
      case "[":
        return this.array(depth + 1);
      case '"':
        return this.string();
      case "t":
        return this.literal("true", true);
      case "f":
        return this.literal("false", false);
      case "n":
        return this.literal("null", null);
      default:
        if (c === "-" || (c !== undefined && c >= "0" && c <= "9")) return this.number();
        return this.fail("unexpected character");
    }
  }

  literal<T>(word: string, v: T): T {
    if (this.s.startsWith(word, this.i)) {
      this.i += word.length;
      return v;
    }
    return this.fail("invalid literal");
  }

  depthCheck(depth: number): void {
    if (depth > this.maxDepth) throw new NoIds("nested too deep");
  }

  object(depth: number): JsonObject {
    this.depthCheck(depth);
    this.i++; // {
    const m: JsonObject = new Map();
    this.ws();
    if (this.s[this.i] === "}") {
      this.i++;
      return m;
    }
    for (;;) {
      this.ws();
      if (this.s[this.i] !== '"') this.fail("expected a member name");
      const k = this.string();
      this.ws();
      if (this.s[this.i] !== ":") this.fail("expected ':'");
      this.i++;
      const v = this.value(depth);
      m.set(k, v);
      this.ws();
      const c = this.s[this.i];
      if (c === ",") {
        this.i++;
        continue;
      }
      if (c === "}") {
        this.i++;
        return m;
      }
      this.fail("expected ',' or '}'");
    }
  }

  array(depth: number): JsonValue[] {
    this.depthCheck(depth);
    this.i++; // [
    const a: JsonValue[] = [];
    this.ws();
    if (this.s[this.i] === "]") {
      this.i++;
      return a;
    }
    for (;;) {
      a.push(this.value(depth));
      this.ws();
      const c = this.s[this.i];
      if (c === ",") {
        this.i++;
        continue;
      }
      if (c === "]") {
        this.i++;
        return a;
      }
      this.fail("expected ',' or ']'");
    }
  }

  string(): string {
    const s = this.s;
    this.i++; // opening quote
    let out = "";
    let start = this.i;
    for (;;) {
      if (this.i >= s.length) this.fail("unterminated string");
      const c = s.charCodeAt(this.i);
      if (c === 0x22) {
        out += s.slice(start, this.i);
        this.i++;
        return wellFormed(out);
      }
      if (c < 0x20) this.fail("control character in string");
      if (c !== 0x5c) {
        this.i++;
        continue;
      }
      out += s.slice(start, this.i);
      const e = s[this.i + 1];
      this.i += 2;
      switch (e) {
        case '"':
          out += '"';
          break;
        case "\\":
          out += "\\";
          break;
        case "/":
          out += "/";
          break;
        case "b":
          out += "\b";
          break;
        case "f":
          out += "\f";
          break;
        case "n":
          out += "\n";
          break;
        case "r":
          out += "\r";
          break;
        case "t":
          out += "\t";
          break;
        case "u": {
          const h = s.slice(this.i, this.i + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(h)) this.fail("invalid \\u escape");
          out += String.fromCharCode(parseInt(h, 16));
          this.i += 4;
          break;
        }
        default:
          this.i -= 2;
          this.fail("invalid escape");
      }
      start = this.i;
    }
  }

  number(): number {
    const s = this.s;
    const start = this.i;
    if (s[this.i] === "-") this.i++;
    if (s[this.i] === "0") this.i++;
    else if (s[this.i]! >= "1" && s[this.i]! <= "9") {
      while (s[this.i]! >= "0" && s[this.i]! <= "9") this.i++;
    } else this.fail("invalid number");
    if (s[this.i] === ".") {
      this.i++;
      if (!(s[this.i]! >= "0" && s[this.i]! <= "9")) this.fail("invalid number");
      while (s[this.i]! >= "0" && s[this.i]! <= "9") this.i++;
    }
    if (s[this.i] === "e" || s[this.i] === "E") {
      this.i++;
      if (s[this.i] === "+" || s[this.i] === "-") this.i++;
      if (!(s[this.i]! >= "0" && s[this.i]! <= "9")) this.fail("invalid number");
      while (s[this.i]! >= "0" && s[this.i]! <= "9") this.i++;
    }
    // Number() rounds correctly to the nearest double; a value too large for a
    // double becomes an infinity, which the canonical text prints as null.
    return Number(s.slice(start, this.i));
  }
}

/**
 * Parse JSON text strictly (RFC 8259): no NaN or Infinity, no leading zeros, no
 * trailing text. Objects keep member order; a repeated member name keeps its
 * first position and takes the last value. Lone surrogates become U+FFFD.
 * Throws JsonSyntaxError on invalid text and NoIds when nested deeper than
 * `maxDepth` containers.
 */
export function parseJson(text: string | Uint8Array, maxDepth = BODY_MAX_DEPTH): JsonValue {
  let s: string;
  if (typeof text === "string") s = text;
  else {
    try {
      s = decodeUtf8(text);
    } catch {
      throw new JsonSyntaxError("invalid UTF-8", 0);
    }
  }
  const p = new Parser(s, maxDepth);
  const v = p.value(0);
  p.ws();
  if (p.i !== s.length) p.fail("unexpected text after the value");
  return v;
}

/**
 * Convert a plain JavaScript value (as from JSON.parse) into the JSON model.
 * Keys are taken in the object's own order, which for integer-like keys is
 * not the wire order: pass the raw body text to keep it.
 */
export function fromJS(v: unknown, depth = 0): JsonValue {
  if (v === null || typeof v === "boolean" || typeof v === "number") return v;
  if (typeof v === "string") return wellFormed(v);
  if (typeof v === "bigint") return Number(v);
  if (depth >= BODY_MAX_DEPTH) throw new NoIds("nested too deep");
  if (v instanceof Map) {
    const m: JsonObject = new Map();
    for (const [k, x] of v) {
      if (typeof k !== "string") throw new NoIds("map key is not a string");
      if (x === undefined || typeof x === "function" || typeof x === "symbol") continue;
      m.set(wellFormed(k), fromJS(x, depth + 1));
    }
    return m;
  }
  if (Array.isArray(v)) {
    return v.map((x) =>
      x === undefined || typeof x === "function" || typeof x === "symbol"
        ? null
        : fromJS(x, depth + 1),
    );
  }
  if (typeof v === "object") {
    const o = v as { toJSON?: () => unknown };
    if (typeof o.toJSON === "function") return fromJS(o.toJSON(), depth);
    const m: JsonObject = new Map();
    for (const k of Object.keys(v)) {
      const x = (v as Record<string, unknown>)[k];
      if (x === undefined || typeof x === "function" || typeof x === "symbol") continue;
      m.set(wellFormed(k), fromJS(x, depth + 1));
    }
    return m;
  }
  throw new NoIds(`value of type ${typeof v} is not JSON`);
}

function quote(s: string): string {
  let out = '"';
  let start = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0x20 && c !== 0x22 && c !== 0x5c) continue;
    out += s.slice(start, i);
    start = i + 1;
    switch (c) {
      case 0x22:
        out += '\\"';
        break;
      case 0x5c:
        out += "\\\\";
        break;
      case 0x08:
        out += "\\b";
        break;
      case 0x0c:
        out += "\\f";
        break;
      case 0x0a:
        out += "\\n";
        break;
      case 0x0d:
        out += "\\r";
        break;
      case 0x09:
        out += "\\t";
        break;
      default:
        out += "\\u00" + (c < 0x10 ? "0" : "") + c.toString(16);
    }
  }
  return out + s.slice(start) + '"';
}

function num(n: number): string {
  if (!Number.isFinite(n)) return "null";
  if (Object.is(n, -0)) return "0";
  return String(n);
}

function dumpInto(out: string[], v: JsonValue, sort: boolean, depth: number): void {
  if (v === null) out.push("null");
  else if (v === true) out.push("true");
  else if (v === false) out.push("false");
  else if (typeof v === "number") out.push(num(v));
  else if (typeof v === "string") out.push(quote(wellFormed(v)));
  else {
    if (depth + 1 > MAX_DEPTH) throw new NoIds("nested too deep");
    if (Array.isArray(v)) {
      out.push("[");
      for (let i = 0; i < v.length; i++) {
        if (i > 0) out.push(",");
        dumpInto(out, v[i]!, sort, depth + 1);
      }
      out.push("]");
    } else {
      let entries = [...v.entries()];
      if (sort) entries = entries.sort((a, b) => compareCodePoints(a[0], b[0]));
      out.push("{");
      for (let i = 0; i < entries.length; i++) {
        if (i > 0) out.push(",");
        out.push(quote(entries[i]![0]), ":");
        dumpInto(out, entries[i]![1], sort, depth + 1);
      }
      out.push("}");
    }
  }
}

/**
 * The canonical JSON text of `v` (decision 0002): no whitespace, members in
 * order (or sorted by code point with `sort`), minimal string escapes,
 * ECMAScript number printing. Throws NoIds past 128 nested containers.
 */
export function canonicalJson(v: JsonValue, sort = false): string {
  const out: string[] = [];
  dumpInto(out, v, sort, 0);
  return out.join("");
}
