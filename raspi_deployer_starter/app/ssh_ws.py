"""
WebSocket endpoint for dynamic, per-device SSH connections.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from .auth import validate_token
from . import ssh_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    return token or None


@router.websocket("/{device_id}/ws")
async def ssh_websocket_endpoint(
    websocket: WebSocket,
    device_id: str,
):
    """
    Handles a WebSocket connection to stream an interactive SSH shell for a
    specific device.
    """
    raw_token = _extract_token(websocket.query_params.get("token"))
    if not validate_token(raw_token, required="admin"):
        logger.warning("SSH websocket rejected for device %s due to invalid token.", device_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    try:
        # Use the new ssh_manager to get a connection object
        conn = ssh_manager.get_ssh_connection(device_id)
        logger.info(f"SSH connection requested for device {device_id}")
        
        # Fabric's invoke_shell gives us the underlying Paramiko channel
        channel = conn.invoke_shell(term="xterm")
        channel.settimeout(0.0)
        logger.info(f"SSH shell invoked for {device_id}")

        async def read_from_ssh() -> None:
            """Read data from SSH channel and forward to WebSocket."""
            try:
                while not channel.closed:
                    if channel.recv_ready():
                        data = channel.recv(1024)
                        if not data:
                            break
                        await websocket.send_text(data.decode("utf-8", "ignore"))
                    await asyncio.sleep(0.01) # Prevent busy-waiting
            except (OSError, asyncio.CancelledError):
                pass # Task was cancelled or connection closed
            finally:
                logger.info(f"SSH read task for {device_id} finished.")

        async def write_to_ssh() -> None:
            """Read data from WebSocket and forward to SSH channel."""
            try:
                while not channel.closed:
                    data = await websocket.receive_text()
                    channel.send(data)
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass # Client disconnected or task was cancelled
            finally:
                logger.info(f"SSH write task for {device_id} finished.")

        # Run both tasks concurrently
        read_task = asyncio.create_task(read_from_ssh())
        write_task = asyncio.create_task(write_to_ssh())

        # Wait for one of the tasks to complete (e.g., disconnect)
        done, pending = await asyncio.wait(
            {read_task, write_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel any pending tasks to ensure a clean exit
        for task in pending:
            task.cancel()
        
        # Wait for pending tasks to finish cancellation
        if pending:
            await asyncio.wait(pending)

    except HTTPException as exc:
        logger.warning(f"SSH connection failed for {device_id}: {exc.detail}")
        await websocket.send_text(f"\r\nError: {exc.detail}\r\n")
        await websocket.close(code=1011)
    except Exception as exc:
        logger.error(f"An unexpected SSH error occurred for {device_id}: {exc}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.send_text(f"\r\nAn unexpected error occurred: {exc}\r\n")
            await websocket.close(code=1011)
    finally:
        # Ensure connection is closed if it was opened
        if 'conn' in locals() and conn.is_connected:
            conn.close()
        logger.info(f"SSH WebSocket for device {device_id} is now closed.")
