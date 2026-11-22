# Content-Derived Conversation Identifiers for LLM Chat APIs (kvsig/1)

**Status: draft 0.1 of `kvsig/1`.** The rules are not complete as prose yet,
but the ids they produce are pinned: see
[Versioning and compatibility](#versioning-and-compatibility). Version 1.0 of
the reference library marks the freeze of the text.

Until each section below is written, the normative rules are the decisions in
[docs/decisions](docs/decisions/) (0001 to 0005) as of this revision, and the
test vectors in [vectors/v1](vectors/). Where the two disagree, the vectors win
and the disagreement is a bug in the text.

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
12. **Versioning.** Written: see [Versioning and compatibility](#versioning-and-compatibility).
13. **Test vectors.** Format and manifest (draft: [decision 0004](docs/decisions/0004-test-vectors.md)).
14. **Registries.** Dialects, part types, labels, loose profiles.
15. **Prior art and acknowledgements.**

Annexes (informative): OpenTelemetry mapping, reference pseudo-code, key file
format, lineage edge vocabulary.

## Versioning and compatibility

This section applies from draft 0.1 (reference library 0.1.0) on.

There are three version numbers, and they move independently:

| Name | Example | What it versions |
|---|---|---|
| Spec label | `kvsig/1` | Canonical form, canonical bytes, id derivation. It is hashed into every id. |
| Loose profile | `loose/1`, `loose/2` | The loose table. Its name is hashed into every loose id. |
| Draft revision and library version | draft 0.1, `kvsig` 0.1.0 | The text, the vector set revision and an implementation. |

**What is stable.** For the spec label `kvsig/1` and the loose profile
`loose/1`, the canonical bytes and every id given by the vectors in
`vectors/v1` (vector set revision 0.1, 232 vectors, listed in
`vectors/v1/manifest.json` with their hashes) are fixed. An implementation
that passes them today keeps passing them. Specifically:

1. No release changes the canonical bytes or the ids of any input under an
   existing spec label and loose profile. A change that would, including one
   that comes out of accepting a proposed decision, is published under a new
   label (`kvsig/2`) or a new loose profile (`loose/3`), with its own vector
   set. The old label or profile stays available by name.
2. The expected values of an existing vector never change. New vectors may be
   added to `vectors/v1`, in a new vector set revision, only when they pin
   what the current rules already give.
3. A reference library that disagrees with a vector has a bug, and the fix
   is a patch release.
4. Changing the library's *default* profile (for example to `loose/2`) is a
   breaking change: before 1.0 it happens only in a minor release (0.x to
   0.x+1), with a "Changed defaults" entry in the CHANGELOG.

**What is not stable yet.**

- `loose/2` (decision 0005, proposed) ships in the reference library as
  `LOOSE_V2` but is experimental. It has no vector set, and its ids may change
  until the decision is accepted and a `loose/2` vector set is published.
- Dialects, part types and request fields that no vector covers. Their
  behaviour is the reference library's, and a later vector may pin it.
- The Python API outside the ids it returns. It follows SemVer from 0.1.0 with
  the 0.x rule: a minor release may change the API, a patch release does not.

After the freeze (1.0) the vectors of a frozen spec version are immutable.
