"""Explicit text exports and optional system clipboard access."""

import os
import shutil
import subprocess
import sys
import tempfile

from dbt_extra.errors import SpecError
from dbt_extra.files.changes import ChangeSet
from dbt_extra.files.paths import safe_path


def save_text(path, text, *, force=False):
    safe_path(path)
    if path.exists() and not force:
        raise SpecError(f"Refusing to overwrite {path}; use --force to replace it")
    if path.exists() and not path.is_file():
        raise SpecError(f"Output must be a file: {path}")
    changes = ChangeSet(path.parent)
    changes.set(path, text)
    changes.apply()


def copy_text(text):
    """Use native clipboard tools without a shell or mandatory dependencies."""
    if sys.platform == "win32":
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                   "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new(); "
                   "Set-Clipboard -Value ([Console]::In.ReadToEnd())"]
    elif sys.platform == "darwin":
        command = ["pbcopy"]
    elif os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        command = ["wl-copy"]
    elif os.environ.get("DISPLAY") and shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard"]
    elif os.environ.get("DISPLAY") and shutil.which("xsel"):
        command = ["xsel", "--clipboard", "--input"]
    else:
        raise SpecError("Clipboard unavailable; use --output PATH instead. "
                        "Linux requires a desktop session and wl-copy, xclip or xsel.")
    # X11 clipboard owners can fork and keep stderr open. A pipe would make
    # communicate() wait for that owner to exit, even after a successful copy.
    with tempfile.TemporaryFile() as errors:
        try:
            subprocess.run(command, input=text, encoding="utf-8", check=True,
                           stdout=subprocess.DEVNULL, stderr=errors, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.seek(0)
            detail = errors.read().decode("utf-8", errors="replace").strip() or str(exc)
            raise SpecError(f"Clipboard copy failed: {detail}. Use --output PATH instead.") from exc
