"""Project boundaries, including Windows symlinks and junctions."""

from pathlib import Path

from dbt_extra.errors import SpecError


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def safe_path(path: Path, *, tree=False) -> None:
    # Do not resolve first: resolution would conceal a link or junction.
    for candidate in (path, *path.parents):
        if linked(candidate):
            raise SpecError(f"symlinks and junctions are not allowed: {candidate}")
    if tree and path.exists():
        for candidate in path.rglob("*"):
            if linked(candidate):
                raise SpecError(f"symlinks and junctions are not allowed: {candidate}")


def within(root: Path, value: str) -> Path:
    path = (root / value).absolute()
    safe_path(path)
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise SpecError(f"Path leaves dbt project: {value}")
    return path
