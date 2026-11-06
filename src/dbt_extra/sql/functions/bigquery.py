"""BigQuery Anonymous gaps; dependent result types remain unresolved."""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("error", "error('stop')", None, 1, 1, volatility="volatile"),
    F("date_bucket", "date_bucket(DATE '2026-01-01', INTERVAL 7 DAY)", "DATE", 2, 3),
    F("datetime_bucket", "datetime_bucket(DATETIME '2026-01-01 00:00:00', INTERVAL 1 HOUR)", "DATETIME", 2, 3),
    F("timestamp_bucket", "timestamp_bucket(TIMESTAMP '2026-01-01 00:00:00+00', INTERVAL 1 HOUR)", "TIMESTAMP", 2, 3),
    F("range_start", "range_start(RANGE(DATE '2026-01-01', DATE '2026-02-01'))", None, 1, 1),
    F("range_end", "range_end(RANGE(DATE '2026-01-01', DATE '2026-02-01'))", None, 1, 1),
    F("generate_range_array", "generate_range_array(RANGE(DATE '2020-01-01', DATE '2020-02-01'), INTERVAL 1 DAY)", None, 2, 3),
)
