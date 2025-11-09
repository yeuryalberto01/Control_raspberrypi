"""
Backward-compatible registry endpoints (under /registry) used by the automated tests.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status

from . import registry, ssh_manager
from .auth import AuthContext, require_role
from .metrics import collect_remote_metrics
from .schemas import DeviceCreate, Metrics


class RegistryDevicePayload(DeviceCreate):
    """Extiende DeviceCreate permitiendo especificar explícitamente un ID."""

    id: Optional[str] = None


router = APIRouter(prefix="/registry", tags=["registry"])


@router.post("/devices")
def registry_upsert_device(
    payload: RegistryDevicePayload,
    _: AuthContext = Depends(require_role("admin")),
):
    """Inserta o actualiza un dispositivo en el registro."""
    device = registry.upsert_device(DeviceCreate(**payload.model_dump(exclude={"id"})), payload.id)
    return {"device": device.model_copy(update={"ssh_pass": None})}


@router.get("/devices")
def registry_list_devices(
    _: AuthContext = Depends(require_role("readonly")),
):
    """Lista los dispositivos registrados."""
    devices = registry.list_devices()
    return {"devices": [device.model_dump() for device in devices]}


@router.delete("/devices/{device_id}")
def registry_delete_device(
    device_id: str,
    _: AuthContext = Depends(require_role("admin")),
):
    """Elimina un dispositivo por ID."""
    if not registry.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True}


@router.get("/{device_id}/proxy/metrics", response_model=Metrics)
def registry_proxy_metrics(
    device_id: str,
    _: AuthContext = Depends(require_role("readonly")),
) -> Metrics:
    """Proxy simple para obtener métricas de un dispositivo remoto."""
    device = registry.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        metrics = collect_remote_metrics(conn)
    except Exception as exc:  # pragma: no cover - relies on SSH connectivity
        raise HTTPException(status_code=502, detail=f"Failed to collect metrics: {exc}") from exc
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return metrics

