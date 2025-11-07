"""
API endpoints for managing the device registry.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Response, status, Header
from invoke import UnexpectedExit

from . import registry
from . import ssh_manager
# from .auth import get_current_active_user  # Disabled for local use
from .metrics import collect_remote_metrics
from .schemas import Device, DeviceCreate, Metrics, ServiceAction, ServiceStatus, ServiceStatusRequest, ExecResult
# from .schemas import User  # Disabled for local use
from .services import list_remote_available_services, manage_remote_service, get_multiple_remote_status
from .system_ops import remote_reboot, remote_poweroff

router = APIRouter(
    prefix="/devices",
    tags=["Devices"],
    # dependencies=[Depends(get_current_active_user)],  # Disabled for local use
)


@router.get("/", response_model=List[Device])
def get_all_devices(
    # current_user: User = Depends(get_current_active_user),  # Disabled for local use
):
    """Lists all registered devices."""
    return registry.list_devices()


@router.post("/", response_model=Device, status_code=status.HTTP_201_CREATED)
def create_new_device(device_in: DeviceCreate
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
):
    """Registers a new device."""
    # In a real app, you might check for duplicate names or base_urls
    new_device = registry.upsert_device(device_in)
    return new_device


@router.get("/{device_id}", response_model=Device)
def get_single_device(device_id: str
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
):
    """Gets detailed information for a single device."""
    device = registry.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # Return device without showing password
    return device.model_copy(update={"ssh_pass": None})


@router.put("/{device_id}", response_model=Device)
def update_existing_device(
    device_id: str, device_in: DeviceCreate
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
):
    """Updates a device's information."""
    existing_device = registry.get_device(device_id)
    if not existing_device:
        raise HTTPException(status_code=404, detail="Device not found")
    updated_device = registry.upsert_device(device_in, device_id)
    return updated_device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_device(device_id: str
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
):
    """Deletes a device from the registry."""
    if not registry.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{device_id}/metrics", response_model=Metrics)
def get_remote_device_metrics(
    device_id: str,
    # current_user: User = Depends(get_current_active_user),  # Disabled for local use
):
    """Gets system metrics from a remote device via SSH."""
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        metrics = collect_remote_metrics(conn)
    except UnexpectedExit as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"A command failed on the remote host: {e.result.command}",
        ) from e
    except Exception as e:  # pylint: disable=broad-except
        # Catches connection errors from the manager and others
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"SSH connection failed: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return metrics


@router.get("/{device_id}/services", response_model=List[str])
def get_remote_service_list(
    device_id: str
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
) -> List[str]:
    """Lists available services on a remote device."""
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        services = list_remote_available_services(conn)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to list services: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return services


@router.post("/{device_id}/service", response_model=ExecResult)
def manage_remote_service_endpoint(
    device_id: str, action: ServiceAction
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
) -> ExecResult:
    """Executes a systemd action (start, stop, restart) on a service on a remote device."""
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        result = manage_remote_service(conn, action)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except UnexpectedExit as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Command failed on remote host: {e.result.command} -> {e.result.stderr}",
        ) from e
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"SSH operation failed: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return result


@router.post("/{device_id}/services/status", response_model=List[ServiceStatus])
def get_multiple_remote_services_status(
    device_id: str, payload: ServiceStatusRequest
    # , current_user: User = Depends(get_current_active_user)  # Disabled for local use
) -> List[ServiceStatus]:
    """Gets the status of multiple services on a remote device."""
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        statuses = get_multiple_remote_status(conn, payload.services)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to get service statuses: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return statuses


@router.post("/{device_id}/system/reboot", response_model=ExecResult)
def remote_system_reboot(
    device_id: str,
    # current_user: User = Depends(get_current_active_user),  # Disabled for local use
    confirm: Optional[str] = Header(None, alias="X-Confirm"),
) -> ExecResult:
    """Triggers a system reboot on a remote device."""
    if confirm != "REBOOT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm reboot by sending X-Confirm: REBOOT",
        )
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        result = remote_reboot(conn)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to reboot device: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return result


@router.post("/{device_id}/system/poweroff", response_model=ExecResult)
def remote_system_poweroff(
    device_id: str,
    # current_user: User = Depends(get_current_active_user),  # Disabled for local use
    confirm: Optional[str] = Header(None, alias="X-Confirm"),
) -> ExecResult:
    """Triggers a system poweroff on a remote device."""
    if confirm != "POWEROFF":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm poweroff by sending X-Confirm: POWEROFF",
        )
    try:
        conn = ssh_manager.get_ssh_connection(device_id)
        result = remote_poweroff(conn)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to poweroff device: {e}"
        ) from e
    finally:
        if "conn" in locals() and conn.is_connected:
            conn.close()
    return result
