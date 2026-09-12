"""Small, dependency-free helpers for durable repository-backed JSON state."""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: str | Path, payload: Any, *, default: Any = None) -> Path:
    """Atomically replace ``path`` with UTF-8 JSON.

    Readers see either the previous complete document or the new complete
    document, never a partially written state file after an interrupted run.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=default)
            handle.write("\n")
        os.replace(temporary, destination)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    return destination
