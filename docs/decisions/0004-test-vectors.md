# 0004. Test vectors: format, keys and the first set

Status: **proposed**, open for comment. The vectors are drafts until spec v1 is
frozen. After the freeze they are immutable (see `vectors/README.md`).

## Question

What does a test vector look like, so that an implementation in any language can
be checked against the same files? The plan this adapts called for JSON vectors
that carry the canonical form. Decision 0001 chose CBOR, so each vector must
carry the normative bytes and a form people can read.

## Decision

### Files

- `vectors/v1/<dialect>/<case>.json`, one vector per file, and
  `vectors/v1/manifest.json`.
- The manifest holds the spec label (`kvsig/1`), the format number, the loose
  profile (`loose/1`), the test keys, and every vector file with its SHA-256,
  level, dialect and category.
- `vectors/tools/generate.py` builds every file from the case definitions in
  `vectors/tools/cases*.py` with the reference implementation. A CI check
  regenerates the files and fails on any difference, so a vector cannot change
  without the manifest.
- Every input is synthetic and hand-written. No captured traffic is used.

### One vector

| Field | Meaning |
|---|---|
| `id`, `spec`, `dialect`, `category`, `description` | Name and purpose. |
| `level` | The lowest conformance level that must pass this vector (1, 2 or 3). |
| `input` | The request body as parsed JSON. |
| `input_raw_b64` | The exact wire bytes, when the case needs them (lone surrogates, duplicate keys, number forms, deep nesting). Then `input` is `null`. |
| `options.max_bytes` | A size cap for this request (the default is 2 MiB). |
| `scope` | `cache_salt`, `tenant_b64` and the derived `scope_b64`. Absent means the empty scope. |
| `expect.none` | True when the request must get no ids (size cap, depth cap, not a chat body). Nothing else is expected then. |
| `expect.stateful` | True for Responses requests that continue server-side history: no prefix or conversation ids. |
| `expect.canonical`, `expect.canonical_bytes_b64` | The exact canonical form. The bytes are normative. The JSON form is for humans, and byte strings appear as `{"$hex": "..."}`. |
| `expect.loose`, `expect.loose_bytes_b64` | The same for the `loose/1` form. |
| `expect.keys.<epoch>` | The ids under each test key: `head`, `sys`, `tools`, `msgs`, `nodes`, and the loose ones plus `conv`. |
| `equivalent_to` | Vectors in other dialects with the same canonical form, so the same ids. |
| `relations` | Claims between vectors: `{"field", "other", "same"}`. For example "same conversation id, different tools". |
| `reply` | Level 3 only. See below. |

The canonical bytes are the CBOR (0001) of `{"head": [...], "tools": [...],
"messages": [...]}`.

### Levels

A vector's `level` is the lowest level that runs it. A Level 2 implementation
runs the Level 1 and Level 2 vectors, and for all of them it also checks the
loose ids and the conversation id. A Level 1 implementation checks only the
exact form and the exact ids. Level 3 vectors are reply-linkage vectors.

### Test keys and rotation

- Key `test-0`: epoch 0, the 32 bytes `0x00` to `0x1f`. This is the published
  test key of the spec.
- Key `test-255`: epoch 255, the 32 bytes `0x20` to `0x3f`. A rotation test needs a
  second key with a different epoch, and epoch 0 is taken. Epoch 255 is the last
  real epoch, so it cannot collide with the low epochs that deployments will
  hand out first. A key ring `{current: 255, accepted: [0]}` models a rotation
  from the test key.
- Every vector carries ids under both keys. The two sets differ in the epoch
  byte and in the MAC bytes, so an implementation that ignores the epoch or
  reuses a MAC fails. The vectors do not test key-ring lookup itself, because
  that is API surface and not part of the id function.
- Both keys are public. They must never protect real data.

### Reply linkage (Level 3)

