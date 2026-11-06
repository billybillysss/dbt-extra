"""Fabric Warehouse gaps in SQLGlot 30.29.0, not inherited T-SQL coverage.

Sources: Microsoft Learn ISJSON, JSON_PATH_EXISTS and STRING_SPLIT pages
(view=fabric), linked in docs/reference/sql-functions/fabric.md.
"""

from dbt_extra.sql.functions.models import FunctionSpec as F


FUNCTIONS = (
    F("isjson", "isjson('{}')", "INT", 1, 2),
    F("json_path_exists", "json_path_exists('{}', '$.a')", "INT", 2, 2),
    F("string_split", "string_split('a,b', ',')", None, 2, 2, "generator"),
    F("json_modify", "json_modify('{}', '$.a', 2)", "NVARCHAR(MAX)", 3, 3),
    F("string_escape", "string_escape('abc', 'json')", "NVARCHAR(MAX)", 2, 2),
    F("difference", "difference('abc', 'abd')", "INT", 2, 2),
    F("quotename", "quotename('abc')", "NVARCHAR(258)", 1, 2),
    F("patindex", "patindex('%a%', 'abc')", None, 2, 2),
    F("bit_count", "bit_count(1)", "BIGINT", 1, 1),
    F("set_bit", "set_bit(1, 0, 0)", None, 2, 3),
    F("isnumeric", "isnumeric('123')", "INT", 1, 1),
    F("object_name", "object_name(1)", "NVARCHAR(128)", 1, 2, volatility="stable"),
    F("checksum", "checksum(id)", "INT", 1, None),
    F("checksum_agg", "checksum_agg(CAST(id AS INT))", "INT", 1, 1, "aggregate"),
)
