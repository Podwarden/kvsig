#!/usr/bin/env node
// Conformance adapter for the TypeScript implementation (js/, npm @kvsig/core).
//
// Speaks the line protocol described in conformance/README.md: one JSON
// request per line on stdin, one JSON response per line on stdout.
//
//   (cd js && npm ci && npm run build)
//   python conformance/run.py -- node conformance/adapters/ts_adapter.mjs
//
// KVSIG_JS_DIST may point at another build (for example an installed package's
// dist/index.js) to test that instead of the checkout.

import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = process.env.KVSIG_JS_DIST ?? path.join(here, "..", "..", "js", "dist", "index.js");
const kvsig = await import(pathToFileURL(path.resolve(dist)).href);
const {
  canonicalize,
  canonicalizeReply,
  canonicalBytes,
  encode,
  ids,
  Key,
  loose,
  looseMessage,
  messageId,
  parseJson,
  scopeFrom,
  LOOSE_V1,
  SPEC_LABEL,
  SUPPORTED,
  VERSION,
} = kvsig;

const b64 = (b) => Buffer.from(b).toString("base64");
const unb64 = (s) => new Uint8Array(Buffer.from(s ?? "", "base64"));

// The request line is parsed with the library's order-preserving parser, so
// `input` keeps the member order the runner sent (JSON.parse would move
// integer-like keys first).
function body(req) {
  const raw = req.get("input_raw_b64");
  if (raw !== undefined && raw !== null) return unb64(raw);
  const v = req.get("input");
  return v === undefined ? null : v;
}

function options(req) {
  const mb = req.get("max_bytes");
  return mb === undefined || mb === null ? {} : { maxBytes: mb };
}

const key = (req) => new Key(req.get("epoch"), unb64(req.get("key_b64")));
const scope = (req) => unb64(req.get("scope_b64") ?? "");
const onError = (e) => {
  throw e;
};

function handle(req) {
  const op = req.get("op");
  const dialect = req.get("dialect");
  if (op === "info") {
    return { ok: true, name: "kvsig-ts", version: VERSION, spec: SPEC_LABEL, levels: 3, dialects: [...SUPPORTED] };
  }
  if (op === "scope") {
    const tenant = req.get("tenant_b64");
    const s = scopeFrom({
      cacheSalt: req.get("cache_salt"),
      tenant: tenant === undefined || tenant === null ? null : unb64(tenant),
    });
    return { ok: true, scope_b64: b64(s) };
  }
  if (op === "canonicalize") {
    const c = canonicalize(body(req), dialect, { ...options(req), onError });
    if (c === null) return { ok: true, none: true };
    return {
      ok: true,
      none: false,
      stateful: c.stateful,
      canonical_bytes_b64: b64(canonicalBytes(c)),
      loose_bytes_b64: b64(canonicalBytes(loose(c, LOOSE_V1))),
    };
  }
  if (op === "ids") {
    const c = canonicalize(body(req), dialect, { ...options(req), onError });
    if (c === null) return { ok: true, none: true };
    const i = ids(c, key(req), { scope: scope(req) });
    const out = {};
    for (const f of ["head", "sys", "tools", "msgs", "nodes", "loose_head", "loose_sys", "loose_tools", "loose_msgs", "loose_nodes", "conv"]) {
      out[f] = i[f];
    }
    return { ok: true, none: false, ids: out };
  }
  if (op === "reply_id") {
    let resp = body(req);
    if (dialect === "openai.chat") {
      // the reply is the first choice's message
      const choices = resp instanceof Map ? resp.get("choices") : undefined;
      const first = Array.isArray(choices) ? choices[0] : undefined;
      resp = first instanceof Map ? first.get("message") : undefined;
      if (resp === undefined) return { ok: true, none: true };
    }
    const m = canonicalizeReply(resp, dialect, { ...options(req), onError });
    if (m === null) return { ok: true, none: true };
    const k = key(req);
    const s = scope(req);
    return {
      ok: true,
      none: false,
      canonical_bytes_b64: b64(encode(m)),
      loose_bytes_b64: b64(encode(looseMessage(m, LOOSE_V1))),
      msg: messageId(m, k, { scope: s }),
      loose_msg: messageId(m, k, { scope: s, profile: LOOSE_V1 }),
    };
  }
  return { ok: false, error: `unknown op ${JSON.stringify(op)}` };
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  let out;
  try {
    out = handle(parseJson(line));
  } catch (e) {
    out = { ok: false, error: `${e?.name ?? "Error"}: ${e?.message ?? e}` };
  }
  process.stdout.write(JSON.stringify(out) + "\n");
}
