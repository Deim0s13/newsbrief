"""Package version from pyproject.toml (single source of truth)."""

from __future__ import annotations

import sys
from pathlib import Path


def read_pyproject_version() -> str:
    """Return [project].version from repo-root pyproject.toml."""
    if sys.version_info >= (3, 11):
        import tomllib as toml_loader
    else:
        import tomli as toml_loader  # type: ignore[import-not-found,unused-ignore]

    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = toml_loader.load(f)
        v = data.get("project", {}).get("version", "dev")
        return str(v) if v else "dev"
    except Exception:
        return "dev"


PACKAGE_VERSION = read_pyproject_version()
