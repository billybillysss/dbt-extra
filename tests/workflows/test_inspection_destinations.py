"""SQL-only inspection exports never mix CLI diagnostics into the payload."""

import subprocess

import pytest

from dbt_extra.errors import SpecError
from dbt_extra.files import output
from dbt_extra.inspection import inspect
from dbt_extra.sql.renderer import render
from tests.helpers import invoke, project, put, snapshot


@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("compiled", ["true", "false"])
def test_copy_and_save_use_rendered_sql_only(native, monkeypatch, tmp_path, verbose, compiled):
    put(native, "models/slv/orders.sql",
        "select id, trim(amount) as amount from {{ source('raw', 'orders') }}")
    before = snapshot(native)
    copied = []
    monkeypatch.setattr("dbt_extra.cli.copy_text", copied.append)
    # Relative output paths are based on the project, not the caller's directory.
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    flags = ["--verbose"] if verbose else []
    result = invoke(native, "inspect", "revenue", "--compile", compiled,
                    "--copy", "--output", "extra/sql/revenue.sql", *flags)
    assert result.exit_code == 0, result.output
    p = project(native)
    tree, parsed, _ = inspect(p, "revenue", compiled=compiled == "true")
    expected = render(tree, parsed, p.dialect)
    destination = native / "extra/sql/revenue.sql"
    assert destination.read_bytes() == expected.encode("utf-8")
    assert copied == [expected]
    assert expected in result.stdout
    assert "Not executed. Authored files unchanged." in result.stdout
    assert "Copied SQL to clipboard." in result.stderr
    assert "Saved SQL:" in result.stderr
    assert "-- Boundary/coverage:" not in copied[0]
    assert "-- Rewrites skipped:" not in copied[0]
    assert "-- Offline" not in copied[0]
    assert {name: (native / name).read_bytes() for name in before} == before


def test_output_overwrite_requires_force(native):
    destination = put(native, "extra/revenue.sql", "keep me")
    result = invoke(native, "inspect", "revenue", "--output", str(destination))
    assert result.exit_code != 0
    assert "use --force" in result.output
    assert destination.read_text() == "keep me"
    result = invoke(native, "inspect", "revenue", "--output", str(destination), "--force")
    assert result.exit_code == 0, result.output
    assert "SELECT" in destination.read_text()


@pytest.mark.parametrize("relative", ["models/gld/revenue.sql", "models/schema.yml", "dbt_project.yml"])
def test_force_cannot_overwrite_project_inputs(native, relative):
    before = snapshot(native)
    result = invoke(native, "inspect", "revenue", "--output", relative, "--force")
    assert result.exit_code != 0
    assert "Refusing to overwrite project input" in result.output
    assert snapshot(native) == before


def test_absolute_output_outside_project(native, tmp_path):
    destination = tmp_path.parent / f"{tmp_path.name}-export.sql"
    try:
        result = invoke(native, "inspect", "revenue", "--output", str(destination))
        assert result.exit_code == 0, result.output
        p = project(native)
        tree, parsed, _ = inspect(p, "revenue")
        assert destination.read_text(encoding="utf-8") == render(tree, parsed, p.dialect)
    finally:
        destination.unlink(missing_ok=True)


@pytest.mark.parametrize("flags", [
    ["--view", "plan", "--copy"],
    ["--view", "plan", "--output", "extra/plan.sql"],
    ["--force"],
])
def test_invalid_destination_options_do_not_write(native, flags):
    before = snapshot(native)
    result = invoke(native, "inspect", "revenue", *flags)
    assert result.exit_code == 2, result.output
    assert "require" in result.output
    assert snapshot(native) == before


