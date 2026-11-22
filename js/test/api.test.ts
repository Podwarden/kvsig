import { describe, expect, it } from "vitest";
import {
  canonicalize,
  canonicalizeReply,
  ids,
  idsAllEpochs,
  Key,
  KeyRing,
  LOOSE_V2,
  looseText,
  messageId,
  scopeFrom,
  TEST_KEY,
  profileFingerprint,
  LOOSE_V1,
} from "../src/index.js";
import { toHex } from "../src/text.js";

const geography = {
  model: "m",
  messages: [
    { role: "system", content: "You answer geography questions." },
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
    { role: "user", content: "And Spain?" },
  ],
};

describe("quickstart", () => {
  it("gives the conversation id of the conv-base vector", () => {
    const body = {
      ...geography,
      tools: [
        {
          type: "function",
          function: {
            name: "ls",
            description: "List a directory",
            parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
          },
        },
      ],
    };
    const canon = canonicalize(body, "openai.chat");
    expect(canon).not.toBeNull();
    const i = ids(canon!, TEST_KEY);
    expect(i.conv).toBe("00fdd9bdfb7d14a82cb5d7d4d70ac60046");
    expect(i.nodes).toHaveLength(3);
    expect(i.head).toMatch(/^00[0-9a-f]{32}$/);
  });

  it("gives the same ids across dialects", () => {
    const chat = canonicalize(geography, "openai.chat")!;
    const anthropic = canonicalize(
      {
        model: "m",
        max_tokens: 64,
        system: "You answer geography questions.",
        messages: [
          { role: "user", content: "What is the capital of France?" },
          { role: "assistant", content: [{ type: "text", text: "Paris." }] },
          { role: "user", content: "And Spain?" },
        ],
      },
      "anthropic.messages",
    )!;
    const responses = canonicalize(
      {
        model: "m",
        instructions: "You answer geography questions.",
        input: [
          { role: "user", content: "What is the capital of France?" },
          { type: "message", role: "assistant", content: [{ type: "output_text", text: "Paris." }] },
          { role: "user", content: "And Spain?" },
        ],
      },
      "openai.responses",
    )!;
    const a = ids(chat, TEST_KEY);
    expect(ids(anthropic, TEST_KEY)).toEqual(a);
    expect(ids(responses, TEST_KEY)).toEqual(a);
  });
});

describe("input forms", () => {
  const raw = '{"model":"m","messages":[{"role":"user","content":"go"},{"role":"assistant","content":[{"type":"tool_use","id":"c1","name":"f","input":{"b":1,"10":2}}]}]}';

  it("keeps wire member order from raw text, string or bytes", () => {
    const a = canonicalize(raw, "anthropic.messages")!;
    const b = canonicalize(new TextEncoder().encode(raw), "anthropic.messages")!;
    expect((a.messages[1]!.parts[0] as { args: string }).args).toBe('{"b":1,"10":2}');
    expect(ids(a, TEST_KEY)).toEqual(ids(b, TEST_KEY));
  });

  it("follows JavaScript key order for a parsed object (integer-like keys first)", () => {
    const c = canonicalize(JSON.parse(raw), "anthropic.messages")!;
    expect((c.messages[1]!.parts[0] as { args: string }).args).toBe('{"10":2,"b":1}');
  });

  it("gives no ids, without throwing, for hostile or foreign input", () => {
    expect(canonicalize("{not json", "openai.chat")).toBeNull();
    expect(canonicalize([1, 2], "openai.chat")).toBeNull();
    expect(canonicalize({ messages: "x" }, "openai.chat")).toBeNull();
    expect(canonicalize({ model: "m", input: 5 }, "openai.responses")).toBeNull();
    expect(canonicalize("[".repeat(200000), "openai.chat")).toBeNull();
    const deep = { messages: [{ role: "user", content: "x" }, { role: "assistant", tool_calls: [{ function: { name: "f", arguments: "[".repeat(5000) + "]".repeat(5000) } }] }] };
    expect(canonicalize(deep, "openai.chat")).toBeNull();
    expect(canonicalize(geography, "openai.chat", { maxBytes: 10 })).toBeNull();
  });

  it("throws for an unknown dialect", () => {
    expect(() => canonicalize({}, "legacy.completions" as never)).toThrow(RangeError);
  });
});

