"""Resource dependency graphs and cycle checks."""

from dbt_extra.errors import SpecError
from dbt_extra.sql.references import resolve_ref


def dependencies(project, parsed):
    return [up.id for ref in parsed.refs.values() if (up := resolve_ref(project, ref))]


def validate_cycles(graph):
    active, done = [], set()

    def visit(uid):
        if uid in active:
            raise SpecError(f"Cyclic dbt references: {' -> '.join((*active, uid))}")
        if uid in done:
            return
        active.append(uid)
        for dependency in graph.get(uid, []):
            visit(dependency)
        active.pop()
        done.add(uid)

    for uid in graph:
        visit(uid)
