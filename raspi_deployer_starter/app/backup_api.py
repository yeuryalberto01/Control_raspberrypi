"""
Helpers to generate configuration backups as tarballs.
"""

from __future__ import annotations

import os
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable, List

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

INCLUDE_PATHS: List[str] = [
    "config/whitelist.yaml",
    "data/devices.yaml",
    ".env",
    "/var/log",
]


def _iter_existing_paths(paths: Iterable[str]) -> Iterable[Path]:
    for item in paths:
        try:
            normalized = Path(item).resolve(strict=True)
        except FileNotFoundError:
            continue
        yield normalized


async def make_backup_tar() -> FileResponse:
    try:
        tmpdir = tempfile.mkdtemp(prefix="pi-backup-")
        tar_path = Path(tmpdir) / "pi_backup.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            for path in _iter_existing_paths(INCLUDE_PATHS):
                arcname = path.name
                tar.add(path, arcname=arcname, recursive=True)
    except (OSError, tarfile.TarError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _cleanup(path: Path):
        try:
            path.unlink()
        except OSError:
            pass
        try:
            path.parent.rmdir()
        except OSError:
            pass

    return FileResponse(
        tar_path,
        filename="pi_backup.tar.gz",
        media_type="application/gzip",
        background=BackgroundTask(_cleanup, tar_path),
    )
