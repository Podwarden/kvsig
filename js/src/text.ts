// Unicode helpers: lone-surrogate repair, UTF-8, code point order.

const REPLACEMENT = "�";

/** `s` with every lone UTF-16 surrogate replaced by U+FFFD (decision 0001, rule 4). */
export function wellFormed(s: string): string {
  // Fast path: no surrogate code unit at all.
  let i = 0;
  const n = s.length;
  for (; i < n; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdfff) break;
  }
  if (i === n) return s;
  let out = s.slice(0, i);
  for (; i < n; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = i + 1 < n ? s.charCodeAt(i + 1) : 0;
      if (d >= 0xdc00 && d <= 0xdfff) {
        out += s[i]! + s[i + 1]!;
        i++;
      } else {
        out += REPLACEMENT;
      }
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      out += REPLACEMENT;
    } else {
      out += s[i]!;
    }
  }
  return out;
}

/** UTF-8 bytes of `s`; lone surrogates become U+FFFD. */
export function utf8(s: string): Uint8Array {
  const n = s.length;
  // ASCII fast path.
  let ascii = true;
  for (let i = 0; i < n; i++) {
    if (s.charCodeAt(i) > 0x7f) {
      ascii = false;
      break;
    }
  }
  if (ascii) {
    const out = new Uint8Array(n);
    for (let i = 0; i < n; i++) out[i] = s.charCodeAt(i);
    return out;
  }
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    let c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = i + 1 < n ? s.charCodeAt(i + 1) : 0;
      if (d >= 0xdc00 && d <= 0xdfff) {
        c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00);
        i++;
      } else {
        c = 0xfffd;
      }
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      c = 0xfffd;
    }
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else
      out.push(
        0xf0 | (c >> 18),
        0x80 | ((c >> 12) & 63),
        0x80 | ((c >> 6) & 63),
        0x80 | (c & 63),
      );
  }
  return Uint8Array.from(out);
}

/** Strict UTF-8 decoding; throws on invalid input. */
export function decodeUtf8(b: Uint8Array): string {
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(b);
}

/** Compare two well-formed strings by Unicode code point (not UTF-16 unit). */
export function compareCodePoints(a: string, b: string): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const x = a.charCodeAt(i);
    const y = b.charCodeAt(i);
    if (x === y) continue;
    // A surrogate (astral code point) sorts above every BMP code unit, which
    // UTF-16 order gets wrong only against U+E000..U+FFFF.
    const xs = x >= 0xd800 && x <= 0xdfff;
    const ys = y >= 0xd800 && y <= 0xdfff;
    if (xs !== ys) return xs ? 1 : -1;
    return x - y;
  }
  return a.length - b.length;
}

export function concatBytes(parts: readonly Uint8Array[]): Uint8Array {
  let len = 0;
  for (const p of parts) len += p.length;
  const out = new Uint8Array(len);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

const HEX = "0123456789abcdef";

export function toHex(b: Uint8Array): string {
  let s = "";
  for (let i = 0; i < b.length; i++) s += HEX[b[i]! >> 4]! + HEX[b[i]! & 15]!;
  return s;
}

export function fromHex(s: string): Uint8Array {
  if (s.length % 2 !== 0 || !/^[0-9a-fA-F]*$/.test(s)) throw new TypeError("invalid hex");
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.slice(2 * i, 2 * i + 2), 16);
  return out;
}

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const B64_INDEX = (() => {
  const t = new Int16Array(128).fill(-1);
  for (let i = 0; i < 64; i++) t[B64.charCodeAt(i)] = i;
  return t;
})();

/** Standard base64 with padding. */
export function toBase64(b: Uint8Array): string {
  let s = "";
  let i = 0;
  for (; i + 2 < b.length; i += 3) {
    const n = (b[i]! << 16) | (b[i + 1]! << 8) | b[i + 2]!;
    s += B64[n >> 18]! + B64[(n >> 12) & 63]! + B64[(n >> 6) & 63]! + B64[n & 63]!;
  }
  const rest = b.length - i;
  if (rest === 1) {
    const n = b[i]! << 16;
    s += B64[n >> 18]! + B64[(n >> 12) & 63]! + "==";
  } else if (rest === 2) {
    const n = (b[i]! << 16) | (b[i + 1]! << 8);
    s += B64[n >> 18]! + B64[(n >> 12) & 63]! + B64[(n >> 6) & 63]! + "=";
  }
  return s;
}

/**
 * Strict standard base64 (RFC 4648 alphabet, padding required), after removing
 * ASCII whitespace (decision 0003, "Base64"). Returns null when invalid.
 */
export function fromBase64Strict(input: string): Uint8Array | null {
  const s = input.replace(/[ \t\n\r\f\v]/g, "");
  if (s.length % 4 !== 0) return null;
  let pad = 0;
  if (s.endsWith("==")) pad = 2;
  else if (s.endsWith("=")) pad = 1;
  const body = s.length - pad;
  const out = new Uint8Array((s.length / 4) * 3 - pad);
  let o = 0;
  let acc = 0;
  let bits = 0;
  for (let i = 0; i < body; i++) {
    const c = s.charCodeAt(i);
    const v = c < 128 ? B64_INDEX[c]! : -1;
    if (v < 0) return null;
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[o++] = (acc >> bits) & 0xff;
    }
  }
  return o === out.length ? out : null;
}
