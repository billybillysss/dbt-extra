# Inspect and optimize SQL

dbt SQL is authoritative. Neither inspection nor optimization invokes dbt,
executes arbitrary templates, accesses a warehouse, estimates cost, or guarantees speedups.

## Inspect a table or selected columns

```bash
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --from orders
extra --project-dir examples/jaffle_shop inspect customer_revenue --columns revenue --view plan
extra --project-dir examples/jaffle_shop inspect customer_revenue --compile false
```

Inspection defaults to `--expand true --optimize true --compile true`. It follows statically
resolvable `ref` calls and explains the complete definition before applying the
requested projection. SQLGlot removes provably redundant joins and wrappers;
joins, filters, grouping, DISTINCT, set operations and multiplicity that affect
the selected rows remain, even when they require nonselected outputs internally.
The inspection rules also perform bounded Boolean normalization, guarded filter
pushdown and inner/cross-join simplification, and factor repeated deterministic
derived tables into shared CTEs. Subquery merging flattens redundant wrappers;
factoring common subqueries does not mean every subquery can be removed.

These extra structural rewrites deliberately skip unsupported query shapes.
Filters are not pushed across row limits, aggregates, window operations, set
operations or outer joins; join reordering also skips `OR` join predicates.
Common-subquery factoring skips scoped CTEs, limited/correlated queries,
order-sensitive aggregates and stored-self relation metadata. Volatile or unknown
functions retain the existing no-optimization guard. SQLGlot's full default
pipeline, including subquery unnesting and type-dependent canonicalization, is
not enabled. These are logical rewrites, not warehouse cost optimization.

Use `--optimize false` to retain the unsimplified explanation. This is more than
a list of value-lineage origins. `--from` retains selected upstream models as logical
relation inputs; other branches may still expand those shared ancestors.

`--compile true` resolves physical **relation names**, not arbitrary dbt Jinja or
compiled model SQL. Literal sources use their declared database/schema/identifier
(schema defaults to the source name; identifier defaults to the table name).
Source-level quoting is inherited, with table-level overrides. For example, the
Jaffle Shop customer source resolves to `main_raw.raw_customers`, not the logical
source name `jaffle_shop.customers`.

Dynamic source names and unexpanded models use resolved relation evidence from
`target/manifest.json` (or `--manifest PATH`). This preserves dbt's generated
schemas and aliases; a model's `+schema: raw` is **not** assumed to mean a physical
schema named `raw`. Manifest quoting and database qualifiers are retained. Changed
model SQL/naming configuration and conflicting literal source names are not
silently replaced by old manifest evidence. Unresolved references retain their
templates with a coverage warning. Only surviving relations are resolved after
optimization, so removed inputs do not generate resolution warnings.

Supply a current manifest for the intended target, for example from `dbt parse`.
extra does not execute profiles, environment expressions, naming macros, or dbt;
it cannot independently verify manifest target/freshness or database existence.
`--compile false` preserves `{{ source(...) }}`, `{{ ref(...) }}`, and `{{ this }}`.
The compile option is independent of expansion/optimization, also applies to
`--view plan`, and never changes authored files or the separate `optimize` command.

Inspection's `--expand true` also previews bounded static local macros, including
macros returning several columns. `--expand false` retains proven scalar calls;
unknown/multi-column output is not guessed. Literal arguments, local nested calls,
and bounded literal-list loops are supported, but dbt context, adapters, database
queries, environment access and arbitrary Jinja operations are not executed.
These previews never replace authored macro calls in source files.

Unknown schemas, unsupported templates, recursive SQL, package/artifact-only
resources, and history-sensitive/incremental definitions retain explicit
boundaries with reasons. Inspection is not a claim that expanded definitions
equal the data currently stored in persisted relations. Nothing is executed.

## Preview authored SQL changes

```bash
extra --project-dir examples/jaffle_shop optimize --select customer_revenue --preview
extra --project-dir examples/jaffle_shop optimize --select customer_revenue
```

Preview shows a diff of the actual source file and writes nothing. Applying the
command changes that same authored `.sql` file. Files under `target/compiled`
are not edited. `--dry-run` is an alias for `--preview`.

Literal leading `config`, static `ref` (including package/version arguments),
`source`, and supported relation-position `this` are reversibly masked, not
evaluated. Only a restricted SQLGlot rule set is used. Output names/order,
comments and SQL/Jinja round-trip checks must survive.

Opaque macros, dynamic `if`/`for` blocks, unsafe whitespace controls, volatile or
unknown functions, recursive queries and unsupported constructs are skipped
with a reason. dbt-extra does not infer uniqueness or remove joins from documentation.
Narrow positive equality-EXISTS filters can become set-membership filters, and
identical complementary UNION ALL scans can collapse while excluding NULL keys.
Guarded predicate pushdown, bounded Boolean normalization, inner/cross-join
simplification and repeated deterministic subquery factoring also apply to source
SQL. Other unsupported correlated shapes still skip. No `dbt compile` is required.
Existing compiled artifacts are never a rewrite input.

Supported scalar macros are validated by bounded static expansion. A guarded
source rule removes unused columns and grouped aggregates using expanded
dependencies, including identifiers hidden in macro arguments; exact macro calls
remain authored. Independent local constants and Boolean identities can simplify
even with macros, aggregates, windows or limits; macro-containing expressions and
scope boundaries are not moved. Arithmetic identities require exact type evidence:
`+ 0` stays for decimal/unknown inputs, and decimal constant arithmetic is not
folded merely because its value is unchanged. Reports explain retained arithmetic,
DISTINCT tuples, and movement boundaries. Other supported shapes can still receive formatting-only
changes, which are reported separately from real structural rewrites and binding
qualification. Structural rewrites require validated bindings and complete
schemas where needed, never assumed-complete documentation columns. See
[source optimizer safety](source-optimizer-safety.md) for schema evidence,
rewrite boundaries, fixed-point checks, conflict protection, and validation details.

## Enrich metadata

`extra enrich --preview` fills missing statically inferred column types and
unambiguous bare-column passthrough/rename descriptions. Transformed expressions
do not inherit descriptions as though their business meaning were unchanged.
Missing schema or Jinja evidence leaves properties unresolved. Authored values
are not overwritten. New model properties default to `_extra_properties.yml`
beside the model; configure a valid dbt property location if needed.

After review, run dbt's own parsing, tests and builds independently. Logical
equivalence checks, metadata inference, executed data tests and warehouse
performance measurements answer different questions.
