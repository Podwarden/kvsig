# Releasing kvsig

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
