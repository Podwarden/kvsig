# Contributing to kvsig

Thank you for helping. Issues and pull requests are welcome on the code, the
test vectors and the specification text.

## Developer Certificate of Origin

We use the [Developer Certificate of Origin](https://developercertificate.org/)
(DCO), not a CLA. Every commit must carry a sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

`git commit -s` adds it. By signing off you certify that you wrote the change,
or have the right to submit it, under the licence of the files it touches
(Apache-2.0 for code and vectors, CC BY 4.0 for the specification text).

## Changes to the specification

- A change that alters canonical bytes or ids is **normative**. Open an issue
  first. Normative changes stay open for comment for at least 14 days before
  they merge, and each one is recorded in [docs/decisions](docs/decisions/).
- Every normative change comes with test vectors that pin the new behaviour.
- Editorial changes (wording, examples, typos) can go straight to a pull
  request.

## Changes to an implementation

- An implementation change must not alter the output for any existing test
  vector unless the spec changed with it. CI checks this.
- Keep the reference implementation free of third-party runtime dependencies.
