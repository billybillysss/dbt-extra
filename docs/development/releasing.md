# Release checklist

dbt-extra `0.1.0` is the initial private preview.
The [release-candidate workflow](https://github.com/billybillysss/dbt-extra/blob/HEAD/.github/workflows/release.yml)
is manual, runs validation, builds distributions and retains them as GitHub
artifacts. It does **not** publish to PyPI, react to tags or request OIDC tokens.
Normal pushes and pull requests run [CI](testing.md).

Do not make the repository public, create a public release, upload packages or
enable a publishing workflow without separate maintainer approval.

## Verify the private candidate

- Review [compatibility](../compatibility.md), dependencies, security issues and
  [migration instructions](../guides/migrating-from-slbt.md).
- Set the version in `src/dbt_extra/__init__.py`, update versioned examples,
  and refresh `uv.lock` with `uv lock` when package metadata changes.
- Preserve MIT licensing and the bundled seed Apache 2.0 attribution.
- Run the full test suite, executable README workflows and both native dbt
  fixtures; inspect CI results for every declared platform/Python target.
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

## Future public release — separate approval required

1. Obtain maintainer approval for public visibility and separately for PyPI
   publication; do not automatically change either after verification.
2. Confirm that `dbt-extra` is available to the intended PyPI owner. No package
   name reservation or publisher configuration is implied by this repository.
3. Verify an unused version and configure a narrowly scoped trusted publisher
   with a protected release environment before adding any publishing automation.
4. Require the approved tag to match the installed distribution version, run CI
   and distribution checks, and inspect the exact artifacts before uploading.
5. After approved publication, verify PyPI artifacts and install instructions,
   create accurate release notes, then update private-preview notices and add a
   package badge only when the matching release actually exists.

Record future changes under Unreleased and verify release notes against the
approved source revision and uploaded artifacts.
