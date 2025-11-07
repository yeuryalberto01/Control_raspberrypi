"""
systemctl helpers to manage services and query their status on remote devices.
"""

from __future__ import annotations

from typing import Iterable, List

from fabric import Connection

from .config_whitelist import allowed_service, list_services
from .schemas import ExecResult, ServiceAction, ServiceStatus

SYSTEMCTL_BIN = "/bin/systemctl"


def _parse_systemctl_show(output: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


async def manage_remote_service(conn: Connection, action: ServiceAction) -> ExecResult:
    """Execute the requested systemctl action over an allowed service on a remote device."""
    # Whitelist check is done locally based on the backend's config
    if not allowed_service(action.name):
        raise PermissionError("Servicio no permitido por la whitelist.")

    cmd = [SYSTEMCTL_BIN, action.action, action.name]
    result = await conn.run(cmd, hide=True, warn=True)

    return ExecResult(
        code=result.exited,
        stdout=result.stdout,
        stderr=result.stderr,
    )


async def get_remote_service_status(conn: Connection, name: str) -> ServiceStatus:
    """Return structured status information for a single service on a remote device."""
    if not allowed_service(name):
        raise PermissionError("Servicio no permitido por la whitelist.")

    cmd = [
        SYSTEMCTL_BIN,
        "show",
        name,
        "--property=ActiveState,SubState,Result,Description",
    ]
    result = await conn.run(cmd, hide=True, warn=True)
    if result.exited != 0:
        raise RuntimeError(result.stderr or "No se pudo obtener el estado del servicio.")

    data = _parse_systemctl_show(result.stdout)
    return ServiceStatus(
        name=name,
        active_state=data.get("ActiveState", "unknown"),
        sub_state=data.get("SubState", ""),
        result=data.get("Result"),
        description=data.get("Description"),
    )


async def get_multiple_remote_status(conn: Connection, names: Iterable[str]) -> List[ServiceStatus]:
    statuses: List[ServiceStatus] = []
    for name in names:
        try:
            status = await get_remote_service_status(conn, name)
            statuses.append(status)
        except (PermissionError, RuntimeError) as exc:
            # Append a status indicating failure for this specific service
            statuses.append(ServiceStatus(
                name=name,
                active_state="failed",
                sub_state="",
                result="error",
                description=str(exc),
            ))
    return statuses


async def list_remote_available_services(conn: Connection) -> List[str]:
    """
    Returns the services the API is allowed to manage on a remote device.

    If a whitelist is configured, it is returned as-is. Otherwise, systemctl is
    queried remotely to provide a list of loaded service units.
    """
    whitelist = list_services()
    if whitelist:
        return whitelist

    cmd = [
        SYSTEMCTL_BIN,
        "list-unit-files",
        "--type=service",
        "--no-legend",
        "--no-pager",
    ]
    result = await conn.run(cmd, hide=True, warn=True)
    if result.exited != 0:
        raise RuntimeError(result.stderr or "No se pudo listar servicios.")

    services: List[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts:
            services.append(parts[0])

    return services


# Local service management functions (for the host system)

async def manage_service(action: ServiceAction) -> ExecResult:
    """Execute systemctl action on the local system."""
    if not allowed_service(action.name):
        raise PermissionError("Servicio no permitido por la whitelist.")

    from .exec_local import run_command_async
    cmd = [SYSTEMCTL_BIN, action.action, action.name]
    result = await run_command_async(cmd)
    return ExecResult(
        code=result.code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


async def get_multiple_status(names: Iterable[str]) -> List[ServiceStatus]:
    """Get status for multiple services on the local system."""
    statuses: List[ServiceStatus] = []
    for name in names:
        try:
            status = await get_local_service_status(name)
            statuses.append(status)
        except (PermissionError, RuntimeError) as exc:
            statuses.append(ServiceStatus(
                name=name,
                active_state="failed",
                sub_state="",
                result="error",
                description=str(exc),
            ))
    return statuses


async def get_local_service_status(name: str) -> ServiceStatus:
    """Get status for a single service on the local system."""
    if not allowed_service(name):
        raise PermissionError("Servicio no permitido por la whitelist.")

    from .exec_local import run_command_async
    cmd = [
        SYSTEMCTL_BIN,
        "show",
        name,
        "--property=ActiveState,SubState,Result,Description",
    ]
    result = await run_command_async(cmd)
    if result.code != 0:
        raise RuntimeError(result.stderr or "No se pudo obtener el estado del servicio.")

    data = _parse_systemctl_show(result.stdout)
    return ServiceStatus(
        name=name,
        active_state=data.get("ActiveState", "unknown"),
        sub_state=data.get("SubState", ""),
        result=data.get("Result"),
        description=data.get("Description"),
    )


async def list_available_services() -> List[str]:
    """List available services on the local system."""
    whitelist = list_services()
    if whitelist:
        return whitelist

    from .exec_local import run_command_async
    cmd = [
        SYSTEMCTL_BIN,
        "list-unit-files",
        "--type=service",
        "--no-legend",
        "--no-pager",
    ]
    result = await run_command_async(cmd)
    if result.code != 0:
        raise RuntimeError(result.stderr or "No se pudo listar servicios.")

    services: List[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts:
            services.append(parts[0])

    return services
