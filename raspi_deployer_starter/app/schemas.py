"""
Pydantic schemas shared across the FastAPI application.

These models cover service management, command execution, system metrics,
and host information as described in the project improvement plan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class DeviceBase(BaseModel):
    """Modelo base para un dispositivo con credenciales."""

    name: str = Field(..., description="Nombre descriptivo del dispositivo.")
    base_url: str = Field(
        ..., description="URL base o IP del dispositivo, ej: '192.168.1.50'."
    )
    ssh_user: str = Field(
        "pi", description="Usuario para la conexión SSH al dispositivo."
    )


class Device(DeviceBase):
    """Representa un dispositivo completo en el registro."""

    id: str = Field(..., description="ID único del dispositivo, usualmente un UUID.")
    ssh_pass: Optional[str] = Field(
        None, description="Clave SSH para el dispositivo. Se almacena en el YAML."
    )


class DeviceCreate(DeviceBase):
    """Modelo para crear un nuevo dispositivo. La clave es obligatoria."""

    ssh_pass: Optional[str] = Field(
        None,
        description="Clave SSH para el dispositivo. Opcional si se manejarán llaves o será agregado más tarde.",
    )


class DeviceRegistry(BaseModel):
    """Modela la estructura del archivo de registro de dispositivos (devices.yaml)."""

    devices: List[Device] = []


class ServiceAction(BaseModel):
    """Represents an action to be performed over a systemd unit."""

    name: str = Field(..., description="Nombre del servicio systemd a gestionar.")
    action: str = Field(
        ..., description="Acción a ejecutar: start | stop | restart | status."
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("El nombre del servicio no puede estar vacío.")
        return value.strip()

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"start", "stop", "restart", "status"}:
            raise ValueError("Acción inválida; usa start, stop, restart o status.")
        return normalized


class ServiceStatus(BaseModel):
    """Structured info for service status listings."""

    name: str
    active_state: str
    sub_state: str
    result: Optional[str] = None
    description: Optional[str] = None


class ExecCommand(BaseModel):
    """Payload para ejecutar comandos locales controlados."""

    command: str = Field(
        ...,
        description="Comando a ejecutar en la Raspberry Pi. Se sanitiza antes de ejecutar.",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        sanitized = value.strip()
        if not sanitized:
            raise ValueError("El comando no puede estar vacío.")
        if "\n" in sanitized or "\r" in sanitized:
            raise ValueError("El comando no puede contener saltos de línea.")
        return sanitized


class ExecResult(BaseModel):
    """Respuesta estándar para la ejecución de comandos."""

    code: int = Field(..., description="Código de salida del proceso.")
    stdout: str = Field("", description="Salida estándar capturada.")
    stderr: str = Field("", description="Salida de error capturada.")



class ProcessMetric(BaseModel):
    """Informacion compacta sobre un proceso en ejecucion."""

    pid: int
    name: str
    cpu_percent: float
    mem_percent: float


class DiskPartitionMetric(BaseModel):
    """Uso detallado de un punto de montaje especifico."""

    device: str
    mountpoint: str
    fstype: str
    total_gb: float
    used_gb: float
    percent: float


class NetworkInterfaceMetric(BaseModel):
    """Estado basico de una interfaz de red local."""

    name: str
    mac: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    is_up: bool = False
    speed_mbps: Optional[float] = None
    mtu: Optional[int] = None


class Metrics(BaseModel):
    """Informaci��n de m��tricas b��sicas y extendidas del sistema."""

    cpu_percent: float
    cpu_cores: int
    cpu_per_core: List[float] = Field(default_factory=list)
    cpu_freq_current_mhz: Optional[float] = None
    cpu_freq_min_mhz: Optional[float] = None
    cpu_freq_max_mhz: Optional[float] = None
    mem_total_mb: int
    mem_used_mb: int
    mem_available_mb: int
    mem_free_mb: int
    mem_percent: float
    mem_cached_mb: Optional[int] = None
    mem_buffers_mb: Optional[int] = None
    swap_total_mb: int
    swap_used_mb: int
    swap_free_mb: int
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_percent: float
    disk_partitions: List[DiskPartitionMetric] = Field(default_factory=list)
    net_rx_kbps: float
    net_tx_kbps: float
    net_interfaces: List[NetworkInterfaceMetric] = Field(default_factory=list)
    process_count: int
    top_cpu: List[ProcessMetric] = Field(default_factory=list)
    top_mem: List[ProcessMetric] = Field(default_factory=list)
    temp_c: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    fan_speed_rpm: Optional[int] = None
    extra_temperatures: Dict[str, float] = Field(default_factory=dict)
    load1: float
    load5: float
    load15: float
    uptime_seconds: int


class DockerPortMapping(BaseModel):
    """Asociac��n de puertos expuestos por un contenedor."""

    container_port: str
    protocol: str
    host_ip: Optional[str] = None
    host_port: Optional[str] = None


class DockerContainerSummary(BaseModel):
    """Datos de uso y estado de un contenedor Docker."""

    id: str
    name: str
    image: str
    status: str
    state: str
    created: datetime
    ports: List[DockerPortMapping] = Field(default_factory=list)
    cpu_percent: Optional[float] = None
    mem_usage_mb: Optional[float] = None
    mem_percent: Optional[float] = None


class DockerPortRequest(BaseModel):
    """Solicitud de mapeo de puertos al arrancar un contenedor."""

    container_port: str = Field(..., description="Puerto interno, ej: '80' o '80/tcp'.")
    protocol: str = Field(
        "tcp",
        description="Protocolo a exponer (tcp/udp). Se ignora si container_port ya incluye '/proto'.",
    )
    host_ip: Optional[str] = Field(
        None,
        description="IP del host donde se expondr�� el puerto. Omite para usar 0.0.0.0.",
    )
    host_port: Optional[int] = Field(
        None,
        description="Puerto del host. Deja vac��o para que Docker asigne uno disponible.",
    )

    @field_validator("container_port")
    @classmethod
    def validate_container_port(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El puerto del contenedor no puede estar vacio.")
        return normalized

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"tcp", "udp"}:
            raise ValueError("El protocolo debe ser tcp o udp.")
        return normalized


class DockerRunRequest(BaseModel):
    """Parametros basicos para crear un contenedor."""

    image: str = Field(..., description="Imagen a ejecutar, ej: 'nginx:latest'.")
    name: Optional[str] = Field(None, description="Nombre opcional del contenedor.")
    command: Optional[Union[str, List[str]]] = Field(
        None, description="Comando/entrypoint opcional."
    )
    env: Dict[str, str] = Field(
        default_factory=dict, description="Variables de entorno adicionales."
    )
    ports: List[DockerPortRequest] = Field(
        default_factory=list,
        description="Puertos a exponer. Deja host_port vacio para asignacion automatica.",
    )
    restart_policy: Optional[str] = Field(
        None, description="Politica de reinicio (no, on-failure, unless-stopped, always)."
    )
    auto_remove: bool = Field(
        False, description="Si es True, Docker eliminara el contenedor al detenerse."
    )
    privileged: bool = Field(False, description="Ejecuta el contenedor en modo privilegiado.")
    detach: bool = Field(
        True,
        description="Debe permanecer True para ejecutar en segundo plano y devolver un resumen.",
    )
    network: Optional[str] = Field(
        None, description="Nombre de la red Docker donde conectar el contenedor."
    )
    workdir: Optional[str] = Field(None, description="Directorio de trabajo dentro del contenedor.")

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("La imagen es obligatoria.")
        return normalized

    @field_validator("detach")
    @classmethod
    def enforce_detach(cls, value: bool) -> bool:
        if not value:
            raise ValueError("detach debe ser True para usar este endpoint.")
        return value


class DockerInfo(BaseModel):
    """Resumen de la instancia Docker local."""

    server_version: str
    os: str
    architecture: str
    kernel_version: Optional[str] = None
    containers_total: int
    containers_running: int
    containers_stopped: int
    containers_paused: int
    images: int
    cgroup_driver: Optional[str] = None
    swarm_active: bool = False


class PortainerEndpoint(BaseModel):
    """Endpoint definido en Portainer."""

    id: int
    name: str
    status: str
    url: Optional[str] = None
    group_id: Optional[int] = None


class PortainerStack(BaseModel):
    """Stack gestionado por Portainer."""

    id: int
    name: str
    endpoint_id: int
    status: Optional[str] = None
    created: Optional[int] = None
    updated: Optional[int] = None
    project_path: Optional[str] = None

class ServiceStatusRequest(BaseModel):
    """Request payload for getting multiple service statuses."""

    services: List[str] = Field(
        ..., min_length=1, description="Lista de servicios a consultar."
    )


class HostInfo(BaseModel):
    """Información general del host."""

    hostname: str
    ip: str
    arch: str
    kernel: str
    os_name: str = Field(..., description="Nombre del sistema operativo detectado (platform.system()).")
    distro: Optional[str] = Field(None, description="Nombre descriptivo de la distribución/SO si está disponible.")
    device_family: str = Field(..., description="Clasificación del dispositivo (raspberry_pi, windows, linux, etc).")
    is_raspberry_pi: bool = Field(False, description="Indica si se identificó como Raspberry Pi.")
    metrics_capabilities: List[str] = Field(
        default_factory=list,
        description="Fuentes/herramientas disponibles para leer el rendimiento del sistema.",
    )
    uptime_seconds: int




