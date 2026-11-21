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
  An integer whose magnitude exceeds 2^53 is first rounded to a double. An
  integer too large for a double is printed in full decimal.
- `true`, `false`, `null` as literals.
- Nesting deeper than 128 levels: the request gets no ids.

## Canonical data model

- **Head** = every message with role `system` or `developer`, wherever it
  occurs, in order. **Body** = every other message, in order. *(Open: a
  mid-conversation system message changes the head, not the body.)*
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
  - `opaque {type, sha256}`: any part the dialect mapping does not know. The
    hash is over its canonical JSON text. It is never dropped.
- **References.** Tool-call ids never enter a hash. A call's `ref` is its index
  within its own assistant message. A result's `ref` is the index of its call
  in the nearest preceding assistant message holding that id, or `-1`. A
  message canonicalised alone therefore equals the same message inside a later
  request.

## Loose profile `loose/1`

In order: drop `reasoning` parts; remove `<system-reminder>…</system-reminder>`
and `<environment_context>…</environment_context>` blocks (ASCII
case-insensitive; an unclosed tag leaves the rest as it is); remove lines that
hold only an ISO date or date-time (ASCII digits only); collapse runs of
whitespace (the Unicode `White_Space` characters plus U+001C to U+001F, as
listed in the profile table) to one space and trim; drop a text that starts
with a listed preamble; drop texts that are empty afterwards; sort object
members in `args` and `schema`. The table is data in
`python/src/kvsig/loose.py` and its version is part of every loose label.

## Ids

```
H(K, label, scope, payload) = epoch || HMAC-SHA-256(K, "kvsig/1" 0x00 label 0x00 u8(len(scope)) scope payload)[0:16]
```

- Labels: `head`, `msg`, `node`, `conv`; loose ids use `loose/1:head`,
  `loose/1:msg`, `loose/1:node`, `loose/1:conv`.
- `head` is over the CBOR of `{"head": [...], "tools": [...]}`; `msg` over one
  message; `node[i]` over `node[i-1] || msg[i]` (raw 17-byte ids), with
  `node[-1] = head`; `conv` over `loose_head || loose_node[0]`.
- The conversation id is the loose one; there is no exact conversation id.
- `scope` is empty, or SHA-256 of the CBOR map `{"cache_salt": text,
  "tenant": bytes}` with absent members left out.
- Epoch: 1 to 255 for deployment keys; 0 is reserved for published test keys.
- Rendering: 34 lowercase hex characters.
