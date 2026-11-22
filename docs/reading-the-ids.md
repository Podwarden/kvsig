# Reading the ids

kvsig gives every request a set of ids. Each one answers a different question.
This page says what each id identifies, and how to tell from two requests what
changed between them. The normative definitions are in
[decision 0002](decisions/0002-draft-canonical-rules.md).

All ids are keyed: they mean something only to components that share the
deployment key, and they reveal nothing about content to anyone else.

## What each id identifies

| Id | Identifies | Changes when |
|---|---|---|
| `sys` | the system and developer messages at the start of the request | the system prompt changes |
| `tools` | the tool list | a tool is added, removed or edited, or tools are reordered |
| `head` | `sys` and `tools` together: everything before the first body message | either of the above |
| `msgs[i]` | message `i` of the body, on its own | that message changes |
| `nodes[i]` | the whole prompt up to and including message `i`, like a git commit | anything before or at position `i` changes |
| `conv` | the conversation: the loose system messages and the first real message | a different system prompt or a different opening message |

Every id except `conv` also has a **loose** form (`loose_sys`,
`loose_tools`, `loose_head`, `loose_msgs`, `loose_nodes`). A loose id ignores
noise that harnesses add between turns: reminder blocks, date-only lines,
whitespace, reasoning, and the member order inside tool arguments and schemas.
`conv` exists only in the loose form.

## Exact or loose?

- Use **exact** ids for anything that depends on the bytes the model sees,
  such as prompt caching. Two requests with equal exact `nodes[i]` have the same
  prompt up to message `i`.
- Use **loose** ids for identity: grouping requests into conversations,
  following a session in logs, linking a reply to the next request.

## What changed between two requests

Compare request A with a later request B from the same client.

| Observation | Meaning |
|---|---|
| `B.nodes` starts with all of `A.nodes` | B continues A: same prompt, new messages at the end. A prompt cache keyed on A's prefix is reusable for B. |
| same `conv`, `sys` equal, `tools` differ | The conversation goes on, but its tool list changed (an MCP server connected, a tool was loaded on demand). The cached prompt after the tool list is lost. |
| same `conv`, `loose_sys` equal, exact `sys` differs | The system prompt changed only in noise (a date line, a reminder). |
| same `conv`, `B.nodes` shares a shorter prefix with `A.nodes` | Part of the history was rewritten: an edit, a fork, or a harness rewriting an old message. Prefix ids up to the shared point are still valid. |
| different `conv`, same `sys` | A new conversation under the same system prompt: a new session, or a compaction that replaced the history with a summary. |
| different `conv`, different `sys` | A different agent: a subagent, a title-generation call, another tool. |

One exception to the last row: under `loose/1` the role of a system message
is part of its identity, so a client that moves the same system prompt from
`system` (or Responses `instructions`) to a `developer` message gets a new
`sys` and a new `conv`, as OpenCode 2.3.2 did. The proposed `loose/2` profile
reads `developer` as `system` and keeps the conversation id; exact ids change
either way. See [decision 0005](decisions/0005-developer-role-in-the-loose-form.md).

A cache-aware router can use the third column directly. For example, a request
with the same `conv` but a new `tools` id still belongs on the replica that
served the conversation, because the system-prompt part of its prompt is still
cached there. Its prefix will be recomputed once, and from then on it extends
normally.

## What the ids do not tell you

- **That two requests are the same session.** `conv` identifies content, not a
  session. Two users who open with the same message under the same system
  prompt share it, unless a scope (a tenant, a `cache_salt`) separates them.
- **Lineage across a compaction.** A compaction replaces the history, so the
  conversation after it has a new `conv`. Linking the two is the job of a
  lineage layer above the ids.
- **Token-level cache blocks.** Engines cache in token blocks, after
  tokenization. kvsig works on messages, before tokenization. kvsig tells you
  *which conversation and which prefix*; the engine's block hashes tell you
  *which blocks*.
