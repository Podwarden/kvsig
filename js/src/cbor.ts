// The restricted deterministic CBOR profile of decision 0001: unsigned and
// negative integers, byte strings, text strings, arrays, maps with text keys
// sorted by the bytes of their encoding, false and true. Nothing else.

import { utf8 } from "./text.js";

/** A value the canonical encoder accepts. */
export type CborValue =
  | number
  | boolean
  | string
  | Uint8Array
  | readonly CborValue[]
  | { readonly [key: string]: CborValue };

class Writer {
  private buf = new Uint8Array(256);
  len = 0;

  private ensure(n: number): void {
    if (this.len + n <= this.buf.length) return;
    let cap = this.buf.length * 2;
    while (cap < this.len + n) cap *= 2;
    const b = new Uint8Array(cap);
    b.set(this.buf.subarray(0, this.len));
    this.buf = b;
  }

  byte(b: number): void {
    this.ensure(1);
    this.buf[this.len++] = b;
  }

  bytes(b: Uint8Array): void {
    this.ensure(b.length);
    this.buf.set(b, this.len);
    this.len += b.length;
  }

  head(major: number, n: number): void {
    const m = major << 5;
    if (n < 24) this.byte(m | n);
    else if (n < 0x100) {
      this.byte(m | 24);
      this.byte(n);
    } else if (n < 0x10000) {
      this.byte(m | 25);
      this.byte(n >>> 8);
      this.byte(n & 0xff);
    } else if (n < 0x100000000) {
      this.byte(m | 26);
      this.byte(n >>> 24);
      this.byte((n >>> 16) & 0xff);
      this.byte((n >>> 8) & 0xff);
      this.byte(n & 0xff);
    } else {
      this.byte(m | 27);
      const hi = Math.floor(n / 0x100000000);
      const lo = n >>> 0;
      for (const v of [hi, lo]) {
        this.byte(v >>> 24);
        this.byte((v >>> 16) & 0xff);
        this.byte((v >>> 8) & 0xff);
        this.byte(v & 0xff);
      }
    }
  }

  result(): Uint8Array {
    return this.buf.slice(0, this.len);
  }
}

function keyBytes(k: string): Uint8Array {
  const w = new Writer();
  const b = utf8(k);
  w.head(3, b.length);
  w.bytes(b);
  return w.result();
}

function compareBytes(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return a[i]! - b[i]!;
  return a.length - b.length;
}

const KEY_CACHE = new Map<string, Uint8Array>();

function cachedKey(k: string): Uint8Array {
  let b = KEY_CACHE.get(k);
  if (b === undefined) {
    b = keyBytes(k);
    if (KEY_CACHE.size < 1024) KEY_CACHE.set(k, b);
  }
  return b;
}

function write(w: Writer, v: CborValue): void {
  if (typeof v === "number") {
    if (!Number.isSafeInteger(v)) throw new TypeError("cbor: only safe integers are allowed");
    if (v >= 0) w.head(0, v);
    else w.head(1, -1 - v);
  } else if (typeof v === "string") {
    const b = utf8(v);
    w.head(3, b.length);
    w.bytes(b);
  } else if (typeof v === "boolean") {
    w.byte(v ? 0xf5 : 0xf4);
  } else if (v instanceof Uint8Array) {
    w.head(2, v.length);
    w.bytes(v);
  } else if (Array.isArray(v)) {
    w.head(4, v.length);
    for (const x of v as readonly CborValue[]) write(w, x);
  } else if (v !== null && typeof v === "object") {
    const entries: [Uint8Array, CborValue][] = [];
    for (const k of Object.keys(v)) {
      const x = (v as { [key: string]: CborValue | undefined })[k];
      if (x === undefined) continue;
      entries.push([cachedKey(k), x]);
    }
    entries.sort((a, b) => compareBytes(a[0], b[0]));
    w.head(5, entries.length);
    for (let i = 0; i < entries.length; i++) {
      const [kb, x] = entries[i]!;
      if (i > 0 && compareBytes(entries[i - 1]![0], kb) === 0) {
        throw new TypeError("cbor: duplicate map key");
      }
      w.bytes(kb);
      write(w, x);
    }
  } else {
    throw new TypeError(`cbor: value of type ${v === null ? "null" : typeof v} is not allowed`);
  }
}

/** The canonical CBOR encoding of `v` (decision 0001). */
export function encode(v: CborValue): Uint8Array {
  const w = new Writer();
  write(w, v);
  return w.result();
}
