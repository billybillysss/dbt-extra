"""Project-independent parsed SQL and literal template reference records."""

from dataclasses import dataclass, field

from sqlglot import exp

from dbt_extra.errors import SpecError


class UnsupportedSQL(SpecError):
    """Valid template structure that cannot be analyzed without rendering dbt."""


@dataclass
class Reference:
    text: str
    kind: str
    args: tuple
    version: object = None


@dataclass
class ParsedSQL:
    tree: exp.Query
    refs: dict[str, Reference] = field(default_factory=dict)
    prefix: str = ""
    config: dict = field(default_factory=dict)
    config_dynamic: bool = False
    macros: dict[str, str] = field(default_factory=dict)
    opaque_macros: dict[str, str] = field(default_factory=dict)
    macro_aliases: dict[str, str] = field(default_factory=dict)
    template_source: str | None = None
