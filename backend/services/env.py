"""Reads backend/.env into the environment.

Django does not load .env files, and `services` deliberately has no Django
dependency, so it cannot borrow one from settings either. This is a dozen lines
rather than another package, and it is intentionally conservative: real
environment variables always win, so a value set by Render or Railway is never
overwritten by a stale local file.
"""

import os
from pathlib import Path
from threading import Lock

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_lock = Lock()
_loaded = False


def load_env_file(path: Path = ENV_PATH) -> None:
    """Load KEY=value lines from .env, once per process. Never overrides."""
    global _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        if not path.is_file():
            return

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def get(name: str, default: str = "") -> str:
    """An environment variable, loading the .env file first if need be."""
    load_env_file()
    return os.environ.get(name, default)
