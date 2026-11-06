"""Offline development benchmark: python -m scripts.benchmark_inspection."""

import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter

from dbt_extra.inspection import inspect
from tests.helpers import project
from tests.synthetic import synthetic_project


def benchmark(root, repeats):
    synthetic_project(root, repeats=repeats)
    p = project(root)
    results = []
    for optimized in (False, True):
        start = perf_counter()
        tree, _, issues = inspect(p, "fact_metrics", columns=["selected_metric"],
                                 optimized=optimized, compiled=False)
        results.append(dict(repeats=repeats, optimized=optimized, seconds=round(perf_counter() - start, 6),
                            ast_nodes=sum(1 for _ in tree.walk()),
                            sql_bytes=len(tree.sql(dialect="duckdb").encode()),
                            diagnostics=len(issues),
                            boundary_diagnostics=sum(i.get("rule") == "expansion" for i in issues),
                            boundary_occurrences=sum(i.get("occurrence_count", 1) for i in issues if i.get("rule") == "expansion")))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, nargs="+", default=[4, 12, 24])
    parser.add_argument("--temp-dir", type=Path)
    args = parser.parse_args()
    if any(n < 1 or n > 100 for n in args.repeats):
        parser.error("repeats must be between 1 and 100")
    with tempfile.TemporaryDirectory(prefix="dbt-extra-benchmark-", dir=args.temp_dir) as directory:
        rows = [row for count in args.repeats for row in benchmark(Path(directory) / str(count), count)]
        print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
