import { describe, expect, it } from "vitest";
import { canonicalJson, JsonSyntaxError, NoIds, parseJson } from "../src/json.js";
import { compareCodePoints } from "../src/text.js";

const canon = (s: string, sort = false) => canonicalJson(parseJson(s, 128), sort);

describe("parseJson", () => {
  it("keeps member order, integer-like keys included", () => {
    expect(canon('{"z":1,"10":2,"2":3}')).toBe('{"z":1,"10":2,"2":3}');
  });

  it("takes the last value of a repeated member, at the first position", () => {
    expect(canon('{"b":1,"a":2,"b":3}')).toBe('{"b":3,"a":2}');
  });

  it("repairs lone surrogates and merges keys that become equal", () => {
    expect(canon('{"\\ud800":1,"\\udbff":2,"z":3}')).toBe('{"\ufffd":2,"z":3}');
    expect(canon('"\\ud83d\\ude00"')).toBe('"\ud83d\ude00"');
    expect(canon('"\\udc00\\ud800"')).toBe('"\ufffd\ufffd"');
  });

  it("rejects what RFC 8259 rejects", () => {
    for (const bad of ["", "NaN", "Infinity", "01", "1.", ".5", "+1", "[1,]", '{"a":1,}', "'a'", '"\u0001"', '"\\x"', "1 2", "\ufeff1"]) {
      expect(() => parseJson(bad), bad).toThrow(JsonSyntaxError);
    }
  });

  it("caps depth at 128 nested containers", () => {
    expect(() => parseJson("[".repeat(128) + "]".repeat(128), 128)).not.toThrow();
    expect(() => parseJson("[".repeat(129) + "]".repeat(129), 128)).toThrow(NoIds);
    expect(() => parseJson("[".repeat(100000), 128)).toThrow(NoIds);
  });
});

describe("canonicalJson", () => {
  it("escapes only quote, backslash and control characters", () => {
    expect(canon('"q\\"b\\\\\\n\\t\\u0001\\u007f\\u2028\\/\\b\\f\\r\\u001F"')).toBe(
      '"q\\"b\\\\\\n\\t\\u0001\u007f\u2028/\\b\\f\\r\\u001f"',
    );
  });

  it("prints numbers as ECMAScript does, with -0 as 0 and overflow as null", () => {
    expect(canon("[1e20,1e21,1e-6,1e-7,100.0,-0,-0.0,1e999,9007199254740993,5e-324]")).toBe(
      "[100000000000000000000,1e+21,0.000001,1e-7,100,0,0,null,9007199254740992,5e-324]",
    );
  });

  it("sorts members by code point in the loose form", () => {
    expect(canon('{"\uffff":1,"\ud83d\ude00":2,"b":3,"B":4}', true)).toBe('{"B":4,"b":3,"\uffff":1,"\ud83d\ude00":2}');
  });

  it("compares by code point, not UTF-16 unit", () => {
    expect(compareCodePoints("\uffff", "\ud83d\ude00")).toBeLessThan(0);
    expect(compareCodePoints("a", "ab")).toBeLessThan(0);
  });
});
