"""
Network / path utilities shared by video-publisher scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote


def ensure_utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr so Chinese messages survive on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def require_abs(*paths: str) -> None:
    """Validate that all given paths are absolute. Exits with error if not."""
    for p in paths:
        if p and not os.path.isabs(p):
            print(f"ERROR: Path must be absolute, got: {p}", file=sys.stderr)
            sys.exit(1)


def download_file(url: str, output_path: str, timeout: int = 300) -> str:
    """Download a file from a URL to output_path. Supports http(s):// and file://."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)

    if parsed.scheme == "file":
        src = unquote(parsed.path)
        if src.startswith("/") and len(src) > 2 and src[2] == ":":
            src = src[1:]
        if not os.path.exists(src):
            raise RuntimeError(f"Local file not found: {src}")
        import shutil
        shutil.copy2(src, output_path)
        return output_path

    elif parsed.scheme in ("http", "https"):
        import requests
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        with open(output_path, "wb") as fh:
            fh.write(resp.content)
        return output_path

    else:
        raise RuntimeError(f"Unsupported URL scheme '{parsed.scheme}': {url}")


def run_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run a subprocess command, returning the CompletedProcess."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"ERROR: Command timed out after {timeout}s: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)


def run_command_checked(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 300,
) -> str:
    """Run a command and return stdout. Exits on failure."""
    result = run_command(cmd, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        print(f"ERROR: Command failed (exit {result.returncode}): {' '.join(cmd)}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout
