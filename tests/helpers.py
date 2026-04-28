from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def workspace_tempdir() -> Iterator[str]:
    root = Path.cwd() / ".test_tmp"
    root.mkdir(exist_ok=True)
    directory = root / f"t_{uuid4().hex}"
    directory.mkdir()
    try:
        yield str(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
