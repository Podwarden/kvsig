# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's private vulnerability reporting:
[open a draft security advisory](https://github.com/Podwarden/kvsig/security/advisories/new)
(the **Security** tab of the repository, then **Report a vulnerability**). Only
the maintainers can see it.

Please include what an attacker can learn or do, the inputs that show it, and
the implementation and version affected (or the spec section, for a flaw in the
specification itself).

We acknowledge the report, confirm or rule out the problem, and agree a
disclosure date with you. With your permission, the advisory credits you.

## Scope

In scope: the specification, the reference implementations in this repository
and the test vectors. Examples: an input that makes canonicalisation super-linear
or crash, ids that leak content without the key, collisions between inputs that
the spec says must differ.

Note that a holder of the deployment key can confirm a guessed message by
computing its id. That is a documented property of keyed ids, not a
vulnerability.
