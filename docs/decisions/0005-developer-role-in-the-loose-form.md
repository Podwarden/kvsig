# 0005. The developer role in the loose form (`loose/2`)

Status: **proposed**, open for comment. Pinned by
`python/tests/test_system_shapes.py` and, for `loose/1`, by the
`system-as-*` vectors in `vectors/v1/openai.chat` and `vectors/v1/openai.responses`.

## Question

One system prompt reaches a server in several shapes:

| Dialect | Shape | Head message (0003) |
|---|---|---|
| OpenAI Responses | top-level `instructions` | role `system` |
| OpenAI Responses | a leading `{"type": "message", "role": "developer", "content": ...}` item | role `developer` |
| OpenAI Chat | a leading `system` message | role `system` |
| OpenAI Chat | a leading `developer` message | role `developer` |
| Anthropic Messages | top-level `system` | role `system` |

Clients move between them. OpenCode 2.3.2 (November 2026) stopped sending its
system prompt in `instructions` and sends it as a leading developer item on
every Responses route, because GPT-6.2 models do not cache `instructions`
([anomalyco/opencode#64542](https://github.com/anomalyco/opencode/pull/64542),
[#64544](https://github.com/anomalyco/opencode/pull/64544)). The text is the
same string as before.

Should the two shapes give the same `sys` and `head` ids, exact and loose?

## What the rules give today

0002 keeps a message's `role` in both the exact and the `loose/1` form, and
0003 maps `instructions` to a `system` message. So the two shapes differ in
the role of the one head message, and **every head-derived id differs**:
`sys`, `head`, every `nodes[i]`, `loose_sys`, `loose_head`, every
`loose_nodes[i]` and `conv`. Only `tools`, `msgs` and `loose_msgs` match.
The vectors `openai.responses/system-as-instructions` and
`openai.responses/system-as-developer-item` pin this, and pair each shape
with its Chat twin (`openai.chat/system-as-system-message`,
`openai.chat/system-as-developer-message`), which does match.

## Decision

1. **Exact ids keep the role.** No change. The role is part of what the
   model is given, and how it is rendered is up to the server: an engine's
   chat template may render `system` and `developer` differently, or reject
   one of them, and kvsig works before rendering. An exact id must never
   claim that two prompts are the same when they may not be. The provider in
   this case shows that the two shapes are not interchangeable for it either:
   one is cached and the other is not. A client that changes shape therefore
   starts a new exact head, which is also what happens to its prompt cache.

2. **A new loose profile, `loose/2`, reads `developer` as `system`.** It is
   `loose/1` plus one rule, applied to every message (head and body): a
   message whose role is `developer` has role `system` in the loose form.
   Everything else is unchanged. The reference package renames the role after
   loosening the parts; the order does not matter, because no part rule reads
   the role.

   - The loose ids are for identity: grouping requests into conversations
     and following a session. A client that changes where it puts the same
     system prompt is the same agent in the same conversation; under
     `loose/1` its `conv` changes, and [Reading the ids](../reading-the-ids.md)
     would read the change as "a different agent". A session resumed across
     the client upgrade would split in two.
   - Cross-dialect equivalence (0003) is the goal of every mapping, and the
     same harness often sends `developer` to one provider and `system` to
     another (Anthropic has no developer role). OpenAI itself presents the
     two as one slot: its API reference says that "with o1 models and newer,
     `developer` messages replace the previous `system` messages"
     ([openai-openapi](https://github.com/openai/openai-openapi), Chat
     Completions `developer` message). Under `loose/2` all five shapes above
     give one `loose_sys`, one `loose_head` and one `conv`.
   - Body messages are renamed too, so a mid-conversation instruction sent
     as a Chat `system` message and as a Responses developer item has one
     loose message id.
   - Reading `developer` as `system` loses the distinction between the two
     roles in the loose form. Nothing in the loose ids depends on it: both
     already count as head roles (0002), so the head boundary does not move.

3. **`loose/2` is a new profile version, not an edit of `loose/1`.** The
   profile version is part of every loose label, so switching from `loose/1`
   to `loose/2` changes **every** loose id of **every** request (`loose_head`,
   `loose_sys`, `loose_tools`, `loose_msgs`, `loose_nodes` and `conv`), not
   only those of requests with a developer message; `loose/2` ids never equal
   `loose/1` ids. The reference package ships it as `LOOSE_V2`
   (`LooseProfile.role_map`); `LOOSE_V1` stays the default and its output is
   unchanged, including its fingerprint. No existing vector changes.

## Migration

A deployment that moves from `loose/1` to `loose/2` resets every
conversation id and every affinity key built on loose ids once, as a key
rotation does. To move without losing affinity:

- compute both profiles during the cutover (`ids(canon, key,
  profile=LOOSE_V1)` and `ids(canon, key, profile=LOOSE_V2)`) and look up
  state under either, until the `loose/1` entries age out; or
- flush loose-keyed state at a quiet point and switch at once.

Exact ids (`head`, `sys`, `tools`, `msgs`, `nodes`) do not depend on the loose
profile, so prefix-cache routing on exact ids is unaffected.

## When this is accepted

- `LOOSE_V2` becomes the default profile. That changes the library's default
  output, so it ships as a SemVer major change with a note in the CHANGELOG.
- A vector set for `loose/2` is generated (the manifest names one loose
  profile per set), and the `system-as-*` vectors there state the opposite
  loose relations: equal `loose_sys`, `loose_head` and `conv`, exact ids
  still different.

## Still open

1. **Tools ahead of the system prompt.** OpenCode puts the developer item
   after a leading `additional_tools` item on models that declare tools that
   way. Such an item is not a message; 0003 makes it a message with role `""`
   and one opaque part, so the head is empty and the system prompt is a body
   message. Those requests get a different `sys` and `conv` even under
   `loose/2`. Mapping that item into `tools` is a dialect question for 0003,
   to settle with captured traffic.
2. **`instructions` and a developer item together.** A client may send both. Under
   `loose/2` they are two `system` messages in the head, in that order, which
   is not equal to one message holding both texts. That is intended: kvsig
   does not merge messages.
