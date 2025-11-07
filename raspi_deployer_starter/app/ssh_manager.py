"""
Centralized SSH connection management.
"""

from fastapi import HTTPException, status
from fabric import Connection

from . import registry
# from .schemas import User  # Disabled for local use


def get_ssh_connection(device_id: str) -> Connection:
    """_summary_

    Args:
        device_id (str): The ID of the device to connect to.

    Raises:
        HTTPException: If the device is not found or has no password.

    Returns:
        Connection: A Fabric Connection object ready to be used.
    """
    device = registry.get_device(device_id)
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if not device.ssh_pass:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device '{device.name}' has no SSH password configured.",
        )

    connect_kwargs = {"password": device.ssh_pass}

    return Connection(
        host=device.base_url,
        user=device.ssh_user,
        connect_kwargs=connect_kwargs,
    )
