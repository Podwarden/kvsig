// SHA-256 (FIPS 180-4) and HMAC-SHA-256 (RFC 2104), synchronous and
// dependency-free so that ids can be computed in any JavaScript runtime
// without an async Web Crypto round trip. Checked against node:crypto and the
// NIST / RFC 4231 test vectors in test/sha256.test.ts.

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

const IV = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
];

/** An incremental SHA-256 hash. */
export class Sha256 {
  private readonly h = new Uint32Array(IV);
  private readonly w = new Uint32Array(64);
  private readonly buf = new Uint8Array(64);
  private bufLen = 0;
  private total = 0;
  private done = false;

  update(data: Uint8Array): this {
    if (this.done) throw new Error("sha256: update after digest");
    let i = 0;
    const n = data.length;
    this.total += n;
    if (this.bufLen > 0) {
      const take = Math.min(64 - this.bufLen, n);
      this.buf.set(data.subarray(0, take), this.bufLen);
      this.bufLen += take;
      i = take;
      if (this.bufLen < 64) return this;
      this.block(this.buf, 0);
      this.bufLen = 0;
    }
    for (; i + 64 <= n; i += 64) this.block(data, i);
    if (i < n) {
      this.buf.set(data.subarray(i), 0);
      this.bufLen = n - i;
    }
    return this;
  }

  digest(): Uint8Array {
    if (this.done) throw new Error("sha256: digest called twice");
    this.done = true;
    const bitsHi = Math.floor(this.total / 0x20000000);
    const bitsLo = (this.total << 3) >>> 0;
    const b = this.buf;
    let len = this.bufLen;
    b[len++] = 0x80;
    if (len > 56) {
      b.fill(0, len);
      this.block(b, 0);
      len = 0;
    }
    b.fill(0, len, 56);
    b[56] = bitsHi >>> 24;
    b[57] = bitsHi >>> 16;
    b[58] = bitsHi >>> 8;
    b[59] = bitsHi;
    b[60] = bitsLo >>> 24;
    b[61] = bitsLo >>> 16;
    b[62] = bitsLo >>> 8;
    b[63] = bitsLo;
    this.block(b, 0);
    const out = new Uint8Array(32);
    for (let j = 0; j < 8; j++) {
      const v = this.h[j]!;
      out[4 * j] = v >>> 24;
      out[4 * j + 1] = v >>> 16;
      out[4 * j + 2] = v >>> 8;
      out[4 * j + 3] = v;
    }
    return out;
  }

  private block(d: Uint8Array, off: number): void {
    const w = this.w;
    for (let t = 0; t < 16; t++) {
      const p = off + 4 * t;
      w[t] = (d[p]! << 24) | (d[p + 1]! << 16) | (d[p + 2]! << 8) | d[p + 3]!;
    }
    for (let t = 16; t < 64; t++) {
      const a = w[t - 15]!;
      const b = w[t - 2]!;
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
      w[t] = (w[t - 16]! + s0 + w[t - 7]! + s1) | 0;
    }
    const h = this.h;
    let a = h[0]!;
    let b = h[1]!;
    let c = h[2]!;
    let dd = h[3]!;
    let e = h[4]!;
    let f = h[5]!;
    let g = h[6]!;
    let hh = h[7]!;
    for (let t = 0; t < 64; t++) {
      const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[t]! + w[t]!) | 0;
      const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) | 0;
      hh = g;
      g = f;
      f = e;
      e = (dd + t1) | 0;
      dd = c;
      c = b;
      b = a;
      a = (t1 + t2) | 0;
    }
    h[0] = (h[0]! + a) | 0;
    h[1] = (h[1]! + b) | 0;
    h[2] = (h[2]! + c) | 0;
    h[3] = (h[3]! + dd) | 0;
    h[4] = (h[4]! + e) | 0;
    h[5] = (h[5]! + f) | 0;
    h[6] = (h[6]! + g) | 0;
    h[7] = (h[7]! + hh) | 0;
  }
}

/** SHA-256 of `data`. */
export function sha256(data: Uint8Array): Uint8Array {
  return new Sha256().update(data).digest();
}

/** HMAC-SHA-256 of the concatenation of `parts` under `key`. */
export function hmacSha256(key: Uint8Array, ...parts: Uint8Array[]): Uint8Array {
  let k = key.length > 64 ? sha256(key) : key;
  const block = new Uint8Array(64);
  block.set(k);
  k = block;
  const ipad = new Uint8Array(64);
  const opad = new Uint8Array(64);
  for (let i = 0; i < 64; i++) {
    ipad[i] = k[i]! ^ 0x36;
    opad[i] = k[i]! ^ 0x5c;
  }
  const inner = new Sha256().update(ipad);
  for (const p of parts) inner.update(p);
  return new Sha256().update(opad).update(inner.digest()).digest();
}
