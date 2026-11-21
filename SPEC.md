# Content-Derived Conversation Identifiers for LLM Chat APIs (kvsig/1)

**Status: working draft. Not stable. Do not implement against it yet.**
Labels, byte encodings and ids in this document will change before spec v1 is
frozen. Version 1.0 of the reference library marks the freeze.

Licence: [CC BY 4.0](LICENSE-SPEC).

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY and OPTIONAL are to be interpreted as described in BCP 14
(RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

## Outline

The sections below are placeholders. Each one is filled in through a pull
request, and each open question becomes a test vector.

1. **Status, scope and goals.** Stable ids for a conversation and its prefixes,
   derived from a stateless request with no client cooperation; the same ids
   across API dialects and across components that share a deployment key; no
   content leaked to holders of ids. Non-goals: token-level KV block hashing,
   identity across deployments, stateful APIs.
2. **Terminology.** Request, dialect, head, body, message, part, canonical
   form, exact and loose profiles, deployment key, key ring, epoch, scope,
   message / head / node / conversation id, reply linkage, conformance levels.
3. **Canonical data model.** Messages `{role, parts}`; part types `text`,
   `media`, `tool_call`, `tool_result`, `reasoning`, `opaque`; tool
   definitions; the rules that make tool-call references position-local.
4. **Dialect mappings.** OpenAI Chat Completions, OpenAI Responses, Anthropic
   Messages, legacy completions; cross-dialect equivalence.
5. **Canonical encoding.** Byte encoding, Unicode rules, numbers, duplicate
   keys, media hashing. *Open: encoding choice, see
   [docs/decisions](docs/decisions/).*
6. **Loose profile `loose/1`.** The volatile-span table as versioned data.
7. **Id derivation.** Keyed HMAC-SHA-256, truncated, with an epoch byte;
   labels; prefix chaining; conversation id; text rendering.
8. **Keys, epochs and rotation.**
9. **Conformance levels.** Level 1 (core ids), Level 2 (loose profile and
   conversation id across dialects), Level 3 (reply linkage).
10. **Privacy considerations.**
11. **Security considerations.**
12. **Versioning.**
13. **Test vectors.** Format and manifest.
14. **Registries.** Dialects, part types, labels, loose profiles.
15. **Prior art and acknowledgements.**

Annexes (informative): OpenTelemetry mapping, reference pseudo-code, key file
format, lineage edge vocabulary.
