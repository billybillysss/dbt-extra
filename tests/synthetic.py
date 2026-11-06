"""Generated offline dbt fixtures. No original project, profile or warehouse needed."""

import csv

from sqlglot import exp

from tests.helpers import put


RELATIONS = {
    "raw_events": ("id INTEGER, entity_id INTEGER, event_time TIMESTAMP, unused INTEGER, a INTEGER, b INTEGER, c INTEGER", [
        (1, 1, "2025-01-01 10:00:00", 9, 1, 2, 3),  # inclusive lower bound
        (2, 1, "2025-01-02 09:00:00", None, 2, 3, 4),
        (3, 1, "2025-01-02 10:00:00", 8, 3, 4, 5),  # exclusive upper bound
        (4, 2, "2025-01-02 09:00:00", 7, 4, 5, 6),
        (5, 1, "2025-01-01 09:59:59", 6, 5, 6, 7),
        (6, 1, "2025-01-02 08:00:00", 5, 6, 7, 8),
    ]),
    "raw_requests": ("request_id INTEGER, entity_id INTEGER, request_time TIMESTAMP", [
        (1, 1, "2025-01-02 10:00:00"), (2, 2, "2025-01-02 10:00:00"),
        (3, 3, "2025-01-02 10:00:00"), (4, 1, "2025-01-01 10:00:00"),
    ]),
    "raw_findings": ("finding_id INTEGER, event_id INTEGER, known_at TIMESTAMP, qualifies BOOLEAN", [
        (1, 1, "2025-01-02 09:00:00", True), (2, 1, "2025-01-02 09:30:00", True),
        (3, 2, "2025-01-02 09:59:59", True), (4, 3, "2025-01-02 09:00:00", True),
        (5, 4, "2025-01-02 10:00:00", True),  # evidence exactly at request is too late
        (6, 5, "2025-01-02 09:00:00", True), (7, 6, "2025-01-02 09:00:00", False),
    ]),
}


def synthetic_project(root, *, repeats=4):
    put(root, "dbt_project.yml", "name: synthetic\nversion: '1.0'\nprofile: synthetic\nmodel-paths: [models]\nseed-paths: [seeds]\n")
    put(root, "extra_project.yaml", "version: 2\nanalysis:\n  dialect: duckdb\n")
    put(root, "profiles.yml", "synthetic:\n  target: local\n  outputs:\n    local:\n      type: duckdb\n      path: fixture.duckdb\n      threads: 1\n")
    put(root, "models/schema.yml", """version: 2
sources:
  - name: raw
    schema: main
    tables:
      - name: events
        identifier: raw_events
        columns:
          - name: id
      - name: requests
        identifier: raw_requests
      - name: findings
        identifier: raw_findings
""")  # Deliberately partial documentation, never complete-schema evidence.
    for name, (definition, rows) in RELATIONS.items():
        path = put(root, f"seeds/{name}.csv", "")
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow([c.strip().split()[0] for c in definition.split(",")])
            writer.writerows(rows)
    models = {
        "events": "SELECT id, entity_id, event_time, unused, a, b, c FROM {{ source('raw','events') }}",
        "requests": "SELECT request_id, entity_id, request_time FROM {{ source('raw','requests') }}",
        "findings": "SELECT finding_id, event_id, known_at, qualifies FROM {{ source('raw','findings') }}",
        "shared": "SELECT id, entity_id, event_time, unused FROM {{ ref('events') }}",
        "grouped": "SELECT entity_id, COUNT(*) AS total_events FROM {{ ref('events') }} GROUP BY entity_id",
        "latest": """SELECT entity_id, id AS latest_event_id, unused,
            ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY event_time DESC, id DESC) AS rn
            FROM {{ ref('events') }} QUALIFY rn = 1""",
        "static_metrics": """{% set metrics = ['a','b','c'] %}
            SELECT entity_id, {% for m in metrics %}SUM({{ m }}) AS {{ m }}_sum{% if not loop.last %},{% endif %}{% endfor %}
            FROM {{ ref('events') }} GROUP BY entity_id""",
        "runtime_boundary": """SELECT entity_id, 0 AS marker FROM {{ ref('events') }}
            {% if is_incremental() %}WHERE event_time > (SELECT MAX(event_time) FROM {{ this }}){% endif %}
            GROUP BY entity_id""",
        "temporal": """SELECT r.request_id,
            COUNT(DISTINCT CASE WHEN f.event_id IS NOT NULL THEN e.id END) AS prior_events
            FROM {{ ref('requests') }} r
            LEFT JOIN {{ ref('events') }} e ON e.entity_id = r.entity_id
              AND e.event_time >= r.request_time - INTERVAL '1 day' AND e.event_time < r.request_time
            LEFT JOIN {{ ref('findings') }} f ON f.event_id = e.id AND f.qualifies = TRUE
              AND f.known_at < r.request_time
            GROUP BY r.request_id""",
    }
    extras = ", ".join(f"s{i}.unused AS feature_{i}" for i in range(repeats))
    joins = "\n".join(f"LEFT JOIN {{{{ ref('shared') }}}} s{i} ON s{i}.id = r.request_id" for i in range(repeats))
    models["fact_metrics"] = f"""SELECT r.request_id, COALESCE(p.prior_events, 0) AS selected_metric,
        g.total_events, w.latest_event_id, s.a_sum, rt.marker{', ' + extras if extras else ''}
        FROM {{{{ ref('requests') }}}} r
        LEFT JOIN {{{{ ref('temporal') }}}} p ON p.request_id = r.request_id
        LEFT JOIN {{{{ ref('grouped') }}}} g ON g.entity_id = r.entity_id
        LEFT JOIN {{{{ ref('latest') }}}} w ON w.entity_id = r.entity_id
        LEFT JOIN {{{{ ref('static_metrics') }}}} s ON s.entity_id = r.entity_id
        LEFT JOIN {{{{ ref('runtime_boundary') }}}} rt ON rt.entity_id = r.entity_id
        {joins}"""
    for name, code in models.items():
        put(root, f"models/{name}.sql", code)
    return root


def load_relations(con, *, empty=False):
    for name, (definition, rows) in RELATIONS.items():
        con.execute(f"CREATE TABLE {name}({definition})")
        if rows and not empty:
            con.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in rows[0])})", rows)
    # The runtime-defined relation is an explicit opaque input, not a guessed template result.
    con.execute("CREATE TABLE runtime_boundary(entity_id INTEGER, marker INTEGER)")
    if not empty:
        con.execute("INSERT INTO runtime_boundary VALUES (1,0),(2,0)")


def executable(tree, parsed):
    """Bind fixture-owned physical inputs without dbt compilation or credentials."""
    tree = tree.copy()
    for table in tree.find_all(exp.Table):
        ref = parsed.refs.get(table.name)
        if ref:
            table.set("this", exp.to_identifier(
                "raw_" + ref.args[-1] if ref.kind == "source" else ref.args[-1]))
    return tree.sql(dialect="duckdb")