A reply vector is the **next request**, which carries the assistant message
back, plus the **response** that produced it. `reply.matches_msg_index` names
the body message that the reply must equal. The loose message id of the reply
must always equal the loose id of that message. The exact id must equal it
when `reply.exact` is true. Reasoning-model vectors with `exact: false` show a
client that does not send reasoning back: only the loose id links.

The response is given whole, as the provider sends it. For `openai.chat` the
reply is `choices[0].message`. Streamed responses are not covered by this
first set: the vectors carry the assembled response.

### Categories in the first set

Per-dialect basics; every part type; tool-call references (out of order,
missing call, repeated ids, result before the call); media (base64, wrapped
base64, percent-encoded, bad base64, URL, file id, documents); Unicode (NBSP,
U+001C to U+001F, astral characters, normal forms, lone surrogates as raw wire
bytes); numbers in arguments; duplicate keys; unparsable arguments; each
`loose/1` rule alone; size cap; depth cap; stateful Responses; head rules;
conversation anchor; tools-free conversation id; scopes; cache control;
cross-dialect equivalence; reply linkage for each dialect.

The set is larger than the 150 vectors the plan aimed for. Equivalence needs
the same conversation in three dialects, and the categories are many.

### Choices the vectors pin

These are places where the draft rules were silent or ambiguous. The vectors
record what the reference implementation does, so that other implementations
match it.

1. **Repeated call id inside one assistant message.** A result takes the index
   of the *last* call with that id (`repeated-id-in-message`). Decision 0002
   says "nearest preceding assistant message holding that id" and does not say
   which one inside a message.
2. **Dates inside sentences stay.** `loose/1` removes date-only lines
   (`loose-date-in-sentence-kept`). This is open question 2 of 0002.
3. **Size cap boundary.** The cap applies to the CBOR length of the head
   payload plus every body message. `size-at-cap` has exactly that length and
   gets ids. `size-over-cap` has a cap one byte lower and gets none. The
   default 2 MiB cap is not exercised, because a vector that large does not
   belong in the repository.
4. **Depth.** 128 nested containers give ids, 129 give none. A 5000-deep
   arguments string must give none and not crash.
5. **Both reasoning outcomes.** Vectors cover a client that sends reasoning
   back and one that does not.

### Bugs the vectors found

Writing the vectors and the independent cross-check found three bugs in the
reference implementation. All three are fixed in the same change, each with a
test, and all three change ids for the inputs concerned.

1. `NaN`, `Infinity` and `-Infinity` in tool arguments were accepted (Python's
   `json` module allows them). They are not JSON, so such arguments are now
   `args_raw`, as 0002 says. Before, they became `null` inside `args`.
2. An integer of more than about 4300 digits made Python's `json` module fail,
   so valid arguments became `args_raw`. They are valid JSON, too large for a
   double, and now print as `null` as 0002 says.
3. The loose form dropped a message's `name`. 0002 lists the loose rules and none
   of them touches `name`, so the loose form now keeps it, like `role`.

### The independent cross-check

`vectors/tools/xcheck.py` does not import kvsig. For every vector that has ids it
rebuilds the canonical bytes with `cbor2` in canonical mode, rebuilds the loose
form with a second implementation of the loose rules written from 0002, and
recomputes every id with a hand-built HMAC
(`"kvsig/1" 0x00 label 0x00 len(scope) scope payload`, epoch byte plus the first
16 bytes). Any difference exits non-zero. Bug 3 above was found this way.

### What the first set does not cover

- Streamed responses (reply linkage from server-sent events).
- The legacy completions dialect, which the library does not implement yet.
- A request near the default 2 MiB cap.
- Inputs that are not valid UTF-8 JSON.
- Key-ring behaviour (the vectors use one key at a time).

## Why

- Bytes are the contract, so they are the normative field. The readable form
  makes a failure diagnosable without a CBOR tool.
- A line protocol and one vector per file keep the runner small and let any
  language join without a shared library.
- Hash-pinned files and a regenerate-and-compare check stop silent edits, which
  matters once the vectors are the definition of the spec.