describe("reply linkage", () => {
  it("links a Chat reply to the next request", () => {
    const reply = canonicalizeReply({ role: "assistant", content: "Paris." }, "openai.chat")!;
    const next = ids(canonicalize(geography, "openai.chat")!, TEST_KEY);
    expect(messageId(reply, TEST_KEY)).toBe(next.msgs[1]);
  });
});

describe("keys and scopes", () => {
  it("validates keys", () => {
    expect(() => new Key(256, new Uint8Array(32))).toThrow(RangeError);
    expect(() => new Key(1, new Uint8Array(31))).toThrow(RangeError);
    expect(() => Key.generate(0)).toThrow(RangeError);
    const hasWebCrypto = typeof (globalThis as { crypto?: unknown }).crypto === "object";
    const k = hasWebCrypto ? Key.generate(7) : new Key(7, new Uint8Array(32).fill(9));
    expect(k.epoch).toBe(7);
    expect(String(k)).not.toMatch(/[0-9a-f]{64}/);
    expect(JSON.stringify(k)).toBe('"Key(epoch=7, <secret>)"');
  });

  it("puts the epoch byte first and varies the MAC by key", () => {
    const c = canonicalize(geography, "openai.chat")!;
    const ring = new KeyRing(new Key(255, Uint8Array.from({ length: 32 }, (_, i) => 32 + i)), [TEST_KEY]);
    const [cur, old] = idsAllEpochs(c, ring);
    expect(cur!.head.slice(0, 2)).toBe("ff");
    expect(old!.head.slice(0, 2)).toBe("00");
    expect(cur!.head.slice(2)).not.toBe(old!.head.slice(2));
    expect(() => new KeyRing(TEST_KEY, [TEST_KEY])).toThrow(RangeError);
  });

  it("derives the empty scope from empty members", () => {
    expect(scopeFrom({}).length).toBe(0);
    expect(scopeFrom({ cacheSalt: "", tenant: new Uint8Array(0) }).length).toBe(0);
    expect(scopeFrom({ cacheSalt: "tenant-a" }).length).toBe(32);
  });
});

describe("loose profiles", () => {
  it("applies the loose/1 text rules", () => {
    expect(looseText("a <System-Reminder>x</SYSTEM-REMINDER> b\n2026-11-21\n  c　d ")).toBe("a b c d");
    expect(looseText("<system-reminder>only</system-reminder>")).toBe("");
  });

  it("has the reference fingerprints", () => {
    expect(toHex(profileFingerprint(LOOSE_V1))).toBe("7bbc9055edb37444");
    expect(toHex(profileFingerprint(LOOSE_V2))).toBe("e07d7a0a2fab64c1");
  });

  it("loose/2 reads developer as system: same conv for instructions and a developer item", () => {
    const text = "You are a coding agent.\n\nAnswer briefly.";
    const a = canonicalize({ model: "m", instructions: text, input: "hi" }, "openai.responses")!;
    const b = canonicalize({ model: "m", input: [{ type: "message", role: "developer", content: text }, { role: "user", content: "hi" }] }, "openai.responses")!;
    expect(ids(a, TEST_KEY).conv).not.toBe(ids(b, TEST_KEY).conv);
    const a2 = ids(a, TEST_KEY, { profile: LOOSE_V2 });
    const b2 = ids(b, TEST_KEY, { profile: LOOSE_V2 });
    expect(a2.conv).toBe(b2.conv);
    expect(a2.loose_sys).toBe(b2.loose_sys);
    expect(a2.sys).not.toBe(b2.sys);
    expect(a2.profile).toBe("loose/2");
    // Every loose id changes with the profile version.
    expect(a2.loose_msgs[0]).not.toBe(ids(a, TEST_KEY).loose_msgs[0]);
  });
});
