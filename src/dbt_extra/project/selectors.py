"""Selection of dbt resources by identity, authored path, tags, or package."""

import fnmatch

from dbt_extra.config import strings
from dbt_extra.errors import SpecError


def select(resources, selections=None, exclude=None, *, kinds=None):
    selections = strings(selections, "select") if selections is not None else None
    exclude = strings(exclude, "exclude") if exclude is not None else []

    def matches(r, selector):
        method, separator, value = selector.partition(":")
        if not separator:
            return fnmatch.fnmatchcase(r.name, selector) or r.id == selector
        tags = r.config.get("tags", r.properties.get("tags", []))
        tags = [tags] if isinstance(tags, str) else tags
        values = {"id": [r.id], "name": [r.name], "path": [r.source_file], "package": [r.package],
                  "resource_type": [r.kind], "tag": tags or []}
        if method not in values:
            raise SpecError(f"Unsupported selector: {selector}")
        return any(fnmatch.fnmatchcase(v, value) for v in values[method])

    result = [r for r in resources if (kinds is None or r.kind in kinds)
              and (selections is None or any(matches(r, s) for s in selections))
              and not any(matches(r, s) for s in exclude)]
    if selections and not result:
        raise SpecError("Selection matched no resources")
    return sorted(result, key=lambda r: (r.package, r.model_path, r.name, r.id))
