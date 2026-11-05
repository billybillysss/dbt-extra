# Contributing to dbt-extra

extra is an offline dbt transformation companion. Changes should keep authored SQL,
business metadata and review outputs inspectable, with dbt responsible for
database execution. Read the [concepts](docs/concepts.md) and
[architecture](docs/development/architecture.md) first.

## Set up and test

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
uv sync --locked
uv run pytest
uv run extra --project-dir examples/jaffle_shop validate
uv run extra --project-dir examples/jaffle_shop export --preview
uv run extra --project-dir examples/jaffle_shop optimize --preview
uv build
```

The suite includes documentation/link checks and DuckDB result-equivalence tests.
See [testing](docs/development/testing.md) for the executable dbt checks and
clean-install package smoke tests. Do not run write-mode optimization against
bundled teaching inputs just to test a change; copy them to a temporary project.

## Propose a change

- Useful first contributions include a small redacted dialect/macro reproduction,
  a regression test, or a clearer walkthrough. Check existing issues first; if no
  suitable issue exists, describe your proposed scope before a substantial change.
- For significant behavior/schema changes, open an issue describing the use case
  before building an incompatible API. Small documentation fixes can go straight
  to a pull request.
- Keep changes focused. Include a minimal reproduction and regression test for
  bugs; include expected inputs/outputs for new features.
- Preserve output-column order, declared metadata, validation-before-write
  behavior, unchanged-file bytes and managed-path protections.
- Prefer explicit errors to guessed schema information. No warehouse access may
   be introduced into offline analysis commands without an explicit design change.
- Update relevant docs and [CHANGELOG](CHANGELOG.md) for user-visible changes.
  Follow [compatibility](docs/compatibility.md) for schema/API changes.
- Write block-style YAML and plain GitHub-readable Markdown. Link reference docs
  rather than duplicating their full content in the README.
- Do not commit credentials, local databases, dbt logs/targets or generated demo
  dbt output. The example workbook and seed data are intentional fixtures.

In your pull request, state what changed, why, commands tested, limitations and
any migration required. If AI helped, review its output and verify business
assumptions yourself; do not submit untested generated logic as verified behavior.

## Report bugs and security issues

For ordinary bugs, include dbt-extra/Python/OS versions, the exact command, a minimal
redacted project and expected versus actual behavior. Never post private
catalogs, credentials or production data. Use the [security policy](SECURITY.md)
for potential vulnerabilities rather than disclosing exploit details publicly.
For source checkouts, also include `git rev-parse HEAD`; unreleased code can share
the published package's version string. The GitHub issue forms collect these details.

## License

Contributions to dbt-extra code and documentation are under the [MIT license](LICENSE).
Preserve third-party notices and the separate Jaffle Shop seed attribution.
