#!/usr/bin/env python3
"""
Simple Tkinter-based GUI to control launcher.py start/stop commands.
Intended for lightweight use on Raspberry Pi (no heavy frameworks).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "launcher.py"
LOG_DIR = ROOT / "logs"


def run_launcher_command(args: list[str]) -> tuple[int, str]:
    """
    Execute `python launcher.py ...` and return (returncode, combined_output).
    """
    cmd = [sys.executable, str(LAUNCHER), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:  # pragma: no cover - GUI helper
        return 1, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


class LauncherGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pi Admin Launcher")
        self.geometry("420x360")
        self.resizable(False, False)

        self.status_var = tk.StringVar(value="Estado: desconocido")
        self.log_text = tk.Text(self, height=10, state="disabled")

        self._build_widgets()
        self.refresh_status()
        self.refresh_logs()

    def _build_widgets(self) -> None:
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Iniciar Backend", width=18, command=lambda: self.run_async(["start", "backend"])).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="Detener Backend", width=18, command=lambda: self.run_async(["stop", "backend"])).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(btn_frame, text="Iniciar Frontend", width=18, command=lambda: self.run_async(["start", "frontend"])).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(btn_frame, text="Detener Frontend", width=18, command=lambda: self.run_async(["stop", "frontend"])).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(btn_frame, text="Actualizar estado", width=18, command=self.refresh_status).grid(row=2, column=0, pady=(5, 0))
        tk.Button(btn_frame, text="Ejecutar tests", width=18, command=lambda: self.run_async(["tests"])).grid(row=2, column=1, pady=(5, 0))
        tk.Button(btn_frame, text="Borrar logs", width=18, command=self.confirm_clear_logs).grid(row=3, column=0, columnspan=2, pady=(10, 0))
        tk.Button(btn_frame, text="Actualizar repositorio", width=22, command=self.confirm_update_repo).grid(row=4, column=0, columnspan=2, pady=(5, 0))

        tk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12)

        tk.Label(self, text="Logs recientes").pack(anchor="w", padx=12, pady=(10, 0))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def run_async(self, args: list[str]) -> None:
        threading.Thread(target=self._run_and_report, args=(args,), daemon=True).start()

    def _run_and_report(self, args: list[str]) -> None:
        rc, output = run_launcher_command(args)
        self.after(0, lambda: self._handle_result(rc, output))

    def _handle_result(self, rc: int, output: str) -> None:
        if output:
            messagebox.showinfo("Launcher", output)
        self.refresh_status()
        self.refresh_logs()
        if rc != 0:
            messagebox.showwarning("Launcher", f"El comando terminó con código {rc}")

    def confirm_clear_logs(self) -> None:
        if messagebox.askyesno("Borrar logs", "¿Deseas borrar todos los logs del launcher?"):
            self.run_async(["clear-logs"])

    def confirm_update_repo(self) -> None:
        if messagebox.askyesno(
            "Actualizar repositorio",
            "¿Descargar la última versión, reinstalar dependencias y recompilar el frontend?\n"
            "El backend se reiniciará si existe el servicio systemd.",
        ):
            self.run_async(["update"])

    def refresh_status(self) -> None:
        rc, output = run_launcher_command(["status"])
        if rc == 0:
            self.status_var.set(output.replace("\n", " | "))
        else:
            self.status_var.set("Error al consultar estado")

    def refresh_logs(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        log_path = LOG_DIR / "backend.log"
        text = ""
        if log_path.exists():
            try:
                text = "\n".join(log_path.read_text(errors="ignore").splitlines()[-50:])
            except Exception:
                text = "(No se pudo leer backend.log)"
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, text or "Sin logs por ahora...")
        self.log_text.config(state="disabled")


def main() -> None:
    if not LAUNCHER.exists():
        print("launcher.py no encontrado en la raíz del proyecto.", file=sys.stderr)
        sys.exit(1)
    app = LauncherGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
