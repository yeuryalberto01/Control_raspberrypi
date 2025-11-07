"""
Pydantic schemas shared across the FastAPI application.

These models cover service management, command execution, system metrics,
and host information as described in the project improvement plan.
"""

from __future__ import annotations

from typing import List, Optional

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

    ssh_pass: str = Field(..., description="Clave SSH para el dispositivo.")


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

class Metrics(BaseModel):
    """Informaci??n de m?tricas bosicas del sistema."""

    cpu_percent: float
    cpu_cores: int
    cpu_per_core: List[float] = Field(default_factory=list)
    mem_total_mb: int
    mem_used_mb: int
    mem_available_mb: int
    mem_percent: float
    swap_total_mb: int
    swap_used_mb: int
    disk_total_gb: float
    disk_used_gb: float
    disk_percent: float
    net_rx_kbps: float
    net_tx_kbps: float
    process_count: int
    top_cpu: List[ProcessMetric] = Field(default_factory=list)
    top_mem: List[ProcessMetric] = Field(default_factory=list)
    temp_c: Optional[float] = None
    load1: float
    load5: float
    load15: float
    uptime_seconds: int

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
    uptime_seconds: int




