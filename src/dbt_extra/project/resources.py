"""In-memory dbt resource identities and authored metadata locations."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Resource:
    id: str
    name: str
    kind: str
    package: str
    path: Path | None
    source_file: str
    model_path: str
    code: str = ""
    properties: dict = field(default_factory=dict)
    property_path: Path | None = None
    property_locator: tuple = ()
    node: dict = field(default_factory=dict)
    inherited_config: dict = field(default_factory=dict)
    catalog_columns: dict = field(default_factory=dict)
    inline_config: dict = field(default_factory=dict)
    stale: bool = False

    @property
    def columns(self):
        return {c["name"]: c for c in self.properties.get("columns", [])}

    @property
    def known_columns(self):
        evidence = {} if self.stale else self.node.get("columns", {})
        result = {}
        for columns in ({} if self.stale else self.catalog_columns, evidence, self.columns):
            for name, properties in columns.items():
                result[name] = {**result.get(name, {}), **properties}
        return result

    @property
    def config(self):
        evidence = {} if self.stale else self.node.get("config", {})
        return {**self.inherited_config, **evidence, **self.properties.get("config", {}), **self.inline_config}
