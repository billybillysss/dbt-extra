# Release checklist

dbt-extra `0.1.0` is the initial private preview.
The [release workflow](https://github.com/billybillysss/dbt-extra/blob/HEAD/.github/workflows/release.yml)
runs on `v*` tags or manual dispatch. It runs CI, builds distributions, checks
package metadata and publishes to PyPI using OIDC trusted publishing.
Normal pushes and pull requests run [CI](testing.md).

Do not make the repository public, create a public release or trigger publication
without maintainer approval. Enabling this workflow does not establish that any
package has been published.

## Verify the private candidate

- Review [compatibility](../compatibility.md), dependencies, security issues and
  release notes.
- Set the version in `src/dbt_extra/__init__.py`, update versioned examples,
  and refresh `uv.lock` with `uv lock` when package metadata changes.
- Preserve MIT licensing and the bundled seed Apache 2.0 attribution.
- Run the full test suite, executable README workflows and the native dbt
  fixture; inspect CI results for every declared platform/Python target.
- Review actual SQL/property diffs and known limitations. No warehouse speedup,
  universal adapter compatibility or crash-safe multi-file write claims.
- Confirm approved SVG assets and image references, including the supplied
  Modular joint icon and its light/dark palette.

## Build and inspect

```sh
uv sync --locked
uv run pytest
uv build --no-sources
uvx twine check dist/*
```

Use a clean build directory. Run [distribution checks](testing.md#distribution-checks)
against **both** isolated wheel and source-archive installations, including the
actual `extra` console entry point and `python -m dbt_extra`. Check package name,
version, license metadata, documentation and example inclusion. Editable-source
tests alone do not establish installability.

## Publish an approved release

1. Obtain maintainer approval for public visibility and separately for PyPI
   publication; do not automatically change either after verification.
2. Confirm that `dbt-extra` is available to the intended PyPI owner. No package
   name reservation or publisher configuration is implied by this repository.
3. Verify an unused version and configure a PyPI trusted publisher for GitHub
   owner `billybillysss`, repository `dbt-extra` and workflow `release.yml`.
   The workflow does not declare a GitHub environment; leave that field unset
   in PyPI unless you also add a matching protected environment to the publish job.
   Only the publish job requests `id-token: write`; no PyPI API token is needed.
4. Run CI and distribution checks, inspect the artifacts locally, then push the
   approved `v<version>` tag (for example, `v0.1.0`). The workflow rejects tags
   that do not match the installed `dbt-extra` version. Manual dispatch also
   publishes, but skips the tag check when run against a branch; choose the
   intended revision carefully. Do not rerun publication for an existing PyPI version.
5. After approved publication, verify PyPI artifacts and install instructions,
   create accurate release notes, then update private-preview notices and add a
   package badge only when the matching release actually exists.

Record future changes under Unreleased and verify release notes against the
approved source revision and uploaded artifacts.
