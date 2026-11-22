// Every test vector of vectors/v1, in process (the conformance runner checks
// the same through conformance/adapters/ts_adapter.mjs).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  canonicalBytes,
  canonicalize,
  canonicalizeReply,
  encode,
  ids,
  Key,
  loose,
  looseMessage,
  LOOSE_V1,
  messageId,
  parseJson,
  scopeFrom,
  type Dialect,
} from "../src/index.js";
import { toBase64 } from "../src/text.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "vectors", "v1");
// Parsed with the order-preserving parser, as a server holding the raw body would.
const man = parseJson(readFileSync(path.join(root, "manifest.json"), "utf8")) as Map<string, any>;
const keys = (man.get("keys") as Map<string, any>[]).map((k) => ({
  epoch: k.get("epoch") as number,
  key: new Key(k.get("epoch"), Uint8Array.from(Buffer.from(k.get("key_b64"), "base64"))),
}));
const files = (man.get("files") as Map<string, any>[]).map((f) => f.get("path") as string);

const b64 = (b: Uint8Array) => toBase64(b);
const unb64 = (s: string) => Uint8Array.from(Buffer.from(s, "base64"));

describe("vectors/v1", () => {
  it("has 232 vectors", () => expect(files.length).toBe(232));

  for (const file of files) {
    it(file, () => {
      const v = parseJson(readFileSync(path.join(root, file), "utf8")) as Map<string, any>;
      const dialect = v.get("dialect") as Dialect;
      const raw = v.get("input_raw_b64");
      const body = raw ? unb64(raw) : v.get("input");
      const mb = v.get("options")?.get("max_bytes");
      const exp = v.get("expect") as Map<string, any>;
      const c = canonicalize(body, dialect, mb ? { maxBytes: mb } : {});
      if (exp.get("none")) {
        expect(c).toBeNull();
        return;
      }
      expect(c).not.toBeNull();
      expect(b64(canonicalBytes(c!))).toBe(exp.get("canonical_bytes_b64"));
      expect(b64(canonicalBytes(loose(c!)))).toBe(exp.get("loose_bytes_b64"));
      expect(c!.stateful).toBe(exp.get("stateful"));

      const sc = v.get("scope") as Map<string, any> | undefined;
      let scope = new Uint8Array(0);
      if (sc) {
        const tenant = sc.get("tenant_b64");
        scope = scopeFrom({ cacheSalt: sc.get("cache_salt"), tenant: tenant == null ? null : unb64(tenant) });
        expect(b64(scope)).toBe(sc.get("scope_b64"));
      }
      for (const { epoch, key } of keys) {
        const want = exp.get("keys").get(String(epoch)) as Map<string, any>;
        const got = ids(c!, key, { scope });
        for (const [f, w] of want) expect((got as any)[f], `${f} (epoch ${epoch})`).toEqual(w);
      }

      const rp = v.get("reply") as Map<string, any> | undefined;
      if (rp) {
        let resp = rp.get("response");
        if (dialect === "openai.chat") resp = resp.get("choices")[0].get("message");
        const m = canonicalizeReply(resp, dialect);
        expect(m).not.toBeNull();
        expect(b64(encode(m))).toBe(rp.get("canonical_bytes_b64"));
        const idx = rp.get("matches_msg_index") as number;
        for (const { epoch, key } of keys) {
          const want = rp.get("keys").get(String(epoch));
          expect(messageId(m!, key, { scope })).toBe(want.get("msg"));
          expect(messageId(m!, key, { scope, profile: LOOSE_V1 })).toBe(want.get("loose_msg"));
          // The loose id of the reply always links to the next request.
          const next = ids(c!, key, { scope });
          expect(messageId(m!, key, { scope, profile: LOOSE_V1 })).toBe(next.loose_msgs[idx]);
          if (rp.get("exact")) expect(messageId(m!, key, { scope })).toBe(next.msgs[idx]);
        }
        expect(looseMessage(m!)).toBeDefined();
      }
    });
  }
});
