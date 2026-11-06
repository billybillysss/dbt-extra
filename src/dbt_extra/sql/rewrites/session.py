"""Copy-on-attempt SQL rules and stable, operation-local transformation outcomes."""

from dataclasses import dataclass

from sqlglot.errors import SqlglotError

from dbt_extra.errors import SpecError
from dbt_extra.sql.parser import read_query
from dbt_extra.sql.renderer import sql


@dataclass(frozen=True)
class Eligibility:
    eligible: bool = True
    reason_code: str = "eligible"
    reason: str = "requirements satisfied"


class Outcomes:
    def __init__(self, resource="SQL", values=None):
        self.resource = resource
        self.values = values if values is not None else []

    def add(self, rule, scope, status, reason_code, reason, *, resource=None, count=1):
        item = dict(rule=rule, resource_id=resource or self.resource, scope=scope,
                    status=status, reason_code=reason_code, reason=reason, occurrence_count=count)
        for previous in self.values:
            if all(previous.get(k) == v for k, v in item.items() if k != "occurrence_count"):
                previous["occurrence_count"] = previous.get("occurrence_count", 1) + count
                return
        self.values.append(item)


class RejectedCandidate(SpecError):
    """An expected validation failure, not an implementation exception."""


class Checkpoints:
    """Only SQLGlot failures and explicitly rejected candidates are recoverable.

    No Scope/binding objects survive a commit. Validators must rebuild analysis on
    the supplied candidate; immutable resource evidence may be cached separately.
    A failed candidate never becomes the input of a subsequent rule.
    """

    def __init__(self, tree, dialect, outcomes=None, *, validate=None):
        self.tree, self.dialect = tree, dialect
        self.outcomes = outcomes if outcomes is not None else Outcomes()
        self.validate = validate
        self.capabilities = set()
        self.generation = 0

    def attempt(self, rule, function, *, decision=Eligibility(), scope="query",
                requires=(), provides=(), invalidates=()):
        missing = set(requires) - self.capabilities
        if missing:
            decision = Eligibility(False, "missing_analysis", "requires " + ", ".join(sorted(missing)))
        if not decision.eligible:
            self.outcomes.add(rule, scope, "blocked", decision.reason_code, decision.reason)
            return False
        candidate = self.tree.copy()
        try:
            candidate = function(candidate)
            if candidate is None:
                raise TypeError(f"Rule {rule} did not return a query")
            changed = candidate != self.tree or sql(candidate, self.dialect) != sql(self.tree, self.dialect)
            # Parsing is a structural check, not evidence of semantic equivalence.
            # An unchanged candidate inherits the last checkpoint's validation.
            if changed:
                try:
                    read_query(sql(candidate, self.dialect), rule, self.dialect)
                except SpecError as exc:
                    raise RejectedCandidate(str(exc)) from exc
                if self.validate:
                    self.validate(candidate)
        except (SqlglotError, RejectedCandidate) as exc:
            self.outcomes.add(rule, scope, "rolled_back", "candidate_rejected", f"{type(exc).__name__}: {exc}")
            return False
        self.tree = candidate
        self.capabilities.difference_update(invalidates)
        self.capabilities.update(provides)
        if changed:
            self.generation += 1
        self.outcomes.add(rule, scope, "applied" if changed else "not_applicable",
                          "validated" if changed else "no_change",
                          "candidate passed structural checks; execution equivalence not verified" if changed else "no eligible change")
        return True


def output_contract(tree):
    return [p.output_name for p in tree.selects]


def outcome_text(item):
    count = item.get("occurrence_count", 1)
    message = f"{item['rule']}: {item['status']}"
    if item.get("scope") not in {None, "query", "resource"}:
        message += f" [{item['scope']}]"
    if item["status"] in {"blocked", "rolled_back"}:
        message += f" — {item['reason']}"
    return message + (f" ({count} occurrences)" if count > 1 else "")


def validate_contract(before, after, dialect):
    if output_contract(before) != output_contract(after):
        raise RejectedCandidate("output names or order changed")
    if sorted(c for n in before.walk() for c in n.comments or []) != sorted(c for n in after.walk() for c in n.comments or []):
        raise RejectedCandidate("SQL comments would be discarded")
    reparsed = read_query(sql(after, dialect), "optimized SQL", dialect)
    if sql(reparsed, dialect) != sql(after, dialect):
        raise RejectedCandidate("SQL did not round-trip")
