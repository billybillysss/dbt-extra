"""Read-only JSON analysis export; deliberately has no import path."""

import json


def outputs(document):
    return {"review.json": (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")}
