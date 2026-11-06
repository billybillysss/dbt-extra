# dbt-extra documentation

dbt-extra reviews and inspects native dbt projects offline and proposes edits to
their SQL and YAML. dbt files remain the source of truth.

## Start here

- [Getting started](getting-started.md): install, inspect a column and export a review.
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
- [Releasing](development/releasing.md)
- [Logo and icons](logo.md)
- [Security](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
