# 0001. Canonical encoding: a restricted deterministic CBOR profile

Status: accepted (2026-11-20). Normative for `kvsig/1`.

## Question

Which byte encoding is the HMAC computed over? The candidates were JSON with
the RFC 8785 (JCS) rules, deterministic CBOR (RFC 8949 section 4.2.1), and a
custom length-prefixed format.

## What comparable projects chose

| Project | Encoding | Purpose |
|---|---|---|
| vLLM prefix cache, `sha256_cbor` | `cbor2.dumps(..., canonical=True)` | Block hashes that are "reproducible, cross-language compatible" ([docs](https://docs.vllm.ai/en/latest/design/prefix_caching.html)) |
| llm-d kv-cache indexer | FNV-64a over a CBOR tuple | Re-deriving engine block keys outside the engine ([architecture](https://github.com/llm-d/llm-d-kv-cache/blob/main/docs/architecture.md)) |
| IPLD | DAG-CBOR (and DAG-JSON) | Content ids ([dag-cbor](https://ipld.io/docs/codecs/known/dag-cbor/)) |
| Matrix | Canonical JSON, integers only, no floats | Event hashes and signatures ([spec](https://spec.matrix.org/latest/appendices/#canonical-json)) |
| W3C Data Integrity, `eddsa-jcs-2022` | JCS | Signatures ([spec](https://www.w3.org/TR/vc-data-integrity/)) |
| DSSE (Sigstore, in-toto) | No canonicalisation: length-prefixed framing over raw bytes | Signatures ([protocol](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md)) |

The two LLM-infrastructure projects that hash structured data across
languages both chose CBOR.

## Decision

Canonical bytes are CBOR (RFC 8949) restricted to this profile:

1. **Types allowed:** unsigned and negative integers (major types 0 and 1),
   byte strings (2), text strings (3), arrays (4), maps (5), and the simple
   values `false` and `true`. **Not allowed:** floats, tags, `null`,
   `undefined`, other simple values, indefinite lengths.
2. **Preferred serialisation** (RFC 8949 section 4.2.1): every integer and
   length in its shortest form.
3. **Maps** have text-string keys only, with no duplicates, sorted by the
   bytewise order of each key's encoding (the section 4.2.1 rule).
4. **Text strings** are valid UTF-8. Before encoding, an implementation
   replaces every lone UTF-16 surrogate with U+FFFD. A well-formed surrogate
   pair is the single code point it stands for. No Unicode normalisation is
   applied.
5. **JSON values that the canonical form keeps** (tool-call arguments, tool
   schemas, unknown parts) are not mapped into CBOR. They are carried as a text
   string holding their *canonical JSON text* (see
   [0002](0002-draft-canonical-rules.md)). This keeps client member order in the
   exact profile and keeps floats out of CBOR.

## Why

- **No escaping, no number formatting in the outer structure.** Every
  string is length-prefixed, and the canonical form has no floats. JCS's
  hardest parts (UTF-16 key sorting, ES6 number printing, surrogate errors) do
  not arise outside JSON values, which are handled by a narrow rule.
- **It is an RFC, and the profile is small.** A conforming encoder is about 60
  lines in any language, and existing deterministic-CBOR libraries produce the
  same bytes for this subset.
- **It lines up with the engines.** vLLM's `sha256_cbor` and llm-d already
  hash CBOR, so a stack that adopts kvsig needs no second canonical format.

## Cost, and how we pay it

Vectors are not human-diffable as raw bytes. Every vector therefore carries the
canonical form twice: the normative bytes (base64) and a readable JSON
rendering of the same structure. A difference shows up in the JSON first.

## Reverses

The original LM Warden implementation hashed sorted-key JSON. That encoding is
not carried into `kvsig/1`; ids from it are not comparable with kvsig ids.
