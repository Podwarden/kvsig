# Releasing kvsig

Each implementation is released on its own tag pattern, so one can ship a
patch without the other:

| Package | Registry | Tag | Workflow |
|---|---|---|---|
| `kvsig` (Python, `python/`) | PyPI | `vX.Y.Z` | [`release.yml`](.github/workflows/release.yml) |
| `@kvsig/core` (TypeScript, `js/`) | npm | `js-vX.Y.Z` | [`release-js.yml`](.github/workflows/release-js.yml) |

The version numbers follow the spec draft revision in the minor (0.1.x for
draft 0.1) but move independently in the patch. The `v*` pattern does not
match `js-v*` tags, so a TypeScript release never starts the PyPI workflow.

## Python package

The Python package is published to PyPI by
[`.github/workflows/release.yml`](.github/workflows/release.yml) with
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): PyPI trusts a
short-lived OIDC token from this repository's workflow. No API token is stored
in GitHub or anywhere else.

## One-time setup (maintainers)

1. **GitHub environments.** In Settings, Environments, create:
   - `pypi`: add yourself (or the maintainers team) as a required reviewer, and
     under "Deployment branches and tags" allow only tags matching `v*`.
   - `testpypi`: no reviewer needed; any branch may deploy.
2. **PyPI trusted publisher.** On pypi.org, Your projects, Publishing, "Add a new
   pending publisher" (the project does not exist until the first upload):
   project name `kvsig`, owner `Podwarden`, repository `kvsig`, workflow
   `release.yml`, environment `pypi`.
3. **TestPyPI trusted publisher.** The same on test.pypi.org, with environment
   `testpypi`.
4. **Tag protection (recommended).** Settings, Rules, add a tag ruleset for `v*`
   that restricts creation and deletion to maintainers and blocks updates.

## Every release

1. Set the version in `python/src/kvsig/__init__.py` (`__version__`) and add a
   `## X.Y.Z (...)` section to `CHANGELOG.md`. Merge to `main`.
2. Optional dry run: Actions, `release`, "Run workflow" on `main`. It builds,
   tests the wheel, runs the conformance runner and publishes to TestPyPI.
   Check with `pip install -i https://test.pypi.org/simple/ kvsig==X.Y.Z`.
   TestPyPI never accepts the same version twice; a repeat run skips the
   upload.
3. Tag and push: `git tag -a vX.Y.Z -m "kvsig X.Y.Z" && git push origin vX.Y.Z`.
   The workflow checks that the tag equals `__version__`, builds, tests on
   Python 3.10 to 3.13, runs the conformance runner against the built wheel,
   then waits for approval of the `pypi` environment and publishes.
4. Create the GitHub release from the tag, with the CHANGELOG section as the
   notes and the `dist/` files from the workflow run attached.

A release that changes canonical bytes or ids for an existing spec label or
loose profile is not allowed; see
[Versioning and compatibility](SPEC.md#versioning-and-compatibility).

## TypeScript package (`@kvsig/core`)

Published to npm by [`.github/workflows/release-js.yml`](.github/workflows/release-js.yml)
with [trusted publishing](https://docs.npmjs.com/trusted-publishers): npm
trusts a short-lived OIDC token from this repository's workflow, no npm token
is stored in GitHub, and npm attaches a provenance attestation automatically.

### One-time setup (maintainers)

1. **npm organisation.** The `kvsig` organisation on npmjs.com owns the
   `@kvsig` scope. Enable two-factor authentication on every member account.
2. **GitHub environment.** In Settings, Environments, create `npm`: add the
   maintainers as required reviewers, and under "Deployment branches and tags"
   allow only tags matching `js-v*`.
3. **Bootstrap publish.** npm configures a trusted publisher on a package, so
   `@kvsig/core` must exist first. Publish 0.1.0 once by hand from a clean
   checkout of the release tag: `cd js && npm ci && npm test && npm publish
   --access public` (interactive login with 2FA, or a granular access token
   with bypass-2FA, read and write on `@kvsig`, deleted right after).
   Alternatively publish a `0.0.0-bootstrap` placeholder and deprecate it.
4. **Trusted publisher.** On npmjs.com, package `@kvsig/core`, Settings,
   "Trusted Publisher", GitHub Actions: organisation or user `Podwarden`,
   repository `kvsig`, workflow filename `release-js.yml`, environment `npm`.
   The fields are case-sensitive and not validated on save.
5. **Lock it down.** In the package's Settings, Publishing access, choose
   "Require two-factor authentication and disallow tokens". Trusted publishing
   keeps working. Delete any token used in step 3.
6. **Tag protection (recommended).** Add `js-v*` to the tag ruleset for `v*`.

### Every release

1. Set the version in `js/package.json` and `VERSION` in `js/src/index.ts`,
   run `npm install` in `js/` to update the lockfile, and add a
   `### @kvsig/core X.Y.Z (...)` section to `CHANGELOG.md`. Merge to `main`.
2. Optional dry run: Actions, `release-js`, "Run workflow" on `main`. It
   builds, tests on Node 18, 20 and 22, runs the conformance runner against the
   packed tarball and runs `npm publish --dry-run`.
3. Tag and push: `git tag -a js-vX.Y.Z -m "@kvsig/core X.Y.Z" && git push origin js-vX.Y.Z`.
   The workflow checks that the tag equals the package version, builds, tests,
   runs the conformance runner, waits for approval of the `npm` environment and
   publishes. A version that is already on npm is skipped, so a re-run is safe.
4. Check the attestation: `npm view @kvsig/core@X.Y.Z dist.attestations` or,
   in a consuming project, `npm audit signatures`.

An npm version can never be reused, and `npm unpublish` works only for 72
hours. The same compatibility rule as for Python applies: no release may change
canonical bytes or ids for an existing spec label or loose profile.
