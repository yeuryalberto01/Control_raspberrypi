#!/usr/bin/env python3
"""
Simple launcher utility to start/stop backend (uvicorn) and frontend (Vite)
processes from one place. Designed for Raspberry Pi or local dev machines.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
PID_DIR = ROOT / ".launcher"
LOG_DIR = ROOT / "logs"
LOG_TARGETS = {
    "backend": LOG_DIR / "backend.log",
    "frontend": LOG_DIR / "frontend.log",
    "tests": LOG_DIR / "tests.log",
}
DOCKER_COMPOSE_FILE = ROOT / "docker-compose.yml"
VALID_MODES = ("local", "docker")


def default_mode() -> str:
    env_mode = os.environ.get("LAUNCH_MODE", "local").lower()
    return env_mode if env_mode in VALID_MODES else "local"


def docker_service_for_target(target: str) -> str:
    if target != "backend":
        print(f"El modo docker solo soporta el target 'backend' (recibido '{target}').", file=sys.stderr)
        sys.exit(1)
    return os.environ.get("DOCKER_BACKEND_SERVICE", "app")


def ensure_docker_available() -> list[str]:
    docker_cli = shutil.which("docker")
    docker_compose = shutil.which("docker-compose")
    if docker_cli:
        return [docker_cli, "compose"]
    if docker_compose:
        return [docker_compose]
    print(
        "No se encontró ni 'docker' ni 'docker-compose' en PATH. Instala Docker para usar el modo docker.",
        file=sys.stderr,
    )
    sys.exit(1)


def run_docker_compose(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    if not DOCKER_COMPOSE_FILE.exists():
        print(f"docker-compose.yml no encontrado en {DOCKER_COMPOSE_FILE}.", file=sys.stderr)
        sys.exit(1)
    base_cmd = ensure_docker_available() + ["-f", str(DOCKER_COMPOSE_FILE), *args]
    kwargs: dict[str, object] = {"cwd": str(ROOT), "check": False}
    if capture:
        kwargs.update({"capture_output": True, "text": True})
    return subprocess.run(base_cmd, **kwargs)


def docker_start_backend() -> None:
    service = docker_service_for_target("backend")
    result = run_docker_compose(["up", "-d", service])
    if result.returncode != 0:
        sys.exit(result.returncode)
    print(f"Servicio docker '{service}' iniciado (modo detach).")


def docker_stop_backend() -> None:
    service = docker_service_for_target("backend")
    result = run_docker_compose(["stop", service])
    if result.returncode != 0:
        sys.exit(result.returncode)
    print(f"Servicio docker '{service}' detenido.")


def docker_backend_container_id() -> str | None:
    service = docker_service_for_target("backend")
    result = run_docker_compose(["ps", "-q", service], capture=True)
    if result.returncode != 0:
        sys.exit(result.returncode)
    container_id = (result.stdout or "").strip()
    return container_id or None


def docker_backend_status_text() -> str:
    container_id = docker_backend_container_id()
    return f"running (container {container_id[:12]})" if container_id else "stopped"


def docker_backend_logs(lines: int) -> str:
    service = docker_service_for_target("backend")
    result = run_docker_compose(["logs", "--tail", str(lines), service], capture=True)
    if result.returncode != 0:
        sys.exit(result.returncode)
    return (result.stdout or "").strip()


def tail_log_file(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    try:
        content = path.read_text(errors="ignore").splitlines()
    except OSError as exc:  # pragma: no cover - log helper
        return f"(No se pudo leer {path.name}: {exc})"
    if not content:
        return ""
    return "\n".join(content[-lines:])


def ensure_dirs() -> None:
    PID_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


def pid_file(name: str) -> Path:
    return PID_DIR / f"{name}.pid"


def read_pid(name: str) -> int | None:
    path = pid_file(name)
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def write_pid(name: str, pid: int) -> None:
    pid_file(name).write_text(str(pid))


def remove_pid(name: str) -> None:
    try:
        pid_file(name).unlink()
    except FileNotFoundError:
        pass


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def npm_executable() -> str:
    candidates = ("npm", "npm.cmd", "npm.exe")
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    print(
        "npm no se encontró en PATH. Instala Node.js o añade la carpeta que contiene npm a PATH.",
        file=sys.stderr,
    )
    sys.exit(1)


def run_process(name: str, command: List[str], cwd: Path) -> None:
    ensure_dirs()
    if read_pid(name):
        print(f"{name} already appears to be running (pid file exists). Stop it first.", file=sys.stderr)
        sys.exit(1)

    log_path = LOG_DIR / f"{name}.log"
    with log_path.open("ab") as log_file:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=False,
            env=os.environ.copy(),
        )

    # Give the child process a moment to fail fast (missing deps, syntax errors, etc.)
    time.sleep(1)
    if proc.poll() is not None:
        tail = ""
        if log_path.exists():
            tail_lines = log_path.read_text(errors="ignore").splitlines()[-20:]
            if tail_lines:
                tail = "\n".join(tail_lines)
        print(f"{name} failed to start (exit code {proc.returncode}). Revisa {log_path} para detalles.", file=sys.stderr)
        if tail:
            print("--- Log tail ---", file=sys.stderr)
            print(tail, file=sys.stderr)
        sys.exit(proc.returncode or 1)

    write_pid(name, proc.pid)
    print(f"{name} started (PID {proc.pid}). Logs -> {log_path}")


def stop_process(name: str) -> None:
    pid = read_pid(name)
    if not pid:
        print(f"{name} does not seem to be running (no PID file).")
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(f"Warning: failed to signal process {pid}: {exc}")
    else:
        print(f"Stop signal sent to {name} (PID {pid}).")
    remove_pid(name)


def backend_command(host: str, port: int) -> List[str]:
    python = venv_python()
    if not python.exists():
        print("Virtualenv python not found. Did you run `python3 -m venv .venv`?", file=sys.stderr)
        sys.exit(1)
    return [
        str(python),
        "-m",
        "uvicorn",
        "raspi_deployer_starter.app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def frontend_command(host: str, port: int) -> List[str]:
    npm_bin = npm_executable()
    return [
        npm_bin,
        "run",
        "dev",
        "--",
        "--host",
        host,
        "--port",
        str(port),
    ]


def handle_start(args: argparse.Namespace) -> None:
    mode = getattr(args, "mode", default_mode())
    if args.target == "backend":
        if mode == "docker":
            docker_start_backend()
        else:
            run_process("backend", backend_command(args.host, args.port), ROOT)
    elif args.target == "frontend":
        run_process("frontend", frontend_command(args.host, args.port), ROOT / "frontend")
    else:
        raise ValueError("Unknown target")


def handle_stop(args: argparse.Namespace) -> None:
    mode = getattr(args, "mode", default_mode())
    if args.target == "backend":
        if mode == "docker":
            docker_stop_backend()
        else:
            stop_process("backend")
    elif args.target == "frontend":
        stop_process("frontend")
    else:
        raise ValueError("Unknown target")


def handle_status(args: argparse.Namespace) -> None:
    mode = getattr(args, "mode", default_mode())
    if mode == "docker":
        backend_status = docker_backend_status_text()
    else:
        backend_pid = read_pid("backend")
        backend_status = f"running (PID {backend_pid})" if backend_pid else "stopped"
    frontend_pid = read_pid("frontend")
    frontend_status = f"running (PID {frontend_pid})" if frontend_pid else "stopped"
    print(f"Backend ({mode}): {backend_status}")
    print(f"Frontend (local): {frontend_status}")


def handle_logs(args: argparse.Namespace) -> None:
    target = args.target
    mode = getattr(args, "mode", default_mode())
    lines = args.lines
    if target == "backend" and mode == "docker":
        output = docker_backend_logs(lines)
    else:
        log_path = LOG_TARGETS.get(target, LOG_DIR / f"{target}.log")
        output = tail_log_file(log_path, lines)
    print(output or "Sin logs por ahora...")


def run_tests_suite() -> int:
    ensure_dirs()
    python = venv_python()
    if not python.exists():
        print("Virtualenv python not found. Did you run `python3 -m venv .venv`?", file=sys.stderr)
        return 1

    log_path = LOG_DIR / "tests.log"
    cmd = [
        str(python),
        "-m",
        "pytest",
        "raspi_deployer_starter/tests",
        "-v",
    ]
    print(f"Running tests -> logs stored in {log_path}")
    with log_path.open("ab") as log_file:
        proc = subprocess.run(cmd, cwd=str(ROOT), stdout=log_file, stderr=subprocess.STDOUT, text=False, check=False)
    if proc.returncode == 0:
        print("Tests completed successfully.")
    else:
        print("Tests finished with failures. Check logs/tests.log for details.", file=sys.stderr)
    return proc.returncode


def handle_tests(_: argparse.Namespace) -> None:
    rc = run_tests_suite()
    if rc != 0:
        sys.exit(rc)


def run_update_pipeline() -> int:
    script = ROOT / "scripts" / "update_repo.sh"
    if not script.exists():
        print("scripts/update_repo.sh no encontrado.", file=sys.stderr)
        return 1
    bash_path = shutil.which("bash")
    if not bash_path:
        print("Bash no está disponible en PATH. Ejecuta el script directamente en la Raspberry Pi.", file=sys.stderr)
        return 1
    print(f"Ejecutando script de actualización: {script}")
    result = subprocess.run([bash_path, str(script)], cwd=str(ROOT), check=False)
    if result.returncode == 0:
        print("Actualización completada correctamente.")
    return result.returncode


def handle_update(_: argparse.Namespace) -> None:
    rc = run_update_pipeline()
    if rc != 0:
        sys.exit(rc)


def clear_logs(target: str) -> None:
    ensure_dirs()
    if target == "all":
        files = list(LOG_DIR.glob("*.log"))
    else:
        files = [LOG_TARGETS.get(target, LOG_DIR / f"{target}.log")]

    removed = []
    for file in files:
        if file.exists():
            file.unlink()
            removed.append(file.name)
    if removed:
        print("Se eliminaron los logs:", ", ".join(sorted(removed)))
    else:
        print("No se encontraron logs para borrar.")


def handle_clear_logs(args: argparse.Namespace) -> None:
    clear_logs(args.target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launcher for Pi Admin backend/frontend.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_mode_arg(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument(
            "--mode",
            choices=VALID_MODES,
            default=default_mode(),
            help="Modo de ejecución: local usa procesos directos, docker usa docker compose (default: %(default)s).",
        )

    start = sub.add_parser("start", help="Start backend or frontend")
    start.add_argument("target", choices=["backend", "frontend"])
    start.add_argument("--host", default="0.0.0.0", help="Binding host (default 0.0.0.0)")
    start.add_argument("--port", type=int, default=8000, help="Port (backend default 8000 / override for frontend)")
    add_mode_arg(start)
    start.set_defaults(func=handle_start)

    stop = sub.add_parser("stop", help="Stop backend or frontend")
    stop.add_argument("target", choices=["backend", "frontend"])
    add_mode_arg(stop)
    stop.set_defaults(func=handle_stop)

    status = sub.add_parser("status", help="Show launcher status")
    add_mode_arg(status)
    status.set_defaults(func=handle_status)

    tests = sub.add_parser("tests", help="Run backend test suite (pytest)")
    tests.set_defaults(func=handle_tests)

    update = sub.add_parser("update", help="Update repository and rebuild services")
    update.set_defaults(func=handle_update)

    clear_logs_cmd = sub.add_parser("clear-logs", help="Delete launcher log files")
    clear_logs_cmd.add_argument(
        "--target",
        default="all",
        choices=["backend", "frontend", "tests", "all"],
        help="Which log to delete (default: all)",
    )
    clear_logs_cmd.set_defaults(func=handle_clear_logs)

    logs_cmd = sub.add_parser("logs", help="Show tail of launcher-managed logs")
    logs_cmd.add_argument("target", choices=["backend", "frontend", "tests"], help="Log objetivo a inspeccionar")
    logs_cmd.add_argument("--lines", type=int, default=50, help="Cantidad de líneas a mostrar (default: 50)")
    add_mode_arg(logs_cmd)
    logs_cmd.set_defaults(func=handle_logs)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if getattr(args, "target", None) == "frontend" and args.command == "start" and getattr(args, "port", 8000) == 8000:
        # avoid accidental reuse of backend port
        args.port = 5173

    args.func(args)


if __name__ == "__main__":
    main()
