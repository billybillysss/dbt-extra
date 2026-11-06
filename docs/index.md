# dbt-extra documentation

**Understand, optimize, and review dbt SQL—without running dbt.**

dbt-extra is a Python library and CLI for tracing column logic, optimizing supported
SQL, and reviewing or editing SQL and metadata in Excel or CSV. Preview changes to
the original SQL and YAML; dbt files remain the source of truth. No initialization
or warehouse connection is required, and arbitrary Jinja is never executed.

## Start here

- [Getting started](getting-started.md): install, inspect a column and export a review.
- [Five-step demo](guides/five-step-demo.md): three models, readable SQL, an optimizer
  diff and an Excel-to-YAML review, all in a temporary copy.
- [Concepts and boundaries](concepts.md): source ownership, analysis and execution.
- [Native Jaffle Shop](../examples/jaffle_shop/README.md): the current end-to-end example.

## Workflows

- [Integrate with an existing dbt project](guides/existing-dbt-project.md)
- [Review and import Excel/CSV catalogs](guides/catalog-round-trip.md)
- [Inspect and optimize SQL](guides/inspection-and-optimization.md)
- [Fill missing metadata](guides/metadata-enrichment.md)
- [Authored-SQL optimizer safety](guides/source-optimizer-safety.md)
- [Partial optimization, outcomes and static templates](guides/partial-optimization.md)
- [Production adoption checklist](guides/production-workflow.md)

## Reference

- [CLI](reference/cli.md): all commands, options, selectors and exit statuses
- [Project configuration](reference/configuration.md)
- [Python API](reference/python-api.md)
- [SQL functions: implementations and types](reference/sql-functions/README.md)
- [Review tables and JSON](reference/catalogs.md)
- [Compatibility and versioning](compatibility.md)
- [Troubleshooting](troubleshooting.md)

## Maintain the project

- [Contributing](../CONTRIBUTING.md)
- [Architecture](development/architecture.md)
- [Testing](development/testing.md)
- [Logo and icons](logo.md)
- [Security](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
