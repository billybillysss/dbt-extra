"""CSV review serialization with an immutable JSON baseline sidecar."""

import csv
import io
import json

from dbt_extra.errors import SpecError
from dbt_extra.review.contract import HEADERS, LEGEND, json_text


def outputs(tables, baseline):
    result = {"_baseline.json": (json_text(baseline) + "\n").encode("utf-8")}
    for name, headers in HEADERS.items():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(tables[name])
        result[name + ".csv"] = stream.getvalue().encode("utf-8-sig")
    result["README.txt"] = "\n".join(f"{a}: {b}" for a, b in LEGEND).encode("utf-8")
    return result


def read_csv(path):
    directory = path if path.is_dir() else path.parent
    baseline_path = directory / "_baseline.json"
    if not baseline_path.is_file():
        raise SpecError("CSV import requires its exported _baseline.json sidecar")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    tables = {}
    for name, headers in HEADERS.items():
        with (directory / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != headers:
                raise SpecError(f"Unexpected headers in {name}.csv")
            items = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in items):
                raise SpecError(f"Malformed CSV row in {name}.csv")
            tables[name] = items
    return tables, baseline
