"""
Low-level system operations such as retrieving host metadata or triggering
reboot/poweroff actions, for both local and remote hosts.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import List, Optional

import psutil
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
    """Devuelve el uptime usando psutil (multiplataforma) y /proc como respaldo."""
    try:
        boot_ts = psutil.boot_time()
        if boot_ts:
            return max(int(time.time() - boot_ts), 0)
    except (OSError, AttributeError, RuntimeError):
        pass

    proc_uptime = Path("/proc/uptime")
    content = _read_file(proc_uptime)
    if content:
        try:
            uptime = float(content.split()[0])
            return int(uptime)
        except (ValueError, IndexError):
            pass
    return 0


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
    os_name = platform.system() or "unknown"
    distro = _read_os_name(os_name)
    device_family = _detect_device_family(os_name)
    metrics_caps = _detect_metrics_capabilities(os_name, device_family)

    return HostInfo(
        hostname=hostname,
        ip=ip_addr,
        arch=arch,
        kernel=kernel,
        os_name=os_name,
        distro=distro,
        device_family=device_family,
        is_raspberry_pi=device_family == "raspberry_pi",
        metrics_capabilities=metrics_caps,
        uptime_seconds=_get_uptime_seconds(),
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


def _read_os_name(system_name: str) -> Optional[str]:
    if system_name.lower() == "linux":
        os_release = Path("/etc/os-release")
        try:
            content = os_release.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        info: dict[str, str] = {}
        for line in content.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            info[key.strip()] = value.strip().strip('"')
        return info.get("PRETTY_NAME") or info.get("NAME")
    if system_name.lower() == "windows":
        return platform.platform()
    if system_name.lower() == "darwin":
        return "macOS " + platform.mac_ver()[0]
    return None


def _detect_device_family(system_name: str) -> str:
    normalized = (system_name or "").lower()
    if normalized == "linux":
        model = _read_file(Path("/sys/firmware/devicetree/base/model")) or _read_file(
            Path("/proc/device-tree/model")
        )
        if model and "raspberry" in model.lower():
            return "raspberry_pi"
        cpuinfo = _read_file(Path("/proc/cpuinfo"))
        if cpuinfo and "raspberry" in cpuinfo.lower():
            return "raspberry_pi"
        return "linux"
    if normalized == "windows":
        return "windows"
    if normalized == "darwin":
        return "macos"
    return normalized or "unknown"


def _detect_metrics_capabilities(system_name: str, device_family: str) -> List[str]:
    caps: List[str] = ["psutil"]
    normalized = (system_name or "").lower()
    if normalized == "linux":
        caps.append("procfs")
    if device_family == "raspberry_pi" and shutil.which("vcgencmd"):
        caps.append("vcgencmd")
    if normalized == "windows":
        if shutil.which("typeperf"):
            caps.append("typeperf")
        if shutil.which("wmic"):
            caps.append("wmic")
    return caps
