"""Offline dbt transformation review, inspection, and checked source edits."""

from dbt_extra.errors import SpecError

__version__ = "0.2.1"

__all__ = ["Project", "ChangeSet", "SpecError", "__version__"]


def __getattr__(name):
    # Version/error access (including CLI --version) needs no project loading.
    if name == "Project":
        from dbt_extra.project import Project
        return Project
    if name == "ChangeSet":
        from dbt_extra.files.changes import ChangeSet
        return ChangeSet
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
