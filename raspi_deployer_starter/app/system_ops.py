"""
Low-level system operations such as retrieving host metadata or triggering
reboot/poweroff actions, for both local and remote hosts.
"""

from __future__ import annotations

import os
import platform
import socket
from pathlib import Path
from typing import Optional

from fabric import Connection

from .exec_local import run_command_async
from .schemas import ExecResult, HostInfo

REBOOT_BIN = "/sbin/reboot"
POWEROFF_BIN = "/sbin/poweroff"


def _read_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def _get_uptime_seconds() -> int:
    proc_uptime = Path("/proc/uptime")
    content = _read_file(proc_uptime)
    if not content:
        return 0
    try:
        uptime = float(content.split()[0])
    except (ValueError, IndexError):
        return 0
    return int(uptime)


def _get_primary_ip() -> str:
    """
    Obtiene la IP principal tratando de establecer una conexión UDP "falsa"
    hacia Internet, lo cual no envía tráfico pero permite conocer la interfaz.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def collect_host_info() -> HostInfo:
    """Genera la información básica del host para el endpoint /info."""
    hostname = socket.gethostname()
    ip_addr = _get_primary_ip()
    arch = platform.machine()
    kernel = platform.release()
    uptime_seconds = _get_uptime_seconds()

    return HostInfo(
        hostname=hostname,
        ip=ip_addr,
        arch=arch,
        kernel=kernel,
        uptime_seconds=uptime_seconds,
    )


async def reboot() -> ExecResult:
    """Dispara un reinicio del sistema LOCAL."""
    return await run_command_async([REBOOT_BIN])


async def poweroff() -> ExecResult:
    """Apaga el sistema LOCAL."""
    return await run_command_async([POWEROFF_BIN])


async def remote_reboot(conn: Connection) -> ExecResult:
    """Triggers a system reboot on a remote device via SSH."""
    result = await conn.sudo(REBOOT_BIN, hide=True, warn=True)
    return ExecResult(
        code=result.exited,
        stdout=result.stdout,
        stderr=result.stderr,
    )


async def remote_poweroff(conn: Connection) -> ExecResult:
    """Triggers a system poweroff on a remote device via SSH."""
    result = await conn.sudo(POWEROFF_BIN, hide=True, warn=True)
    return ExecResult(
        code=result.exited,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def get_uptime_seconds() -> int:
    """Expuesto para otros módulos que necesitan el uptime."""
    return _get_uptime_seconds()
