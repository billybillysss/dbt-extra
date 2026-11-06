"""Snapshot named functions from official documentation for the ownership tables.

Network access is explicit: run this script to refresh function_sources.json,
review its diff, then regenerate the Markdown with generate_sql_function_docs.py.
This collects documented names, not warehouse signatures or runtime capabilities.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urldefrag, urljoin
from urllib.request import Request, urlopen


OUTPUT = Path(__file__).resolve().parents[1] / "docs/reference/sql-functions/function_sources.json"
NAME = re.compile(r"[@A-Za-z_][@A-Za-z_0-9$]*(?:\.[A-Za-z_][A-Za-z_0-9$]*)*")


class Links(HTMLParser):
    def __init__(self, text, tables_only=False):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
        self.tables_only = tables_only
        self.table_depth = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
        if tag == "a" and (not self.tables_only or self.table_depth):
            self.current = [dict(attrs).get("href", ""), ""]

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if tag == "table":
            self.table_depth -= 1
        if tag == "a" and self.current is not None:
            self.links.append(tuple(self.current))
            self.current = None


def fetch(url):
    request = Request(url, headers={"User-Agent": "dbt-extra-function-docs", "Accept": "*/*"})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8")


def pages(urls):
    with ThreadPoolExecutor(max_workers=12) as pool:
        return list(zip(urls, pool.map(fetch, urls)))


def snapshot(version, sources, names):
    names = {name.upper() for name in names if NAME.fullmatch(name)}
    if not names:
        raise ValueError(f"No names extracted from {sources}")
    return {"version": version, "sources": sorted(set(sources)), "names": sorted(names)}


def linked_index(url, path_fragment, version, suffix="", tables_only=False):
    names = []
    for href, label in Links(fetch(url), tables_only=tables_only).links:
        if path_fragment not in href:
            continue
        label = label.strip()
        if suffix:
            # Databricks labels include "aggregate function", "table-valued
            # generator function", signature hints and MATCH_RECOGNIZE suffixes.
            match = re.match(r"^([a-z_][a-z_0-9]*)\b.*\bfunction\b", label)
            label = match[1] if match else ""
        # Multi-name/wildcard index labels require manual expansion, not guesses.
        if NAME.fullmatch(label):
            names.append(label)
    return snapshot(version, [url], names)


def duckdb():
    root = "https://duckdb.org/docs/2.0/sql/functions/overview.html"
    urls = sorted({urldefrag(urljoin(root, href))[0] for href, _ in Links(fetch(root)).links
                   if urljoin(root, href).startswith("https://duckdb.org/docs/2.0/sql/functions/")})
    names = []
    for _, text in pages(urls):
        for _, label in Links(text).links:
            match = re.match(r"^([a-z_][a-z_0-9]*)\s*\(", label.strip())
            if match:
                names.append(match[1])
    return snapshot("DuckDB 2.0 function reference", urls, names)


def postgres():
    root = "https://www.postgresql.org/docs/18/functions.html"
    urls = sorted({urldefrag(urljoin(root, href))[0] for href, _ in Links(fetch(root)).links
                   if re.match(r"functions-[a-z-]+\.html", href)})
    names = []
    for _, text in pages(urls):
        names.extend(re.findall(r'<code class="function">([@A-Za-z_][A-Za-z_0-9]*)</code>', text))
    return snapshot("PostgreSQL 18, Functions and Operators chapter", urls, names)


def spark():
    url = "https://spark.apache.org/docs/3.5.7/api/sql/index.html"
    text = fetch(url)
    names = re.findall(r'<h3 id="([a-z_][a-z_0-9]*)"', text)
    # The built-in reference also lists operators/expressions, not just functions.
    names = set(names) - {"and", "or", "not", "between", "case", "in", "when", "like", "ilike"}
    return snapshot("Apache Spark 3.5.7 built-ins", [url], names)


def trino():
    url = "https://trino.io/docs/current/functions/list.html"
    names = []
    for href, label in Links(fetch(url)).links:
        if ".html#" in href:
            label = label.strip()
            if label not in {"ALL", "AND", "ANY", "BETWEEN", "CASE", "DECIMAL", "NOT", "OR", "SOME"}:
                names.append(label.removesuffix("()"))
    return snapshot("Trino current function index (dated snapshot)", [url], names)


def athena():
    root = "https://docs.aws.amazon.com/athena/latest/ug/functions-env3.html"
    changes = "https://docs.aws.amazon.com/athena/latest/ug/engine-versions-reference-0003.html"
    # Only categories linked by Athena's own reference; no local Trino catalog inheritance.
    urls = sorted({href for href, _ in Links(fetch(root)).links
                   if href.startswith("https://trino.io/docs/current/functions/")})
    names = {"invoker_principal"}
    for _, text in pages(urls):
        # Sphinx marks the actual function signatures with this class.
        names.update(re.findall(
            r'<span class="sig-name descname"><span class="pre">([a-z_][a-z_0-9]*)</span>', text
        ))
    # Explicit engine-3 additions in the AWS reference (not all are in current Trino).
    names.update({"contains_sequence", "murmur3", "format_number", "listagg"})
    return snapshot("Athena engine 3; AWS-linked Trino categories (dated reference, verify availability)",
                    [root, changes, *urls], names)


def redshift():
    root = "https://docs.aws.amazon.com/redshift/latest/dg/c_SQL_functions.html"
    urls = sorted({urldefrag(urljoin(root, href))[0] for href, _ in Links(fetch(root)).links
                   if href.startswith("./") and href.endswith(".html")})
    names = []
    for _, text in pages(urls):
        for _, label in Links(text).links:
            label = label.strip().removesuffix(" function").removesuffix("()").strip()
            if label == label.upper() or label.startswith("ST_"):
                if NAME.fullmatch(label):
                    names.append(label)
    return snapshot("Amazon Redshift SQL function category indexes (dated snapshot)", [root, *urls], names)


def microsoft():
    api = "https://api.github.com/repos/MicrosoftDocs/sql-docs/contents/docs/t-sql/functions"
    entries = json.loads(fetch(api))
    urls = sorted(entry["download_url"] for entry in entries if entry["name"].endswith(".md"))
    tsql, fabric = set(), set()
    for _, text in pages(urls):
        title = re.search(r"^# (.+?)\s*\(Transact-SQL\)", text, re.MULTILINE)
        if not title:
            continue
        names = {name.strip(" `") for name in re.split(r" and |, | / ", title[1])}
        names = {name for name in names if NAME.fullmatch(name) and name == name.upper()}
        tsql.update(names)
        # Fabric SQL Database alone is not Warehouse evidence.
        includes = re.findall(r"applies-to-version/([^\s)]+)", text)
        if any("fabricdw" in include or "fabricse" in include for include in includes):
            fabric.update(names)
    tsql_source = "https://learn.microsoft.com/en-us/sql/t-sql/functions/functions?view=sql-server-ver17"
    fabric_source = "https://learn.microsoft.com/en-us/sql/t-sql/functions/functions?view=fabric"
    return (
        snapshot("SQL Server 17.x documentation; T-SQL function articles", [tsql_source, api], tsql),
        snapshot("Fabric Warehouse/SQL analytics endpoint applies-to articles (not Fabric SQL Database)",
                 [fabric_source, api], fabric),
    )


def main():
    data = {"snapshot_date": date.today().isoformat(), "dialects": {}}
    collectors = {
        "duckdb": duckdb, "postgres": postgres, "spark": spark, "trino": trino,
        "athena": athena, "redshift": redshift,
        "snowflake": lambda: linked_index(
            "https://docs.snowflake.com/en/sql-reference/functions-all", "/functions/",
            "Snowflake all-functions index (dated snapshot)", tables_only=True),
        "bigquery": lambda: linked_index(
            "https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/functions-all",
            "/standard-sql/", "GoogleSQL all-functions index (dated snapshot)", tables_only=True),
        "databricks": lambda: linked_index(
            "https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-functions-builtin-alpha",
            "/functions/", "Databricks built-in alphabetical index (dated snapshot)", "function"),
    }
    for dialect, collect in collectors.items():
        data["dialects"][dialect] = collect()
        print(f"{dialect}: {len(data['dialects'][dialect]['names'])} official names")
    tsql, fabric = microsoft()
    data["dialects"].update(tsql=tsql, fabric=fabric)
    print(f"tsql: {len(tsql['names'])}; fabric: {len(fabric['names'])} official names")
    OUTPUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
