import { createHash, createHmac, randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import { hmacSha256, sha256, Sha256 } from "../src/sha256.js";
import { toHex, utf8 } from "../src/text.js";

describe("sha256", () => {
  it("matches the FIPS 180-4 examples", () => {
    expect(toHex(sha256(utf8("")))).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(toHex(sha256(utf8("abc")))).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(toHex(sha256(utf8("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")))).toBe(
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    );
  });

  it("matches node:crypto on random inputs of every length up to 300", () => {
    for (let n = 0; n <= 300; n++) {
      const b = new Uint8Array(randomBytes(n));
      expect(toHex(sha256(b))).toBe(createHash("sha256").update(b).digest("hex"));
    }
  });

  it("hashes incrementally the same as in one call", () => {
    const b = new Uint8Array(randomBytes(1000));
    const h = new Sha256();
    for (let i = 0; i < b.length; i += 37) h.update(b.subarray(i, i + 37));
    expect(toHex(h.digest())).toBe(toHex(sha256(b)));
  });
});

describe("hmacSha256", () => {
  it("matches RFC 4231 test cases 1, 2 and 6", () => {
    expect(toHex(hmacSha256(new Uint8Array(20).fill(0x0b), utf8("Hi There")))).toBe(
      "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
    );
    expect(toHex(hmacSha256(utf8("Jefe"), utf8("what do ya want for nothing?")))).toBe(
      "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
    );
    expect(
      toHex(hmacSha256(new Uint8Array(131).fill(0xaa), utf8("Test Using Larger Than Block-Size Key - Hash Key First"))),
    ).toBe("60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
  });

  it("matches node:crypto on random keys and messages", () => {
    for (let i = 0; i < 200; i++) {
      const key = new Uint8Array(randomBytes(i % 100));
      const msg = new Uint8Array(randomBytes(i * 3));
      const split = Math.floor(msg.length / 2);
      expect(toHex(hmacSha256(key, msg.subarray(0, split), msg.subarray(split)))).toBe(
        createHmac("sha256", key).update(msg).digest("hex"),
      );
    }
  });
});
