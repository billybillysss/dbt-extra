"""Shared dbt analysis used by inspection, review, and enrichment."""

from dbt_extra.analysis.analyzer import analyze, catalog

__all__ = ["analyze", "catalog"]
