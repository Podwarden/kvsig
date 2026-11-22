# Test vectors

One directory per spec version (`v1/`), one sub-directory per dialect, plus a
`manifest.json` listing every file with its SHA-256. The format is defined in
[decision 0004](../docs/decisions/0004-test-vectors.md). The runner that uses
them is in [conformance/](../conformance/README.md).

The set is versioned: `manifest.json` names the spec label (`kvsig/1`), the
loose profile the expected loose values use (`loose/1`) and the vector set
revision (`0.1`, released with the reference library 0.1.0). From revision 0.1
on, the expected values of an existing vector never change; a change to the
canonical bytes or ids needs a new spec label or loose profile, with its own
vector set. A later revision may only add vectors that pin what the rules
already give. See
[Versioning and compatibility](../SPEC.md#versioning-and-compatibility).

All inputs are synthetic. Do not add captured traffic.

## Do not edit the JSON files by hand

The files under `v1/` are generated from `tools/cases.py`, `tools/cases_hand.py`
and `tools/cases_reply.py` by the reference implementation:

```
python vectors/tools/generate.py           # rewrite vectors/v1 and the manifest
python vectors/tools/generate.py --check   # fail if the files differ from the generator
python vectors/tools/xcheck.py             # independent re-derivation of every id
```

Both tools need `cbor2`. The cross-check does not import kvsig. CI runs all
three, and fails when a file under `v1/` changes without the manifest.
