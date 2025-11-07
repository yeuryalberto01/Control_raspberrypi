#!/usr/bin/env python3
"""
Pruebas opcionales de integración SSH.

Estas pruebas se ejecutan únicamente cuando se configuran las variables de entorno:
    RUN_SSH_TESTS=1
    SSH_TEST_IP=<ip>
    SSH_TEST_PASSWORD=<password>
    [SSH_TEST_USER=pi]
    [SSH_TEST_PORT=22]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Asegurar que los módulos del proyecto estén en el path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Asegurar que los módulos del proyecto estén en el path
sys.path.insert(0, str(Path(__file__).parent))


async def _run_ssh_integration() -> bool:
    """Ejecuta las pruebas SSH reales contra un dispositivo definido por el usuario."""
    from launcher.modules.database import DatabaseManager
    from launcher.modules.device_monitor import DeviceMonitor
    from launcher.modules.ssh_manager import SSHDevice, SSHManager

    ip = os.getenv("SSH_TEST_IP")
    password = os.getenv("SSH_TEST_PASSWORD")
    user = os.getenv("SSH_TEST_USER", "pi")
    port = int(os.getenv("SSH_TEST_PORT", "22"))

    if not ip or not password:
        raise RuntimeError(
            "Debe definir SSH_TEST_IP y SSH_TEST_PASSWORD para ejecutar las pruebas SSH."
        )

    db_path = Path("test_ssh.db")
    db_manager = DatabaseManager(db_path)
    ssh_manager = SSHManager(db_manager)

    try:
        device = SSHDevice(
            ip=ip,
            user=user,
            password=password,
            port=port,
            name=f"SSH Test {ip}",
            is_raspberry_pi=True,
        )

        print(f"📡 Conectando con {device.ip}…")
        ssh_manager.add_device(device)

        connection_ok = await ssh_manager.connect(device.ip)
        if not connection_ok:
            print("❌ No se pudo establecer la conexión SSH")
            return False

        print("✅ Conexión SSH establecida, ejecutando comandos básicos…")
        result = await ssh_manager.execute_command("uname -a")
        print(result.stdout.strip())

        monitor = DeviceMonitor(db_manager, ssh_manager)
        monitor.start_monitoring(interval=5)
        await asyncio.sleep(10)
        monitor.stop_monitoring()

        return True

    finally:
        ssh_manager.cleanup()
        db_manager.close()
        db_path.unlink(missing_ok=True)


def _should_run_ssh_tests() -> bool:
    """Determina si se debe ejecutar la prueba SSH."""
    required = {"RUN_SSH_TESTS", "SSH_TEST_IP", "SSH_TEST_PASSWORD"}
    return all(os.getenv(var) for var in required)


@pytest.mark.skipif(
    not _should_run_ssh_tests(),
    reason="Prueba SSH deshabilitada (defina RUN_SSH_TESTS y credenciales SSH_TEST_*).",
)
def test_ssh_functionality() -> None:
    """Wrapper síncrono para integrar con pytest."""
    assert asyncio.run(_run_ssh_integration())


if __name__ == "__main__":  # pragma: no cover - ejecución manual
    try:
        ok = asyncio.run(_run_ssh_integration())
    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ Error en pruebas SSH: {exc}")
        ok = False
    sys.exit(0 if ok else 1)
