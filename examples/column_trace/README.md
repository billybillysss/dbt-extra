# Column tracing example

This project supports the [three-layer inspection walkthrough](../../README.md#trace-a-column-through-multiple-dbt-layers).
It contains model definitions and literal source declarations, not source data
or a database connection profile. Inspection needs neither dbt nor a warehouse.

From the repository root after `uv sync --locked`:

```bash
uv run extra --project-dir examples/column_trace inspect customer_profile --columns customer_name
uv run extra --project-dir examples/column_trace inspect customer_profile --columns customer_name --optimize false
```

`customer_name` follows `customer_profile → customer_details → stg_customers`
to `TRIM(first_name)` on `raw.customers`. The order flag depends on `raw.orders`.
Inspection expands the model definitions and selects the requested output, but
retains the order join and any intermediate expressions it cannot safely remove.
Coverage comments describe these boundaries. Neither command changes files or
executes the generated SQL.
