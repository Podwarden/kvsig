# Conformance runner

The runner checks any kvsig implementation against the test vectors in
`vectors/v1/`. It talks to your implementation through a small stdin/stdout
protocol, so an implementation in any language needs only a thin adapter.

```
python conformance/run.py [--level N] [--only TEXT] [-v] -- <adapter command>
python conformance/run.py -- python conformance/adapters/python_adapter.py
python conformance/run.py --manifest-only        # no adapter: hashes only
```

The runner needs Python 3.10 or later and nothing else. It first checks that
`vectors/v1/manifest.json` matches the files on disk, and that the vector set
agrees with itself (the `equivalent_to` and `relations` claims hold on the
expected values). Then it starts your adapter, sends requests, and prints a
table:

```
level           openai.chat    openai.responses  anthropic.messages    total
L1                    88/88               38/38               36/36  162/162
L2                    ...
```

Rows are the level of the vector, columns are dialects, cells are passed/total.
The exit status is 0 when everything passes, 1 when a vector fails, 2 when the
setup is wrong (stale manifest, adapter crash).

## The protocol

The runner starts your adapter as a subprocess. It writes one JSON object per
line to the adapter's stdin and reads one JSON object per line from its
stdout. The adapter answers every request, in order, and never writes anything
else to stdout (use stderr for logs). Every response has `"ok": true`, or
`"ok": false` with an `"error"` text. An `ok: false` answer fails the vector.

All byte values are standard base64 (RFC 4648, with padding). All ids are
lowercase hex strings of 34 characters: the epoch byte, then 16 bytes of
HMAC output.

### Common request fields

| Field | Meaning |
|---|---|
| `op` | One of `info`, `scope`, `canonicalize`, `ids`, `reply_id`. |
| `dialect` | `openai.chat`, `openai.responses` or `anthropic.messages`. |
| `input` | The request body as parsed JSON. Used when `input_raw_b64` is absent. |
| `input_raw_b64` | When present, the exact wire bytes (UTF-8 JSON text) of the request body. Parse these yourself and ignore `input`. |
| `max_bytes` | Optional. The size cap in bytes for this request. Absent means the default, 2 MiB (2097152). |

Why raw bytes: some inputs cannot be carried by a JSON line. A JSON text may
hold a lone surrogate escape (a high or low surrogate written as `\u` plus four
hex digits) or a repeated object member name. A JSON parser in the runner
would repair or merge those before your code saw them. In those vectors the
runner sends the wire text untouched in `input_raw_b64`, and your adapter must
parse it with a parser that keeps lone surrogates as lone surrogates (or
reports them) and applies the "last duplicate wins, at the first position"
rule of decision 0002. Parse with your normal JSON parser, then hand the value
to the library, as a server would.

In JavaScript, parse into a structure that keeps member order (a `Map`, or a
reviver that records order): plain objects reorder integer-like keys.

### `info`

Request: `{"op":"info"}`.

Response: `{"ok":true,"name":"my-impl","spec":"kvsig/1","levels":2,"dialects":["openai.chat"]}`

`levels` is the highest level you claim (1, 2 or 3). `dialects` lists what you
implement. The runner skips vectors for other dialects and vectors above your
level. A user can lower the level with `--level`.

### `scope`

Request: `{"op":"scope","cache_salt":"text or null","tenant_b64":"base64 or null"}`.

Response: `{"ok":true,"scope_b64":"..."}`.

The scope is empty (empty string here) when neither input is given or both are
empty. Otherwise it is the SHA-256 of the CBOR map holding `cache_salt` (text)
and `tenant` (bytes), with absent or empty members left out (decision 0002).

### `canonicalize`

Request: common fields.

Response when the request gets ids:

```json
{"ok":true,"none":false,"stateful":false,
 "canonical_bytes_b64":"...","loose_bytes_b64":"..."}
```

Response when it gets none (size cap, depth cap, not a chat body):
`{"ok":true,"none":true}`.

`canonical_bytes_b64` is the CBOR encoding (decision 0001) of the map
`{"head": [...], "tools": [...], "messages": [...]}`: the head messages, the
tool definitions and the body messages of the exact canonical form.
`loose_bytes_b64` is the same map for the loose form (`loose/1`). Level 1
implementations may leave `loose_bytes_b64` out. `stateful` is true when the
request continues server-side history (Responses `previous_response_id` or
`conversation`).

### `ids`

Request: common fields plus `key_b64` (the 32-byte key), `epoch` (0 to 255)
and `scope_b64` (may be the empty string).

Response when the request gets ids:

```json
{"ok":true,"none":false,"ids":{
  "head":"..","sys":"..","tools":"..","msgs":[".."],"nodes":[".."],
  "loose_head":"..","loose_sys":"..","loose_tools":"..",
  "loose_msgs":[".."],"loose_nodes":[".."],"conv":".."}}
```

`conv` is `null` when there is no conversation id. For a stateful request
`nodes` and `loose_nodes` are empty lists and `conv` is `null`. Level 1
implementations return only `head`, `sys`, `tools`, `msgs` and `nodes`.
When the request gets no ids, answer `{"ok":true,"none":true}`.

### `reply_id` (Level 3)

Request: `dialect`, `input` (the whole response body as the provider sent it),
`key_b64`, `epoch`, `scope_b64`.

Response:

```json
{"ok":true,"none":false,"canonical_bytes_b64":"..","loose_bytes_b64":"..",
 "msg":"..","loose_msg":".."}
```

The reply is the assistant message canonicalised alone. `canonical_bytes_b64`
is the CBOR of that one message map (`{"role": ..., "parts": [...]}`). `msg`
is its exact message id, `loose_msg` its loose message id. For
`openai.chat`, the response body holds the message at `choices[0].message`:
use that. For `anthropic.messages` the reply is the whole response (its
`content`). For `openai.responses` it is the `output` items. Streamed
responses are not covered yet: the vectors carry the assembled response.

## What the runner checks

For every vector at or below the level under test:

1. `scope`, if the vector has a `cache_salt` or `tenant`.
2. `canonicalize`: `none`, `stateful`, `canonical_bytes_b64`, and (Level 2 and
   up) `loose_bytes_b64`.
3. `ids` for each test key in the manifest: the exact ids (`head`, `sys`,
   `tools`, `msgs`, `nodes`) and, from Level 2, the loose ids and `conv`.
4. `reply_id` for each test key, at Level 3, when the vector has a `reply`.

A vector passes when every answer equals the expected value. Levels are
defined in SPEC.md. Level 1 is the canonical form and the exact ids for at
least one dialect. Level 2 adds `loose/1` and the conversation id for all
three dialects. Level 3 adds reply linkage.

## Writing an adapter

1. Read `docs/decisions/0004-test-vectors.md` for the vector format.
2. Write a loop that reads a line, parses it, calls your library, and prints
   one JSON line. `conformance/adapters/python_adapter.py` is about 130 lines.
3. Run `python conformance/run.py -- <your command>`. Use `--only openai.chat/`
   to focus on one dialect and `-v` to see every failure.
4. A failing line prints the first difference, for example the field and the
   two ids. For a canonical-bytes failure, compare your canonical form with the
   readable `expect.canonical` in the vector file.

An adapter should never crash on a hostile input: a request that gets no ids
is an ordinary `none: true` answer.

## Claiming conformance

Conformance is self-declared. Run the runner at the level you claim and link
its output in your README. List your implementation in an issue on this
repository.
