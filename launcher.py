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


def run_process(name: str, command: List[str], cwd: Path) -> None:
    ensure_dirs()
    if read_pid(name):
        print(f"{name} already appears to be running (pid file exists). Stop it first.", file=sys.stderr)
        sys.exit(1)

    log_path = LOG_DIR / f"{name}.log"
    log_file = log_path.open("ab")
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=False,
        env=os.environ.copy(),
    )
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
    return [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        host,
        "--port",
        str(port),
    ]


def handle_start(args: argparse.Namespace) -> None:
    if args.target == "backend":
        run_process("backend", backend_command(args.host, args.port), ROOT)
    elif args.target == "frontend":
        run_process("frontend", frontend_command(args.host, args.port), ROOT / "frontend")
    else:
        raise ValueError("Unknown target")


def handle_stop(args: argparse.Namespace) -> None:
    stop_process(args.target)


def handle_status(_: argparse.Namespace) -> None:
    backend_pid = read_pid("backend")
    frontend_pid = read_pid("frontend")
    print(f"Backend:  {'running (PID '+str(backend_pid)+')' if backend_pid else 'stopped'}")
    print(f"Frontend: {'running (PID '+str(frontend_pid)+')' if frontend_pid else 'stopped'}")


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

    start = sub.add_parser("start", help="Start backend or frontend")
    start.add_argument("target", choices=["backend", "frontend"])
    start.add_argument("--host", default="0.0.0.0", help="Binding host (default 0.0.0.0)")
    start.add_argument("--port", type=int, default=8000, help="Port (backend default 8000 / override for frontend)")
    start.set_defaults(func=handle_start)

    stop = sub.add_parser("stop", help="Stop backend or frontend")
    stop.add_argument("target", choices=["backend", "frontend"])
    stop.set_defaults(func=handle_stop)

    status = sub.add_parser("status", help="Show launcher status")
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
