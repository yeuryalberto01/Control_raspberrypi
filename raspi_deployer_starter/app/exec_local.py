"""
Helpers to execute shell commands safely on the Raspberry Pi host.

Commands are normalised to avoid invoking the shell directly, reducing the risk
of command injection.  Both async and sync helpers are provided to fit the
FastAPI endpoints and occasional CLI usage inside the codebase.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from typing import Iterable, List, Optional, Sequence, Union

from .schemas import ExecResult

# Tokens that should never appear in a command to avoid shell injection.
_FORBIDDEN_TOKENS = {";", "&&", "||", "|", "`"}
_FORBIDDEN_SUBSTRINGS = {"$(", "${", ">" , "<"}


def _normalise_command(command: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(command, str):
        parts = shlex.split(command, posix=True)
    else:
        parts = [str(part) for part in command]

    if not parts:
        raise ValueError("El comando no puede estar vacío.")

    for token in parts:
        stripped = token.strip()
        if not stripped:
            raise ValueError("Los argumentos del comando no pueden estar vacíos.")
        if any(forbidden in stripped for forbidden in _FORBIDDEN_TOKENS):
            raise ValueError(f"Token no permitido en el comando: {stripped!r}")
        if any(fragment in stripped for fragment in _FORBIDDEN_SUBSTRINGS):
            raise ValueError(f"Secuencia no permitida en el comando: {stripped!r}")
        if "\n" in stripped or "\r" in stripped:
            raise ValueError("El comando no puede contener saltos de línea.")

    return parts


async def run_command_async(
    command: Union[str, Sequence[str]],
    *,
    timeout: Optional[float] = None,
    env: Optional[Iterable[tuple[str, str]]] = None,
) -> ExecResult:
    """
    Ejecuta un comando de forma asíncrona usando subprocess_exec.

    Se devuelve un ExecResult con stdout/stderr en UTF-8 (ignorando errores).
    """
    cmd = _normalise_command(command)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(dict(env))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged_env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return ExecResult(code=-1, stdout="", stderr="Timeout ejecutando el comando.")

    stdout = stdout_bytes.decode("utf-8", errors="ignore")
    stderr = stderr_bytes.decode("utf-8", errors="ignore")
    return ExecResult(code=process.returncode, stdout=stdout, stderr=stderr)


def run_command(
    command: Union[str, Sequence[str]],
    *,
    timeout: Optional[float] = None,
    env: Optional[Iterable[tuple[str, str]]] = None,
) -> ExecResult:
    """
    Ejecuta un comando de manera síncrona.

    Útil fuera de corutinas (p.ej. scripts de despliegue). Usa subprocess.run
    evitando invocar el shell directamente.
    """
    cmd = _normalise_command(command)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(dict(env))

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=merged_env,
        )
    except subprocess.TimeoutExpired:
        return ExecResult(code=-1, stdout="", stderr="Timeout ejecutando el comando.")

    stdout = completed.stdout.decode("utf-8", errors="ignore")
    stderr = completed.stderr.decode("utf-8", errors="ignore")
    return ExecResult(code=completed.returncode, stdout=stdout, stderr=stderr)
