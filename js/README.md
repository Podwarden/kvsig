# kvsig for JavaScript and TypeScript

Keyed, content-derived ids for LLM chat conversations. This is an independent
TypeScript implementation of the
[kvsig specification](https://github.com/Podwarden/kvsig/blob/main/SPEC.md)
(`kvsig/1`, draft 0.1), written from the spec, its decisions and the test
vectors. It passes all 232 vectors at conformance Level 3, byte for byte with
the Python reference.

A gateway or router that sees a stream of stateless chat requests can use it to
tell which conversation each request belongs to, which prefix it shares with an
earlier request, and whether the system prompt or the tools changed, the same
way in OpenAI Chat Completions, OpenAI Responses and Anthropic Messages.

- Pure TypeScript, no native code. One runtime dependency,
  [`@noble/hashes`](https://github.com/paulmillr/noble-hashes) (audited,
  itself dependency-free), for SHA-256 and HMAC.
- ESM and CommonJS builds with type declarations.
- Node 18 or later, browsers, Deno, Bun and edge runtimes. Ids are computed
  synchronously (no async Web Crypto round trip).

## Install

```bash
npm install @kvsig/core
```

## Quickstart

```ts
import { Key, canonicalize, ids } from "@kvsig/core";

const key = Key.generate(1); // one per deployment; keep it secret and keep it
const body = {
  model: "m",
  messages: [
    { role: "system", content: "You answer geography questions." },
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
    { role: "user", content: "And Spain?" },
  ],
};

const canon = canonicalize(body, "openai.chat"); // null means "this request gets no ids"
if (canon !== null) {
  const i = ids(canon, key);
  i.conv; // conversation id: stable across turns, reminders, dates and tool changes
  i.nodes.at(-1); // id of the whole prefix, like a git commit
  i.sys, i.tools; // the two halves of the head: which one changed?
}
```

The same conversation sent as `"anthropic.messages"` or `"openai.responses"`
gives the same ids. Hostile or oversized input never throws; it gives `null`.
CommonJS works too: `const { Key, canonicalize, ids } = require("@kvsig/core")`.

**Pass the raw body when you have it.** `canonicalize` takes a parsed value or
the raw JSON text (a string or a `Uint8Array`). JavaScript objects move
integer-like keys to the front (`{"b":1,"10":2}` becomes `{"10":2,"b":1}`), and
the exact form keeps the wire order of tool arguments and schemas. A gateway
that forwards the body untouched should hand kvsig the same bytes:

```ts
const canon = canonicalize(rawBodyBytes, "anthropic.messages");
```

The library parses it with its own strict, order-preserving JSON parser
(duplicate members: the last value wins, at the first position; lone
surrogates become U+FFFD), as decision 0002 requires. It is strict RFC 8259:
a body holding `NaN` or `Infinity` gets no ids.

**Node 18.** `Key.generate` needs Web Crypto on `globalThis`, which Node 18 does
not expose by default. Use `new Key(epoch, crypto.randomBytes(32))` from
`node:crypto` there.

To check your install against the published test vectors, use the published
test key (epoch 0) on the vector
[`openai.chat/conv-base`](https://github.com/Podwarden/kvsig/blob/main/vectors/v1/openai.chat/conv-base.json):

```ts
import { readFileSync } from "node:fs";
import { TEST_KEY, canonicalize, ids } from "@kvsig/core";

const raw = readFileSync("vectors/v1/openai.chat/conv-base.json", "utf8");
const v = JSON.parse(raw);
const i = ids(canonicalize(v.input, v.dialect)!, TEST_KEY);
console.assert(i.conv === v.expect.keys["0"].conv); // "00fdd9bdfb7d14a82cb5d7d4d70ac60046"
```

## API

| Function | Does |
|---|---|
| `canonicalize(body, dialect, { maxBytes })` | The canonical form of a request, or `null` (no ids). |
| `ids(canon, key, { scope, profile })` | Every id: `head`, `sys`, `tools`, `msgs`, `nodes`, their loose forms, and `conv`. |
| `canonicalizeReply(message, dialect)` | A response's assistant message alone, for reply linkage. |
| `messageId(message, key, { scope, profile })` | One message id: exact, or loose with `profile`. |
| `scopeFrom({ cacheSalt, tenant })` | Scope bytes that separate tenants. |
| `Key`, `KeyRing`, `idsAllEpochs`, `TEST_KEY` | Deployment keys, rotation, the published test key. |
| `loose`, `looseMessage`, `looseText`, `LOOSE_V1`, `LOOSE_V2` | The loose profiles. |
| `canonicalBytes`, `encode` | The canonical CBOR bytes, as the vectors give them. |

[Reading the ids](https://github.com/Podwarden/kvsig/blob/main/docs/reading-the-ids.md)
says what each id identifies and how to tell what changed between two requests.

## What 0.1 guarantees

- For the spec label `kvsig/1` and the loose profile `loose/1` (the default),
  canonical bytes and ids are pinned by the
  [`vectors/v1`](https://github.com/Podwarden/kvsig/tree/main/vectors) test
  vectors, and equal to the Python reference's. No later release changes them;
  a change ships under a new label or profile version instead.
- `LOOSE_V2` (`loose/2`, decision 0005) is included but **experimental**: it is
  not covered by the vectors yet and its ids may change until its decision is
  accepted. Today it gives the same ids as the Python `LOOSE_V2`.
- The package version follows the spec draft revision (0.1.0 for draft 0.1)
  and SemVer with the 0.x rule: a minor release may change the API, a patch
  release does not. The full policy is in the
  [specification](https://github.com/Podwarden/kvsig/blob/main/SPEC.md#versioning-and-compatibility).

## Conformance

```
level           openai.chat    openai.responses  anthropic.messages    total
L1                    88/88               38/38               36/36  162/162
L2                    32/32               16/16                 7/7    55/55
L3                      4/4                 6/6                 5/5    15/15
Level 3 conformant for: openai.chat, openai.responses, anthropic.messages (vectors kvsig/1 revision 0.1)
```

## Development

From `js/` in a checkout:

```bash
npm ci
npm run typecheck && npm test && npm run build
npm run conformance   # python3 ../conformance/run.py -- node ../conformance/adapters/ts_adapter.mjs
```

## Licence

Apache-2.0. The specification text is licensed separately under CC BY 4.0; see
[NOTICE](https://github.com/Podwarden/kvsig/blob/main/NOTICE).
