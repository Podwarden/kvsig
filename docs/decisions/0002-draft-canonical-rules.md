# 0002. Draft canonical rules (provisional)

Status: **proposed**, open for comment until the spec draft is complete. These
are the choices the first reference implementation makes. Each one is pinned
by a test, and each can still change in 0.x.

## Canonical JSON text (for tool arguments, tool schemas and unknown parts)

- No whitespace. Separators `,` and `:`.
- Object members keep the order they had in the input (exact profile), or are
  sorted by Unicode code point of the key (loose profile). Implementations in
  languages whose native objects reorder keys (JavaScript reorders
  integer-like keys) must parse into an order-preserving structure.
- Duplicate keys in a parsed JSON text: the last value wins, at the position
  of the first occurrence.
- Strings: only `"`, `\` and the control characters U+0000 to U+001F are
  escaped. `\b \f \n \r \t` use their short forms, the rest `\u00xx` in
  lowercase hex. Everything else is literal UTF-8. Lone surrogates become
  U+FFFD.
- Numbers: the value as an IEEE 754 double, printed with the ECMAScript
  `Number.prototype.toString` algorithm (as in RFC 8785). `-0` prints as `0`.
  An integer whose magnitude exceeds 2^53 is first rounded to a double. A
  number too large for a double, and NaN or an infinity, prints as `null`
  (what a parser that reads numbers as doubles produces).
- Object keys are taken as Unicode scalars (lone surrogates become U+FFFD)
  before anything else. Keys that become equal are merged by the duplicate-key
  rule above.
- `true`, `false`, `null` as literals.
- Depth counts containers (arrays and objects) only. Up to 128 nested
  containers are allowed; a 129th gives the request no ids.

## Canonical data model

- **Head** = the leading run of messages with role `system` or `developer`.
  **Body** = every message after it, in order, including any later system or
  developer message. (So an instruction injected mid-conversation extends the
  body; it does not rewrite the head, and prefix ids stay prefixes.)
- **Messages** are `{role, parts}`, plus `name` when the request gives a
  non-empty one. A message that is not an object is
  `{role: "", parts: [opaque]}`; it is kept, never dropped.
- **Tools** become `{"name", "desc", "schema"}`: `desc` is `""` when absent,
  and `schema` is the canonical JSON text of the parameters object. A tool that
  is not a function tool becomes `{"type", "def"}`, with `def` the canonical
  JSON text of the whole definition.
- **Parts** (maps, `t` names the type):
  - `text {v}`; an empty text is dropped; a string content equals one text
    part; adjacent text parts are not merged.
  - `media {sha256, mime, src}`: `sha256` is 32 raw bytes. `src` is `bytes`
    (the hash is over decoded inline data), `url` (over the UTF-8 URL) or
    `file_id` (over the UTF-8 file id), so the three can never collide. The
    MIME type comes only from a data-URL header or an explicit field. It is
    never guessed from a file extension.
  - `tool_call {name, args, ref}`, where `args` is canonical JSON text. When
    the arguments string does not parse as JSON, the part is
    `tool_call {name, args_raw, ref}`, so raw text never equals valid JSON.
  - `tool_result {ref, parts}`, plus `error: true` only when the dialect marks
    the result as an error.
  - `reasoning {v}`: the first part of an assistant message.
  - `opaque {type, sha256}`: any value the dialect mapping does not know,
    including a part, tool call or message that is not an object, and the
    assistant `refusal` and `audio` fields. The hash is over its canonical
    JSON text. It is never dropped.
- **Deprecated OpenAI fields.** `functions` become tools. An assistant
  `function_call` becomes a `tool_call` after any `tool_calls`. A message with
  role `function` becomes a `tool_result` with `ref: -1`, keeping its `name`.
- **References.** Tool-call ids never enter a hash. A call's `ref` is its index
  within its own assistant message. A result's `ref` is the index of its call
  in the nearest preceding assistant message holding that id, or `-1`. Every
  entry of `tool_calls` takes an index, including one that is not an object.
  A message canonicalised alone therefore equals the same message inside a
  later request.

## Size cap

The cap is on the total CBOR length of the head payload plus every body
message (exact profile), default 2 MiB. Over the cap, the request gets no ids.
Implementations may stop early on any lower bound of that length.

## Loose profile `loose/1`

In order: drop `reasoning` parts; remove `<system-reminder>…</system-reminder>`
and `<environment_context>…</environment_context>` blocks (ASCII
case-insensitive; an unclosed tag leaves the rest as it is); remove lines that
hold only an ISO date or date-time (ASCII digits only, lines end at LF); collapse
runs of whitespace (the Unicode `White_Space` characters plus U+001C to U+001F,
as listed in the profile table) to one space and trim; drop texts that are
empty afterwards; sort object members in `args` and `schema` by code point.
The table is data in `python/src/kvsig/loose.py` and its version is part of
every loose label. There are no harness-specific preamble rules.

## Ids

```
H(K, label, scope, payload) = epoch || HMAC-SHA-256(K, "kvsig/1" 0x00 label 0x00 u8(len(scope)) scope payload)[0:16]
```

- Labels: `head`, `msg`, `node`; loose ids use `loose/1:head`,
  `loose/1:msg`, `loose/1:node`, and the conversation id is built from
  `loose/1:sys` and `loose/1:conv`.
- `head` is over the CBOR of `{"head": [...], "tools": [...]}`; `msg` over one
  message; `node[i]` over `node[i-1] || msg[i]` (raw 17-byte ids), with
  `node[-1] = head`.
- `conv` is over `loose_sys || loose_msg[a]`. `loose_sys` is the id (label
  `loose/1:sys`) of the CBOR map `{"head": [...]}` holding the loose head
  messages **without the tools**; `a` is the first body message whose loose
  form still has parts. When no message has, there is no conversation id.
  - A constant opener that loosens to nothing (an environment block, a
    reminder) would otherwise give every session the same id.
  - Tools are left out because harnesses add and remove them mid-session (an
    MCP server, tool search). Measured on recorded traffic (2026-11-21):
    leaving them out kept the main Codex and OpenCode sessions on one id
    across an added MCP tool, while subagents, title calls and post-compaction
    conversations kept ids of their own. Tools stay in the head and prefix
    ids: a different tool list is a different prompt.
- The conversation id is the loose one; there is no exact conversation id. It
  identifies *content*, not a session: two users who open with the same
  message under the same head share it, unless a scope separates them.
- `scope` is empty, or SHA-256 of the CBOR map `{"cache_salt": text,
  "tenant": bytes}` with absent members left out.
- Epoch: 1 to 255 for deployment keys; 0 is reserved for published test keys.
- Rendering: 34 lowercase hex characters.

## Still open

To be settled with test vectors built from captured traffic of real harnesses
(Claude Code, Codex, OpenCode, Cline):

1. **Reply linkage on reasoning models.** A client that does not send
   reasoning back makes a reply's exact id differ from the same message in
   the next request. Recorded traffic (2026-11-21): Claude Code, Codex,
   OpenCode and Cline all sent reasoning back on every earlier turn.
   Proposal: still define reply linkage on loose ids, which hold either way.
2. **Dates inside sentences.** `loose/1` removes date-only lines. A date in a
   sentence ("Today's date is ...") survives and would change the
   conversation id daily.
3. **Tools without parameters.** OpenAI may omit `parameters` (`"null"`
   here); Anthropic always sends a schema. Settle with the Anthropic adapter.
