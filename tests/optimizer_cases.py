"""Portable positive rule cases shared by real-engine execution lanes."""

from sqlglot import exp, parse_one


RULE_SCHEMA = {
    "violations": {"id": "INT", "type_id": "INT", "amount": "INT"},
    "types": {"id": "INT", "code": "VARCHAR"},
}
RULE_QUERIES = {
    "normalize": "select v.id from violations v where (v.id=1 and v.amount>1) or v.id=2",
    "pushdown": "select q.id from (select distinct v.id from violations v) q where q.id>1 and true",
    "join": "select a.id, b.id as peer, c.id as matched from violations a cross join violations b "
            "join violations c on a.type_id=c.type_id and b.type_id=c.type_id",
    "factor": "select a.id, a.n, b.n as other from "
              "(select v.id, count(*) as n from violations v group by v.id) a join "
              "(select v.id, count(*) as n from violations v group by v.id) b on a.id=b.id",
    "membership": "select v.id from violations v where exists("
                  "select 1 from types t where t.id=v.type_id and t.code='A')",
    "union": "select v.id from violations v where v.amount=2 union all "
             "select v.id from violations v where v.amount<>2",
}
RULE_NAMES = {
    "normalize": "predicate_normalization", "pushdown": "predicate_pushdown",
    "join": "join_reordering", "factor": "subquery_deduplication",
    "membership": "exists_decorrelation", "union": "complementary_union",
}


def assert_rule_exercised(rule, candidate, dialect, outcomes):
    tree = parse_one(candidate, read=dialect)
    if rule == "membership" and dialect not in {"duckdb", "spark"}:
        assert tree.find(exp.Exists) and not tree.find(exp.In)
        assert not any(o["rule"] == RULE_NAMES[rule] and o["status"] == "applied" for o in outcomes)
        return
    assert any(o["rule"] == RULE_NAMES[rule] and o["status"] == "applied" for o in outcomes), outcomes
    if rule == "normalize":
        assert isinstance(tree.args["where"].this, exp.And)
    elif rule == "pushdown":
        assert tree.args.get("where") is None and next(tree.find_all(exp.Subquery)).this.args.get("where")
    elif rule == "join":
        assert len(list(tree.find_all(exp.Join))) == 2 and not any(j.kind == "CROSS" for j in tree.find_all(exp.Join))
    elif rule == "factor":
        assert len(list(tree.find_all(exp.CTE))) == 1 and len(list(tree.find_all(exp.Select))) == 2
    elif rule == "membership":
        assert not tree.find(exp.Exists) and tree.find(exp.In)
    else:
        assert not tree.find(exp.Union) and len(list(tree.find_all(exp.Table))) == 1
