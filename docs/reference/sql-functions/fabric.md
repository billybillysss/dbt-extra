# Fabric Warehouse SQL functions

## dbt-extra local function gaps

These entries fill SQLGlot 30.29.0 Anonymous-function gaps for Fabric
Warehouse and its SQL analytics endpoint. They do not inherit the T-SQL catalog
or certify SQL database in Fabric. Sources: Microsoft Learn
[ISJSON](https://learn.microsoft.com/en-us/sql/t-sql/functions/isjson-transact-sql?view=fabric),
[JSON_PATH_EXISTS](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-path-exists-transact-sql?view=fabric),
[STRING_SPLIT](https://learn.microsoft.com/en-us/sql/t-sql/functions/string-split-transact-sql?view=fabric).

`ISJSON` accepts one or two arguments; `JSON_PATH_EXISTS` accepts two. `STRING_SPLIT`
is a two-argument table source with one value column and zero or more rows. Its
value type depends on its input; no TVF schema or YAML type is guessed. The third
ordinal argument is deliberately unregistered pending Warehouse-specific evidence.
`XACT_STATE` and `DATALENGTH` are likewise not assumed available from T-SQL.
Native `JSON_VALUE` remains outside this Anonymous-only catalog, even when its
type cannot be inferred. All local calls retain error/evaluation rewrite barriers.

See [contracts and enrichment examples](README.md), the
[catalog](../../../src/dbt_extra/sql/functions/fabric.py), and
[tests](../../../tests/sql/functions/test_fabric.py). Verification is offline;
these are not warehouse execution checks.

Additional JSON/string, bit, numeric and checksum registrations require each
Microsoft function page's explicit **Warehouse in Microsoft Fabric** applicability,
including [JSON_MODIFY](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-modify-transact-sql),
[BIT_COUNT](https://learn.microsoft.com/en-us/sql/t-sql/functions/bit-count-transact-sql)
and [CHECKSUM_AGG](https://learn.microsoft.com/en-us/sql/t-sql/functions/checksum-agg-transact-sql).
NVARCHAR results describe expression types, not permission to persist NVARCHAR
columns in Warehouse. `PATINDEX` and `SET_BIT` retain input-dependent results.
`OBJECT_NAME` is context-sensitive. `DATALENGTH`, `COL_LENGTH`, ordinal STRING_SPLIT
and DATE_BUCKET's special datepart grammar remain outside this expansion.

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `isjson` | scalar | `INT` | immutable |
| `json_path_exists` | scalar | `INT` | immutable |
| `string_split` | generator | unresolved / input-dependent | immutable |
| `json_modify` | scalar | `NVARCHAR(MAX)` | immutable |
| `string_escape` | scalar | `NVARCHAR(MAX)` | immutable |
| `difference` | scalar | `INT` | immutable |
| `quotename` | scalar | `NVARCHAR(258)` | immutable |
| `patindex` | scalar | unresolved / input-dependent | immutable |
| `bit_count` | scalar | `BIGINT` | immutable |
| `set_bit` | scalar | unresolved / input-dependent | immutable |
| `isnumeric` | scalar | `INT` | immutable |
| `object_name` | scalar | `NVARCHAR(128)` | stable |
| `checksum` | scalar | `INT` | immutable |
| `checksum_agg` | aggregate | `INT` | immutable |

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Fabric Warehouse/SQL analytics endpoint applies-to articles (not Fabric SQL Database).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
