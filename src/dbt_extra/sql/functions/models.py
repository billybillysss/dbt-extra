"""Independent records shared by dialect catalogs and function lookup."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    example: str
    returns: str | None
    minimum: int
    maximum: int | None
    kind: str = "scalar"
    volatility: str = "immutable"
    may_raise: bool = True
    arities: tuple[int, ...] | None = None


@dataclass(frozen=True)
class FunctionShape:
    kind: str
    columns: int | None
    rows: str
