"""
Device registry utilities to support multi-Pi management.

Uses a YAML file as a simple database, now modeled with Pydantic
for type safety and clear structure.
"""

from __future__ import annotations

import os
import uuid
from typing import List, Optional

import yaml
from pydantic import ValidationError

from .deps import get_settings
from .schemas import Device, DeviceCreate, DeviceRegistry


def _registry_path() -> str:
    """Returns the absolute path to the devices.yaml registry file."""
    return get_settings().devices_reg_path


def _load_registry() -> DeviceRegistry:
    """Loads the device registry from YAML into Pydantic models."""
    path = _registry_path()
    if not os.path.exists(path):
        return DeviceRegistry(devices=[])

    try:
        with open(path, "r", encoding="utf-8") as handler:
            data = yaml.safe_load(handler) or {}
        return DeviceRegistry.model_validate(data)
    except (yaml.YAMLError, ValidationError):
        # If file is corrupt or schema is wrong, start fresh
        return DeviceRegistry(devices=[])


def _save_registry(registry: DeviceRegistry) -> None:
    """Saves the Pydantic model registry back to the YAML file."""
    path = _registry_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handler:
        # Dump the model as a dictionary, excluding unset fields
        data = registry.model_dump()
        yaml.safe_dump(data, handler, allow_unicode=True, sort_keys=False)


def list_devices() -> List[Device]:
    """Return the list of registered devices, hiding sensitive fields."""
    registry = _load_registry()
    # Return devices without showing password in general listings
    return [d.model_copy(update={"ssh_pass": None}) for d in registry.devices]


def get_device(device_id: str) -> Optional[Device]:
    """Finds and returns a single device by its ID, including credentials."""
    registry = _load_registry()
    for device in registry.devices:
        if device.id == device_id:
            return device
    return None


def upsert_device(device_in: DeviceCreate, device_id: Optional[str] = None) -> Device:
    """Insert or update a device entry.

    - If device_id is provided, it updates an existing device.
    - If device_id is None, it creates a new device with a new UUID.
    """
    registry = _load_registry()
    devices = registry.devices

    if device_id:
        for i, existing in enumerate(devices):
            if existing.id == device_id:
                # Update existing device, keeping its original ID
                updated_device = existing.model_copy(
                    update=device_in.model_dump(exclude_unset=True)
                )
                devices[i] = updated_device
                _save_registry(registry)
                return updated_device
        # If ID provided but not found, we could raise an error or fall through
        # For upsert, we'll treat it as a creation with a specified ID.
        new_id = device_id
    else:
        new_id = str(uuid.uuid4())

    # Create new device
    new_device = Device(id=new_id, **device_in.model_dump())
    devices.append(new_device)
    _save_registry(registry)
    return new_device


def delete_device(device_id: str) -> bool:
    """Remove a device from the registry by its ID. Returns True if deleted."""
    registry = _load_registry()
    devices = registry.devices
    original_count = len(devices)
    registry.devices = [d for d in devices if d.id != device_id]

    if len(registry.devices) < original_count:
        _save_registry(registry)
        return True
    return False
