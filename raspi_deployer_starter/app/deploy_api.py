"""
Deployment utilities for uploading archives or pulling from Git, for both local and remote hosts.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from fabric import Connection

from .config_whitelist import allowed_deploy_target, deploy_service_to_restart
from .exec_local import run_command_async
from .schemas import ExecResult

SYSTEMCTL_BIN = "/bin/systemctl"


def _ensure_target_allowed(target_dir: str) -> Path:
    target_dir = os.path.abspath(target_dir)
    if not allowed_deploy_target(target_dir):
        raise HTTPException(status_code=403, detail="Destino no permitido")
    path = Path(target_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="La ruta destino no existe")
    return path


async def _restart_service_if_needed() -> None:
    service = deploy_service_to_restart()
    if not service:
        return
    await run_command_async([SYSTEMCTL_BIN, "restart", service])


async def _remote_restart_service_if_needed(conn: Connection) -> None:
    service = deploy_service_to_restart()
    if not service:
        return
    await conn.sudo(f"{SYSTEMCTL_BIN} restart {service}", hide=True, warn=True)


async def deploy_archive(upload: UploadFile, target_dir: str) -> dict:
    """Deploys an archive to a LOCAL target directory."""
    target_path = _ensure_target_allowed(target_dir)

    suffix = Path(upload.filename or "package.zip").suffix.lower()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir) / (upload.filename or "package")
        try:
            with open(tmpfile, "wb") as buffer:
                while chunk := await upload.read(1024 * 1024):
                    buffer.write(chunk)
        finally:
            await upload.close()

        # Determine archive format
        try:
            shutil.unpack_archive(str(tmpfile), str(target_path))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Formato de archivo no soportado: {suffix}"
            ) from exc

    await _restart_service_if_needed()
    return {"ok": True, "target": str(target_path)}


async def remote_deploy_archive(conn: Connection, upload: UploadFile, target_dir: str) -> dict:
    """Deploys an archive to a REMOTE target directory via SSH."""
    # Ensure target is allowed (local whitelist check)
    _ = _ensure_target_allowed(target_dir)

    suffix = Path(upload.filename or "package.zip").suffix.lower()

    with tempfile.TemporaryDirectory() as tmpdir:
        local_tmp_file = Path(tmpdir) / (upload.filename or "package")
        try:
            # Save uploaded file locally first
            with open(local_tmp_file, "wb") as buffer:
                while chunk := await upload.read(1024 * 1024):
                    buffer.write(chunk)
        finally:
            await upload.close()

        remote_tmp_path = f"/tmp/{local_tmp_file.name}"
        # Transfer file to remote
        await conn.put(str(local_tmp_file), remote=remote_tmp_path)

        # Unpack and move on remote
        remote_unpack_cmd = f"sudo tar -xzf {remote_tmp_path} -C {target_dir}" # Assuming tar.gz
        if suffix == ".zip":
            remote_unpack_cmd = f"sudo unzip {remote_tmp_path} -d {target_dir}"
        elif suffix == ".tar":
            remote_unpack_cmd = f"sudo tar -xf {remote_tmp_path} -C {target_dir}"

        unpack_result = await conn.sudo(remote_unpack_cmd, hide=True, warn=True)
        if not unpack_result.ok:
            raise HTTPException(
                status_code=500, detail=f"Remote unpack failed: {unpack_result.stderr}"
            )
        
        # Clean up remote temp file
        await conn.run(f"rm {remote_tmp_path}", hide=True, warn=True)

    await _remote_restart_service_if_needed(conn)
    return {"ok": True, "target": target_dir}


async def deploy_git_pull(target_dir: str, branch: Optional[str] = None) -> dict:
    """Executes git pull on a LOCAL target directory."""
    target_path = _ensure_target_allowed(target_dir)

    cmd = ["git", "-C", str(target_path), "pull"]
    if branch:
        cmd.extend(["origin", branch])

    result = await run_command_async(cmd)
    if result.code != 0:
        raise HTTPException(
            status_code=500, detail=result.stderr or "git pull falló"
        )

    await _restart_service_if_needed()
    return {"ok": True, "stdout": result.stdout}


async def remote_deploy_git_pull(conn: Connection, target_dir: str, branch: Optional[str] = None) -> dict:
    """Executes git pull on a REMOTE target directory via SSH."""
    # Ensure target is allowed (local whitelist check)
    _ = _ensure_target_allowed(target_dir)

    cmd = ["git", "-C", target_dir, "pull"]
    if branch:
        cmd.extend(["origin", branch])

    result = await conn.sudo(cmd, hide=True, warn=True)
    if not result.ok:
        raise HTTPException(
            status_code=500, detail=result.stderr or "Remote git pull failed"
        )

    await _remote_restart_service_if_needed(conn)
    return {"ok": True, "stdout": result.stdout}
