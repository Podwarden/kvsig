# Changelog

All notable changes to the specification and the reference implementations.
The library follows SemVer; spec versions are labelled `kvsig/N`.

## Unreleased

Nothing yet.

## 0.1.0 (draft 0.1 of `kvsig/1`)

The first release. The Python package is published on PyPI as `kvsig`
(`pip install kvsig`), pure Python, no runtime dependencies, typed, for Python
3.10 to 3.13.

What 0.1 promises (full text: SPEC.md, "Versioning and compatibility"):

- **Stable ids.** Under the spec label `kvsig/1` and the loose profile
  `loose/1` (the default), the canonical bytes and ids pinned by `vectors/v1`
  revision 0.1 (232 vectors) do not change in any later release. A change to
  them ships under a new label or loose profile version, with its own vectors.
- **Experimental `loose/2`.** `LOOSE_V2` (decision 0005, proposed) is included,
  has no vectors yet, and may change until the decision is accepted.
- **Defaults.** Changing the default loose profile is a breaking change: before
  1.0 it happens only in a minor release, with a CHANGELOG entry.

Changes in this release:

- The spec status is "draft 0.1". Until each section of SPEC.md is written, the
  decisions 0001 to 0005 and the vectors are the rules, and the vectors win
  where the two disagree. New section: Versioning and compatibility.
- `vectors/v1/manifest.json` gains `"revision": "0.1"`. No vector file changed.
  The conformance runner prints the vector set revision and the adapter
  version (new optional `version` field of the `info` answer).
- `kvsig.__version__`. Package metadata for PyPI; the wheel ships `py.typed`,
  `LICENSE` and `NOTICE`.
- A release workflow: tag `vX.Y.Z` builds the sdist and wheel, tests the built
  wheel on Python 3.10 to 3.13, runs the conformance runner against it and
  publishes to PyPI with Trusted Publishing. A manual run publishes to TestPyPI.

Everything below was developed before 0.1.0:

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
- Test vectors `vectors/v1`, the conformance runner (`conformance/run.py`, with a
  Python adapter), the vector generator and an independent cross-check
  (decision 0004, proposed).
- **Changed ids (pre-release, intentional), found by the vectors:**
  tool arguments `NaN`, `Infinity` and `-Infinity` are no longer treated as JSON
  (they become `args_raw`); an integer of more than 4300 digits is valid JSON and
  prints as `null` instead of making the arguments `args_raw`; the loose form
  keeps a message's `name`.
- Decision 0005 (proposed): a `loose/2` profile that reads a `developer`
  message as a `system` message, so a system prompt sent as Responses
  `instructions`, as a leading developer item, or as a Chat `system` or
  `developer` message gives one conversation id. Shipped as `LOOSE_V2`
  (`LooseProfile.role_map`); `LOOSE_V1` stays the default and unchanged.
- Vectors `system-as-instructions`, `system-as-developer-item`,
  `system-as-system-message` and `system-as-developer-message` pin the
  `loose/1` behaviour: the instructions and developer shapes have different
  head ids and conversation ids. No existing vector changed.
- Vectors `system-as-developer-item-request-options`,
  `system-as-instructions-tool-turn`, `system-as-developer-item-tool-turn`,
  `system-as-instructions-no-tools` and `system-as-developer-item-no-tools`:
  Responses request options, a tool turn and a tool-less request under both
  system prompt shapes. No existing vector changed.
