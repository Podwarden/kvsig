# 0003. Dialect mappings: Anthropic Messages and OpenAI Responses

Status: **proposed**, open for comment. Pinned by `python/tests/test_anthropic.py`,
`test_responses.py` and `test_equivalence.py`.

The goal of every mapping is cross-dialect equivalence: one conversation sent
through OpenAI Chat Completions, Anthropic Messages or OpenAI Responses gives
one canonical form, and so the same ids. `test_equivalence.py` proves it for a
conversation with a system prompt, a tool, an image, reasoning, a tool call
and its result.

## Anthropic Messages (`anthropic.messages`)

- `system`, a string or a list of text blocks, is one head message with role
  `system` and one text part per block (as a Chat system message whose
  content is a list of text parts).
- A user turn is split so that each `tool_result` block is its own message
  with role `tool`, in place. The turn's other blocks stay together, in order,
  as user messages. (Chat Completions expresses the same turn that way.)
- `tool_result`: `content` (a string or blocks) becomes the result's parts,
  images and documents included, **in place**. `is_error: true` adds
  `error: true`.
- Assistant blocks, in order: `thinking` becomes a `reasoning` part (the
  `signature` is not part of the conversation); `text` is text; `tool_use`
  becomes `tool_call` with `args` the canonical JSON text of `input` and `ref`
  its index among the message's `tool_use` blocks. `redacted_thinking`,
  `server_tool_use`, `*_tool_result` and any newer block are opaque.
- `image` and `document` sources: `base64` hashes the decoded bytes with the
  source `media_type`; `text` hashes the UTF-8 data; `url` and `file` are
  references. A `document` with a `title` or `context` is opaque (the model
  reads those beside the file).
- Tools: a tool without a `type` (or `type: custom`) becomes
  `{name, desc, schema}` from `input_schema`. A server tool (`web_search_*`,
  `bash_*`, ...) becomes `{type, def}`.
- `cache_control` is ignored everywhere, including inside opaque values and
  server-tool definitions. `citations` are ignored.

## OpenAI Responses (`openai.responses`)

- `instructions` is the head's first system message; a leading run of
  `system`/`developer` message items follows it in the head. `input` given as
  a string is one user message.
- A run of consecutive assistant-side items (`reasoning`, assistant `message`,
  `function_call`, `custom_tool_call`) is one assistant message, in item order.
- `reasoning` becomes one reasoning part: its `reasoning_text` content, or
  else its `summary_text` parts, joined by a blank line. An item with only
  `encrypted_content` is opaque.
- `function_call` becomes `tool_call` (arguments as in Chat Completions);
  `custom_tool_call` becomes `tool_call` with `args_raw`. `call_id` sets the
  reference, like a Chat `tool_calls[].id`.
- `function_call_output` and `custom_tool_call_output` are `tool` messages.
- Content: `input_text`/`output_text` are text (annotations ignored);
  `input_image` and `input_file` are media; `refusal` is opaque with the same
  value a Chat message's `refusal` field gives.
- Any other item (`web_search_call`, `computer_call`, `mcp_*`,
  `item_reference`, ...) is a message with role `""` and one opaque part.
- **Stateful requests.** With `previous_response_id` or `conversation`, the
  body is not the whole conversation: the request gets message and head ids
  but no prefix or conversation ids.
- Tools: `type: function` becomes `{name, desc, schema}` from `parameters`;
  `strict` is ignored. Other tools become `{type, def}`.

## Known non-equivalences

These conversations do *not* map to the same canonical form across dialects,
on purpose or because one dialect cannot express them:

1. A tool result marked as an error (Anthropic `is_error`); Chat and
   Responses have no such flag.
2. Several reasoning blocks in one assistant turn (Anthropic interleaved
   thinking); Chat has one `reasoning_content`.
3. Two assistant message items in a row in Responses become one message; two
   Chat assistant messages stay two.
4. Responses reasoning given only as a summary; Chat carries the raw text.
5. Server-side tools of each provider, which have no counterpart elsewhere.
6. A Chat assistant `refusal` is placed after the content; a Responses
   `refusal` part keeps its position.
