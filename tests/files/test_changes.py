"""Failure boundaries of shared checked writes, independent of review formats."""

import pytest

from dbt_extra import ChangeSet, SpecError
from dbt_extra.files import changes as writes
from tests.helpers import snapshot


def test_public_changeset_accepts_a_string_root(tmp_path):
    changes = ChangeSet(str(tmp_path))
    changes.set("model.sql", "SELECT 1 AS id\n")
    assert changes.apply() == [tmp_path / "model.sql"]
    assert (tmp_path / "model.sql").read_bytes() == b"SELECT 1 AS id\n"


def test_staging_failure_cleans_files_and_new_directories(tmp_path, monkeypatch):
    first, second = tmp_path / "first.sql", tmp_path / "nested/second.sql"
    first.write_bytes(b"original")
    changes = ChangeSet(tmp_path)
    changes.set(first, b"updated")
    changes.set(second, b"new")
    temporary = writes.temporary

    def fail_second(path, data):
        if path == second:
            raise PermissionError("injected staging failure")
        return temporary(path, data)

    monkeypatch.setattr(writes, "temporary", fail_second)
    with pytest.raises(PermissionError, match="injected staging failure"):
        changes.apply()
    assert snapshot(tmp_path) == {"first.sql": b"original"}
    assert not second.parent.exists()


def test_replace_failure_rolls_back_existing_and_new_files(tmp_path, monkeypatch):
    first, second, third = (tmp_path / name for name in ("first.sql", "new/second.sql", "third.sql"))
    first.write_bytes(b"original first")
    third.write_bytes(b"original third")
    before = snapshot(tmp_path)
    changes = ChangeSet(tmp_path)
    for path in (first, second, third):
        changes.set(path, b"updated")
    replace = writes.os.replace

    def fail_third(source, destination):
        if destination == third:
            raise PermissionError("injected replacement failure")
        return replace(source, destination)

    monkeypatch.setattr(writes.os, "replace", fail_third)
    with pytest.raises(PermissionError, match="injected replacement failure"):
        changes.apply()
    assert snapshot(tmp_path) == before
    assert not second.parent.exists()


def test_preview_and_diffs_do_not_create_directories(tmp_path):
    path = tmp_path / "new/model.sql"
    changes = ChangeSet(tmp_path)
    changes.set(path, "SELECT 1 AS id\n")
    assert "+SELECT 1 AS id" in changes.diffs()
    assert changes.apply(preview=True) == [path]
    assert not list(tmp_path.iterdir())


def test_noop_changes_still_check_the_read_set(tmp_path):
    path = tmp_path / "model.sql"
    path.write_bytes(b"original")
    changes = ChangeSet(tmp_path)
    changes.set(path, b"original")
    path.write_bytes(b"concurrent edit")
    with pytest.raises(SpecError, match="Conflict"):
        changes.apply()
    assert path.read_bytes() == b"concurrent edit"


def test_external_watch_does_not_authorize_external_writes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    settings = tmp_path / "extra_project.yaml"
    settings.write_bytes(b"version: 2")
    changes = ChangeSet(root)
    changes.watch(settings, external=True)
    with pytest.raises(SpecError, match="Path leaves"):
        changes.set(settings, b"overwritten")
    assert settings.read_bytes() == b"version: 2"


def test_linked_write_path_is_rejected(tmp_path):
    target, link = tmp_path / "target", tmp_path / "link"
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires platform privileges")
    with pytest.raises(SpecError, match="symlinks and junctions"):
        ChangeSet(tmp_path).set(link / "model.sql", b"unsafe")
    assert not list(target.iterdir())
