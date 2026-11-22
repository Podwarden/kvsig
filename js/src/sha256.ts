// SHA-256 (FIPS 180-4) and HMAC-SHA-256 (RFC 2104) from @noble/hashes, an
// audited, dependency-free, synchronous implementation that runs in every
// JavaScript runtime. Checked against node:crypto and the NIST / RFC 4231
// test vectors in test/sha256.test.ts.

import { hmac } from "@noble/hashes/hmac";
import { sha256 as nobleSha256 } from "@noble/hashes/sha2";

/** An incremental SHA-256 hash. */
export class Sha256 {
  private readonly h = nobleSha256.create();

  update(data: Uint8Array): this {
    this.h.update(data);
    return this;
  }

  digest(): Uint8Array {
    return this.h.digest();
  }
}

/** SHA-256 of `data`. */
export function sha256(data: Uint8Array): Uint8Array {
  return nobleSha256(data);
}

/** HMAC-SHA-256 of the concatenation of `parts` under `key`. */
export function hmacSha256(key: Uint8Array, ...parts: Uint8Array[]): Uint8Array {
  const m = hmac.create(nobleSha256, key);
  for (const p of parts) m.update(p);
  return m.digest();
}
