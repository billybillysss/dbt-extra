"""Checked byte changes, read-set conflicts and rollback-capable writes."""

from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from pathlib import Path

from dbt_extra.files.paths import safe_path, within
from dbt_extra.errors import SpecError


def digest(content):
    return hashlib.sha256(content).hexdigest() if content is not None else None


def content(path):
    return path.read_bytes() if path.is_file() else None


class ChangeSet:
    def __init__(self, root):
        root = Path(root).absolute()
        safe_path(root)
        self.root = root.resolve()
        self.before = {}
        self.after = {}

    def watch(self, path, expected=None, *, check=False, external=False):
        # Only read-set checks may explicitly watch external tool settings.
        # set() always enforces the write root regardless of prior watches.
        path = Path(path).absolute() if external else within(self.root, str(path))
        safe_path(path)
        current = content(path)
        if check and digest(current) != expected:
            raise SpecError(f"Conflict: {path} changed since export; re-export before editing")
        self.before.setdefault(path, current)
        return path

    def set(self, path, value):
        path = self.watch(path)
        self.after[path] = value.encode("utf-8") if isinstance(value, str) else value

    def changed(self):
        return {p: data for p, data in self.after.items() if data != self.before[p]}

    def diffs(self):
        return "".join("".join(difflib.unified_diff(
            (self.before[p] or b"").decode("utf-8").splitlines(keepends=True),
            data.decode("utf-8").splitlines(keepends=True),
            fromfile=p.relative_to(self.root).as_posix(), tofile=p.relative_to(self.root).as_posix(),
        )) for p, data in self.changed().items())

    def apply(self, *, preview=False):
        changed = self.changed()
        # Check the whole read set, even when individual staged updates are no-ops.
        for path, before in self.before.items():
            safe_path(path)
            if content(path) != before:
                raise SpecError(f"Conflict: {path} changed while preparing edits")
        if preview:
            return list(changed)
        staged, written, created = {}, [], []
        try:
            for path, data in changed.items():
                missing = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for parent in reversed(missing):
                    parent.mkdir()
                    created.append(parent)
                staged[path] = temporary(path, data)
            for path in changed:
                safe_path(path)
                if content(path) != self.before[path]:
                    raise SpecError(f"Conflict: {path} changed while staging edits")
            for path, stage in staged.items():
                os.replace(stage, path)
                written.append(path)
        except Exception:
            for path in reversed(written):
                original = self.before[path]
                if original is None:
                    path.unlink()
                else:
                    restore = temporary(path, original)
                    os.replace(restore, path)
            raise
        finally:
            for stage in staged.values():
                stage.unlink(missing_ok=True)
            for directory in reversed(created):
                if not any(directory.iterdir()):
                    directory.rmdir()
        return list(changed)


def temporary(path, data):
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".extra", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        if path.exists():
            os.chmod(name, path.stat().st_mode)
        return Path(name)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
