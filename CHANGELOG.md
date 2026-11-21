# Changelog

All notable changes to the specification and the reference implementations.
The library follows SemVer; spec versions are labelled `kvsig/N`.

## Unreleased

- Repository created: licences, governance, specification outline.
- Decision 0001: canonical bytes are a restricted deterministic CBOR profile.
- Decision 0002 (proposed): draft canonical rules.
- Python reference implementation: CBOR encoder, canonical JSON text, the
  `openai.chat` dialect, the `loose/1` profile, keyed ids, key rings, `IdCache`.
- Dialects `anthropic.messages` and `openai.responses` (decision 0003).
- `Ids` gains `sys`, `tools`, `loose_sys` and `loose_tools`.
- **Changed ids (pre-release, intentional):** the conversation id is now built
  from the loose system messages and the first message with content, without
  the tools. Conversation ids from earlier development builds do not match.
  The labels are not bumped because nothing has been released; from 0.1 on, a
  change like this needs a new label or profile version.
