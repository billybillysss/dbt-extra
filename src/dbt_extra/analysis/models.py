"""Coverage and provenance vocabulary for JSON-compatible analysis results.

Results describe dbt definitions, not an independently authored semantic model.
"""

from collections import Counter
from typing import Literal, NotRequired, TypedDict


Status = Literal["metadata_only", "parsed", "partial", "unavailable", "source_only"]


class ResourceAnalysis(TypedDict):
    resource_id: str
    name: str
    resource_type: str
    package: str
    model_path: str
    source_file: str
    properties_file: str | None
    description: str
    properties: dict
    config: dict
    sql: str
    columns: list[dict]
    dependencies: list[str]
    status: Status
    reason: str | None
    provenance: str
    context: NotRequired[dict]


def coverage(resources):
    return dict(sorted(Counter(r["status"] for r in resources).items()))
