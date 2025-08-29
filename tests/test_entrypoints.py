from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _python() -> str:
    # Use the same interpreter running the tests
    return sys.executable


def test_module_entrypoint_help():
    """Running `python -m bootServer --help` should exit 0 and print usage/help."""
    proc = subprocess.run([_python(), "-m", "bootServer", "--help"], capture_output=True, text=True, timeout=5)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "usage" in out.lower() or "serve-boot-artifacts" in out


def test_launcher_script_help(tmp_path: Path):
    """Running the repository launcher script with --help should exit 0 and print usage/help."""
    # ensure the launcher script is present at repository root
    launcher = Path.cwd() / "serve-boot-artifacts"
    assert launcher.exists() and launcher.is_file()
    # invoke with --help
    proc = subprocess.run([_python(), str(launcher), "--help"], capture_output=True, text=True, timeout=5)
    assert proc.returncode == 0
    out = proc.stdout + proc.stderr
    assert "usage" in out.lower() or "serve-boot-artifacts" in out
