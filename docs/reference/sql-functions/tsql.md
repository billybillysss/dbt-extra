# T-SQL function gaps

These 76 entries fill SQLGlot 30.29.0 recognition/semantic gaps, not native
function coverage. Sources: Microsoft Learn
[functions](https://learn.microsoft.com/en-us/sql/t-sql/functions/functions?view=sql-server-ver17),
[metadata](https://learn.microsoft.com/en-us/sql/t-sql/functions/metadata-functions-transact-sql?view=sql-server-ver17),
[security](https://learn.microsoft.com/en-us/sql/t-sql/functions/security-functions-transact-sql?view=sql-server-ver17),
[JSON](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-functions-transact-sql?view=sql-server-ver17).
Availability differs by SQL Server version; newer JSON and bit functions need
appropriate server versions. This catalog does not certify Synapse or Fabric.
See [contracts and enrichment examples](README.md).

`scalar` means one value per input row, `aggregate` one per group, and `generator`
a table/row-expansion boundary. `STRING_SPLIT` has one value column with two
arguments; a literal third argument `1` adds a BIGINT ordinal column. An unknown
flag does not establish output arity. Its value type depends on its input string;
no TVF output schema is guessed for YAML inference.

Unresolved types include input-dependent types and `sql_variant`, whose concrete
type is not established offline. `stable` means catalog/session/environment
dependent; `volatile` may change during execution. All local entries remain
error/evaluation rewrite barriers, including immutable ones. SQLGlot-rendered type
spellings, nullability and runtime success are separate concerns.

Implementation and executable argument examples:
[catalog](../../../src/dbt_extra/sql/functions/tsql.py),
[tests](../../../tests/sql/functions/test_tsql.py).

| Function | Kind | Return type policy | Volatility |
| --- | --- | --- | --- |
| `isjson` | scalar | `INT` | immutable |
| `json_path_exists` | scalar | `INT` | immutable |
| `json_modify` | scalar | `NVARCHAR(MAX)` | immutable |
| `string_escape` | scalar | `NVARCHAR(MAX)` | immutable |
| `string_split` | generator | unresolved / input-dependent | immutable |
| `decompress` | scalar | `VARBINARY(MAX)` | immutable |
| `difference` | scalar | `INT` | immutable |
| `nchar` | scalar | unresolved / input-dependent | immutable |
| `quotename` | scalar | `NVARCHAR(258)` | immutable |
| `patindex` | scalar | unresolved / input-dependent | immutable |
| `formatmessage` | scalar | `NVARCHAR(2048)` | stable |
| `set_bit` | scalar | unresolved / input-dependent | immutable |
| `bit_count` | scalar | `BIGINT` | immutable |
| `left_shift` | scalar | unresolved / input-dependent | immutable |
| `right_shift` | scalar | unresolved / input-dependent | immutable |
| `datetime2fromparts` | scalar | unresolved / input-dependent | immutable |
| `datetimeoffsetfromparts` | scalar | unresolved / input-dependent | immutable |
| `smalldatetimefromparts` | scalar | `SMALLDATETIME` | immutable |
| `date_bucket` | scalar | unresolved / input-dependent | immutable |
| `isdate` | scalar | `INT` | stable |
| `isnumeric` | scalar | `INT` | immutable |
| `ident_current` | scalar | `DECIMAL(38,0)` | volatile |
| `ident_incr` | scalar | `DECIMAL(38,0)` | stable |
| `ident_seed` | scalar | `DECIMAL(38,0)` | stable |
| `scope_identity` | scalar | `DECIMAL(38,0)` | volatile |
| `xact_state` | scalar | `SMALLINT` | volatile |
| `error_number` | scalar | `INT` | volatile |
| `error_severity` | scalar | `INT` | volatile |
| `error_state` | scalar | `INT` | volatile |
| `error_procedure` | scalar | `NVARCHAR(128)` | volatile |
| `error_line` | scalar | `INT` | volatile |
| `error_message` | scalar | `NVARCHAR(4000)` | volatile |
| `object_name` | scalar | `NVARCHAR(128)` | stable |
| `object_schema_name` | scalar | `NVARCHAR(128)` | stable |
| `objectproperty` | scalar | `INT` | stable |
| `objectpropertyex` | scalar | unresolved / input-dependent | stable |
| `col_length` | scalar | `SMALLINT` | stable |
| `col_name` | scalar | `NVARCHAR(128)` | stable |
| `columnproperty` | scalar | `INT` | stable |
| `databasepropertyex` | scalar | unresolved / input-dependent | stable |
| `db_id` | scalar | `INT` | stable |
| `db_name` | scalar | `NVARCHAR(128)` | stable |
| `file_id` | scalar | `SMALLINT` | stable |
| `file_idex` | scalar | `INT` | stable |
| `file_name` | scalar | `NVARCHAR(128)` | stable |
| `filegroup_id` | scalar | `INT` | stable |
| `filegroup_name` | scalar | `NVARCHAR(128)` | stable |
| `filegroupproperty` | scalar | `INT` | stable |
| `fileproperty` | scalar | `INT` | stable |
| `index_col` | scalar | `NVARCHAR(128)` | stable |
| `indexproperty` | scalar | `INT` | stable |
| `schema_id` | scalar | `INT` | stable |
| `serverproperty` | scalar | unresolved / input-dependent | stable |
| `type_id` | scalar | `INT` | stable |
| `type_name` | scalar | `NVARCHAR(128)` | stable |
| `typeproperty` | scalar | `INT` | stable |
| `app_name` | scalar | `NVARCHAR(128)` | stable |
| `host_id` | scalar | `VARCHAR(10)` | stable |
| `host_name` | scalar | `NVARCHAR(128)` | stable |
| `original_login` | scalar | `NVARCHAR(128)` | stable |
| `suser_id` | scalar | `INT` | stable |
| `suser_sid` | scalar | `VARBINARY(85)` | stable |
| `user_id` | scalar | `INT` | stable |
| `user_name` | scalar | `NVARCHAR(128)` | stable |
| `is_member` | scalar | `INT` | stable |
| `is_rolemember` | scalar | `INT` | stable |
| `is_srvrolemember` | scalar | `INT` | stable |
| `has_perms_by_name` | scalar | `INT` | stable |
| `permissions` | scalar | `INT` | stable |
| `session_context` | scalar | unresolved / input-dependent | volatile |
| `context_info` | scalar | `VARBINARY(128)` | volatile |
| `connectionproperty` | scalar | unresolved / input-dependent | stable |
| `cursor_status` | scalar | `SMALLINT` | volatile |
| `checksum` | scalar | `INT` | immutable |
| `binary_checksum` | scalar | `INT` | immutable |
| `checksum_agg` | aggregate | `INT` | immutable |
