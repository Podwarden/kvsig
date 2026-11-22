import { describe, expect, it } from "vitest";
import { encode } from "../src/cbor.js";
import { toHex } from "../src/text.js";

const hex = (v: Parameters<typeof encode>[0]) => toHex(encode(v));

describe("canonical CBOR", () => {
  it("uses the shortest form for integers and lengths (RFC 8949 appendix A)", () => {
    expect(hex(0)).toBe("00");
    expect(hex(23)).toBe("17");
    expect(hex(24)).toBe("1818");
    expect(hex(255)).toBe("18ff");
    expect(hex(256)).toBe("190100");
    expect(hex(65536)).toBe("1a00010000");
    expect(hex(4294967296)).toBe("1b0000000100000000");
    expect(hex(-1)).toBe("20");
    expect(hex(-1000)).toBe("3903e7");
    expect(hex("")).toBe("60");
    expect(hex("\u00fc")).toBe("62c3bc");
    expect(hex("\ud800\udd51")).toBe("64f0908591");
    expect(hex(new Uint8Array([1, 2, 3, 4]))).toBe("4401020304");
    expect(hex([1, [2, 3]])).toBe("8201820203");
    expect(hex(false)).toBe("f4");
    expect(hex(true)).toBe("f5");
  });

  it("sorts map keys by the bytes of their encoding (shorter first)", () => {
    expect(hex({ b: 1, aa: 2, a: 3 })).toBe("a3616103616201626161" + "02");
  });

  it("encodes a lone surrogate as U+FFFD", () => {
    expect(hex("\ud800")).toBe("63efbfbd");
  });

  it("rejects values outside the profile", () => {
    expect(() => encode(1.5)).toThrow();
    expect(() => encode(null as never)).toThrow();
    expect(() => encode(2 ** 60)).toThrow();
  });
});
