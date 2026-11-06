"""Dialect-local function recognition, output shapes and rewrite barriers."""

from dbt_extra.sql.functions.models import FunctionShape, FunctionSpec
from dbt_extra.sql.functions.registry import (
    ATHENA, BIGQUERY, DATABRICKS, DUCKDB, FABRIC, POSTGRES, REDSHIFT, SNOWFLAKE,
    SPARK, TRINO, TSQL, CATALOG, dialect_key, function_barrier,
    function_shape, function_spec, has_generators, recognize_functions,
)