def test_clipboard_failure_preserves_sql_and_saved_file(native, monkeypatch):
    def unavailable(text):
        raise SpecError("Clipboard unavailable; use --output PATH instead.")
    monkeypatch.setattr("dbt_extra.cli.copy_text", unavailable)
    result = invoke(native, "inspect", "revenue", "--copy", "--output", "extra/revenue.sql")
    assert result.exit_code == 1
    assert "Clipboard unavailable" in result.stderr
    assert "Saved SQL:" in result.stderr
    assert (native / "extra/revenue.sql").read_text() in result.stdout


def test_save_failure_does_not_copy_or_replace_files(native, monkeypatch):
    destination = put(native, "extra/revenue.sql", "keep me")
    copied = []
    monkeypatch.setattr("dbt_extra.cli.copy_text", copied.append)
    result = invoke(native, "inspect", "revenue", "--copy", "--output", str(destination))
    assert result.exit_code == 1
    assert destination.read_text() == "keep me"
    assert copied == []


def test_output_rejects_linked_parent(native):
    actual = native / "actual"
    actual.mkdir()
    link = native / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    result = invoke(native, "inspect", "revenue", "--output", "linked/revenue.sql")
    assert result.exit_code != 0
    assert "symlinks and junctions are not allowed" in result.output
    assert not (actual / "revenue.sql").exists()


def test_sql_comments_and_unicode_are_preserved(native, monkeypatch):
    put(native, "models/commented.sql", "select 'café 客户' as label /* authored comment */")
    copied = []
    monkeypatch.setattr("dbt_extra.cli.copy_text", copied.append)
    result = invoke(native, "inspect", "commented", "--copy", "--output", "extra/commented.sql")
    assert result.exit_code == 0, result.output
    assert "café 客户" in copied[0]
    assert "authored comment" in copied[0]
    assert (native / "extra/commented.sql").read_bytes() == copied[0].encode("utf-8")


@pytest.mark.parametrize("platform, environment, installed, expected", [
    ("win32", {}, [], ["powershell.exe"]),
    ("darwin", {}, [], ["pbcopy"]),
    ("linux", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, ["wl-copy", "xclip"], ["wl-copy"]),
    ("linux", {"DISPLAY": ":0"}, ["xclip"], ["xclip", "-selection", "clipboard"]),
    ("linux", {"DISPLAY": ":0"}, ["xsel"], ["xsel", "--clipboard", "--input"]),
])
def test_native_clipboard_commands(monkeypatch, platform, environment, installed, expected):
    monkeypatch.setattr(output.sys, "platform", platform)
    for name in ("WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(output.shutil, "which", lambda name: name if name in installed else None)
    calls = []
    monkeypatch.setattr(output.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    text = "SELECT 'café 客户';\n"
    output.copy_text(text)
    command, kwargs = calls[0]
    assert command[:len(expected)] == expected
    assert kwargs["input"] == text
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["check"] is True
    assert kwargs["timeout"] == 10
    assert not kwargs.get("shell")
    if platform == "win32":
        assert "Set-Clipboard" in command[-1]
        assert "InputEncoding" in command[-1]


def test_headless_clipboard_has_actionable_error(monkeypatch):
    monkeypatch.setattr(output.sys, "platform", "linux")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(SpecError, match="Clipboard unavailable; use --output PATH"):
        output.copy_text("SELECT 1;\n")


@pytest.mark.parametrize("error", [
    FileNotFoundError("clipboard tool missing"),
    subprocess.CalledProcessError(1, "pbcopy", stderr="clipboard denied"),
    subprocess.TimeoutExpired("pbcopy", 10),
])
def test_native_clipboard_errors_are_user_facing(monkeypatch, error):
    monkeypatch.setattr(output.sys, "platform", "darwin")
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(output.subprocess, "run", fail)
    with pytest.raises(SpecError, match="Clipboard copy failed:.*Use --output PATH"):
        output.copy_text("SELECT 1;\n")


def test_help_documents_destinations(native):
    result = invoke(native, "inspect", "--help")
    assert result.exit_code == 0
    for flag in ("--copy", "--output", "--force", "--verbose"):
        assert flag in result.output
