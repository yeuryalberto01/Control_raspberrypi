"""
Endpoints para interactuar con el daemon Docker local.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import docker
from docker.errors import APIError, DockerException, NotFound
from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import AuthContext, require_role
from .deps import Settings, get_settings
from .schemas import (
    DockerContainerSummary,
    DockerInfo,
    DockerPortMapping,
    DockerPortRequest,
    DockerRunRequest,
)

router = APIRouter(prefix="/docker", tags=["docker"])


def _bytes_to_mb(value: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    return round(value / (1024**2), 2)


def _parse_created(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except ValueError:
                pass
    return datetime.now(tz=timezone.utc)


def _parse_ports(raw_ports: Optional[Dict[str, Optional[List[Dict[str, str]]]]]) -> List[DockerPortMapping]:
    if not raw_ports:
        return []
    ports: List[DockerPortMapping] = []
    for port_key, mappings in raw_ports.items():
        container_port, _, proto = port_key.partition("/")
        protocol = proto or "tcp"
        if not mappings:
            ports.append(
                DockerPortMapping(
                    container_port=container_port,
                    protocol=protocol,
                    host_ip=None,
                    host_port=None,
                )
            )
            continue
        for mapping in mappings:
            ports.append(
                DockerPortMapping(
                    container_port=container_port,
                    protocol=protocol,
                    host_ip=mapping.get("HostIp"),
                    host_port=mapping.get("HostPort"),
                )
            )
    return ports


def _cpu_percent(stats: Dict[str, Any]) -> Optional[float]:
    try:
        cpu_stats = stats["cpu_stats"]
        precpu = stats.get("precpu_stats") or {}
        cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu.get("cpu_usage", {}).get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
        if cpu_delta <= 0 or system_delta <= 0:
            return None
        online = cpu_stats.get("online_cpus") or len(cpu_stats["cpu_usage"].get("percpu_usage", [])) or 1
        return round((cpu_delta / system_delta) * online * 100.0, 2)
    except (KeyError, ZeroDivisionError, TypeError):
        return None


def _memory_stats(stats: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    try:
        usage = stats["memory_stats"]["usage"]
        limit = stats["memory_stats"].get("limit") or 0
        usage_mb = _bytes_to_mb(usage)
        mem_percent = round((usage / limit) * 100.0, 2) if limit else None
        return usage_mb, mem_percent
    except (KeyError, TypeError, ZeroDivisionError):
        return None, None


def _image_name(container: docker.models.containers.Container) -> str:
    config_image = container.attrs.get("Config", {}).get("Image")
    if config_image:
        return config_image
    tags = getattr(container.image, "tags", None) or []
    if tags:
        return tags[0]
    short_id = getattr(container.image, "short_id", None)
    if short_id:
        return short_id
    return container.id[:12]


def _summarize_container(container: docker.models.containers.Container) -> DockerContainerSummary:
    stats: Optional[Dict[str, Any]] = None
    try:
        stats = container.stats(stream=False)
    except DockerException:
        stats = None
    cpu_percent = _cpu_percent(stats) if stats else None
    mem_usage_mb, mem_percent = _memory_stats(stats) if stats else (None, None)
    ports = _parse_ports(container.attrs.get("NetworkSettings", {}).get("Ports"))
    return DockerContainerSummary(
        id=container.id,
        name=container.name,
        image=_image_name(container),
        status=container.status,
        state=container.attrs.get("State", {}).get("Status", container.status),
        created=_parse_created(container.attrs.get("Created")),
        ports=ports,
        cpu_percent=cpu_percent,
        mem_usage_mb=mem_usage_mb,
        mem_percent=mem_percent,
    )


def _normalize_container_port(request_port: DockerPortRequest) -> str:
    container_port = request_port.container_port
    if "/" in container_port:
        port_part, _, proto = container_port.partition("/")
        protocol = proto or request_port.protocol
    else:
        port_part = container_port
        protocol = request_port.protocol
    return f"{port_part}/{protocol}"


def _build_port_bindings(ports: List[DockerPortRequest]) -> Dict[str, object]:
    bindings: Dict[str, object] = {}
    for port in ports:
        key = _normalize_container_port(port)
        host_port = port.host_port if port.host_port and port.host_port > 0 else None
        if port.host_ip and host_port is not None:
            binding: object = (port.host_ip, host_port)
        elif port.host_ip:
            binding = (port.host_ip,)
        elif host_port is not None:
            binding = host_port
        else:
            binding = None  # Permite que Docker asigne el puerto
        bindings[key] = binding
    return bindings


@contextlib.contextmanager
def _docker_client(settings: Settings):
    client: Optional[docker.DockerClient] = None
    try:
        if settings.docker_host:
            client = docker.DockerClient(base_url=settings.docker_host)
        else:
            client = docker.from_env()
        yield client
    except DockerException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Docker: {exc}",
        ) from exc
    finally:
        if client:
            with contextlib.suppress(Exception):
                client.close()


def _fetch_docker_info(settings: Settings) -> DockerInfo:
    with _docker_client(settings) as client:
        info = client.info()
    swarm = info.get("Swarm") or {}
    swarm_state = swarm.get("LocalNodeState") if isinstance(swarm, dict) else swarm
    return DockerInfo(
        server_version=info.get("ServerVersion", "unknown"),
        os=info.get("OperatingSystem", "linux"),
        architecture=info.get("Architecture", ""),
        kernel_version=info.get("KernelVersion"),
        containers_total=info.get("Containers", 0),
        containers_running=info.get("ContainersRunning", 0),
        containers_stopped=info.get("ContainersStopped", 0),
        containers_paused=info.get("ContainersPaused", 0),
        images=info.get("Images", 0),
        cgroup_driver=info.get("CgroupDriver"),
        swarm_active=bool(swarm_state) and str(swarm_state).lower() not in {"inactive", "pending"},
    )


def _list_containers(settings: Settings, show_all: bool) -> List[DockerContainerSummary]:
    with _docker_client(settings) as client:
        containers = client.containers.list(all=show_all)
        return [_summarize_container(container) for container in containers]


def _apply_action(settings: Settings, container_id: str, action: Literal["start", "stop", "restart"]) -> DockerContainerSummary:
    with _docker_client(settings) as client:
        try:
            container = client.containers.get(container_id)
        except NotFound as exc:
            raise HTTPException(status_code=404, detail="Contenedor no encontrado.") from exc
        try:
            if action == "start":
                container.start()
            elif action == "stop":
                container.stop()
            elif action == "restart":
                container.restart()
        except (APIError, DockerException) as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo {action} el contenedor: {exc}") from exc
        container.reload()
        return _summarize_container(container)


def _run_container(settings: Settings, payload: DockerRunRequest) -> DockerContainerSummary:
    port_bindings = _build_port_bindings(payload.ports)
    run_kwargs: Dict[str, Any] = {
        "name": payload.name,
        "command": payload.command,
        "environment": payload.env or None,
        "ports": port_bindings or None,
        "auto_remove": payload.auto_remove,
        "privileged": payload.privileged,
        "detach": True,
        "network": payload.network,
        "working_dir": payload.workdir,
    }
    run_kwargs = {k: v for k, v in run_kwargs.items() if v not in (None, {})}
    if payload.restart_policy:
        run_kwargs["restart_policy"] = {"Name": payload.restart_policy}

    with _docker_client(settings) as client:
        try:
            container = client.containers.run(payload.image, **run_kwargs)
        except DockerException as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo crear el contenedor: {exc}") from exc
        container.reload()
        return _summarize_container(container)


@router.get("/info", response_model=DockerInfo)
async def docker_info(
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> DockerInfo:
    """Devuelve informacion del daemon Docker."""
    return await asyncio.to_thread(_fetch_docker_info, settings)


@router.get("/containers", response_model=List[DockerContainerSummary])
async def docker_containers(
    all_containers: bool = Query(True, description="Incluir contenedores detenidos."),
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> List[DockerContainerSummary]:
    """Lista contenedores locales con metricas basicas."""
    return await asyncio.to_thread(_list_containers, settings, all_containers)


@router.post("/containers/{container_id}/{action}", response_model=DockerContainerSummary)
async def docker_container_action(
    container_id: str,
    action: Literal["start", "stop", "restart"],
    _: AuthContext = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
) -> DockerContainerSummary:
    """Ejecuta una accion simple sobre un contenedor."""
    return await asyncio.to_thread(_apply_action, settings, container_id, action)


@router.post("/containers/run", response_model=DockerContainerSummary, status_code=201)
async def docker_run_container(
    payload: DockerRunRequest,
    _: AuthContext = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
) -> DockerContainerSummary:
    """
    Crea un contenedor nuevo permitiendo que Docker asigne puertos automaticamente si el host_port queda vacio.
    """
    return await asyncio.to_thread(_run_container, settings, payload)
