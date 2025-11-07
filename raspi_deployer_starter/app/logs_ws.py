"""
Utilities for streaming system logs over WebSocket using journalctl.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
from typing import AsyncGenerator, Optional

from .config_whitelist import allowed_log_unit
from .exec_local import run_command_async

JOURNALCTL_BIN = "/bin/journalctl"
SUDO_BIN = shutil.which("sudo") or "sudo"
RATE_LINES_PER_SEC = 100
TAIL_DEFAULT = 200


def _build_journal_command(
    unit: Optional[str],
    *,
    follow: bool,
    lines: int,
) -> list[str]:
    cmd = [JOURNALCTL_BIN, "-o", "cat"]
    if lines:
        cmd.extend(["-n", str(lines)])
    if unit:
        cmd.extend(["-u", unit])
    if follow:
        cmd.append("-f")
    return [SUDO_BIN, "-n", *cmd]


async def journal_stream(unit: Optional[str] = None) -> AsyncGenerator[str, None]:
    """
    Async generator that yields lines from journalctl -f with simple rate limiting.
    """
    if not allowed_log_unit(unit):
        raise PermissionError("Unidad de logs no permitida.")

    cmd = _build_journal_command(unit, follow=True, lines=TAIL_DEFAULT)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _drain_stderr() -> None:
        if process.stderr is None:
            return
        while True:
            chunk = await process.stderr.readline()
            if not chunk:
                break

    stderr_task = asyncio.create_task(_drain_stderr())
    lines_sent = 0
    window_start = time.monotonic()

    try:
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            now = time.monotonic()
            if now - window_start >= 1:
                window_start = now
                lines_sent = 0

            if lines_sent >= RATE_LINES_PER_SEC:
                await asyncio.sleep(max(0.0, 1 - (now - window_start)))
                window_start = time.monotonic()
                lines_sent = 0

            lines_sent += 1
            yield line.decode("utf-8", errors="ignore")
    finally:
        if process.returncode is None:
            process.terminate()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()
        stderr_task.cancel()
        with contextlib.suppress(Exception):
            await stderr_task


async def download_logs(unit: Optional[str], lines: int = 500) -> str:
    """Retrieve the last *lines* from journalctl for download endpoints."""
    if lines <= 0:
        lines = TAIL_DEFAULT

    if not allowed_log_unit(unit):
        raise PermissionError("Unidad de logs no permitida.")

    cmd = _build_journal_command(unit, follow=False, lines=lines)
    result = await run_command_async(cmd)
    if result.code != 0:
        raise RuntimeError(result.stderr or "No se pudieron obtener los logs.")
    return result.stdout
