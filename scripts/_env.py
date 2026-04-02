"""Minimal .env loader for local provider test scripts."""

from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


def load_env(path: Path | None = None) -> dict[str, str]:
    """Load key/value pairs from a simple .env file."""
    env_path = path or ENV_PATH
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env(name: str, default: str | None = None) -> str | None:
    """Return one value from .env or a provided default."""
    return load_env().get(name, default)


def require_env(name: str) -> str:
    """Return a required value from .env or raise a friendly error."""
    value = get_env(name)
    if value is None or value == "":
        raise SystemExit(
            f"Missing {name} in {ENV_PATH}. Fill in your .env before running this script."
        )
    return value
