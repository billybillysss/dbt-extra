# Redshift SQL functions

## dbt-extra local function gaps

These calls fill SQLGlot 30.29.0 `Anonymous` gaps, independently of
PostgreSQL parser ancestry. They retain authored AST/spelling and `may_raise=True`
rewrite barriers. Fixed type families do not establish nullability or equivalence.

Additional [JSON](https://docs.aws.amazon.com/redshift/latest/dg/json-functions.html)
and [SUPER operations](https://docs.aws.amazon.com/redshift/latest/dg/operators-functions.html)
use Redshift contracts, not PostgreSQL JSONB rules. Text extraction/serialization
returns VARCHAR; binary serialization returns VARBYTE; SUPER array transforms
retain SUPER. Native JSON_PARSE inference is separately corrected from JSON to
SUPER, and native SUM/AVG widening follows Redshift's documented integer/decimal rules.

| Function | Kind | Return policy | Volatility |
| --- | --- | --- | --- |
| `fnv_hash` | scalar | `BIGINT` | immutable |
| `can_json_parse` | scalar | `BOOLEAN` | immutable |
| `json_typeof` | scalar | `VARCHAR` | immutable |
| `pg_last_query_id` | scalar | `INTEGER` | volatile |
| `json_array_length` | scalar | `INTEGER` | immutable |
| `is_valid_json` | scalar | `BOOLEAN` | immutable |
| `is_valid_json_array` | scalar | `BOOLEAN` | immutable |
| `json_extract_array_element_text` | scalar | `VARCHAR` | immutable |
| `json_serialize` | scalar | `VARCHAR` | immutable |
| `json_serialize_to_varbyte` | scalar | `VARBYTE` | immutable |
| `json_size` | scalar | `INTEGER` | immutable |
| `is_object` | scalar | `BOOLEAN` | immutable |
| `is_boolean` | scalar | `BOOLEAN` | immutable |
| `is_integer` | scalar | `BOOLEAN` | immutable |
| `is_float` | scalar | `BOOLEAN` | immutable |
| `is_decimal` | scalar | `BOOLEAN` | immutable |
| `is_varchar` | scalar | `BOOLEAN` | immutable |
| `get_array_length` | scalar | `INTEGER` | immutable |
| `array_flatten` | scalar | `SUPER` | immutable |
| `subarray` | scalar | `SUPER` | immutable |

Signatures and official sources:

- [FNV_HASH](https://docs.aws.amazon.com/redshift/latest/dg/r_FNV_HASH.html):
  one value plus an optional seed (one or two arguments); returns BIGINT.
- [CAN_JSON_PARSE](https://docs.aws.amazon.com/redshift/latest/dg/CAN_JSON_PARSE.html):
  one argument; returns BOOLEAN. Even a validation function gains no rewrite permission.
- [JSON_TYPEOF](https://docs.aws.amazon.com/redshift/latest/dg/r_json_typeof.html):
  one SUPER expression; returns the type name as VARCHAR, not the type of its input.
- [PG_LAST_QUERY_ID](https://docs.aws.amazon.com/redshift/latest/dg/PG_LAST_QUERY_ID.html):
  no arguments; session query-history INTEGER, conservatively volatile.

Native `SOUNDEX` and `JSON_EXTRACT_PATH_TEXT` inference gaps are not replaced.
No PostgreSQL catalog inheritance or Redshift execution checks are claimed.
See the [audit](audit.md), [catalog](../../../src/dbt_extra/sql/functions/redshift.py)
and [per-function regressions](../../../tests/sql/functions/test_redshift.py).

<!-- BEGIN GENERATED FUNCTION INVENTORY -->
## Function implementation reference

All function names and implementation symbols are in the single
[function implementation matrix](README.md#function-implementation-matrix).

Source scope: Amazon Redshift SQL function category indexes (dated snapshot).
See the [official-source snapshot](function_sources.json) for all source URLs (collected 2026-11-05).
<!-- END GENERATED FUNCTION INVENTORY -->
