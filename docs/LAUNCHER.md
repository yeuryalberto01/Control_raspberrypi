# Launcher Utility

The repository now includes launcher.py to simplify starting/stopping the backend (FastAPI/uvicorn) and the frontend (Vite dev server) without having to type long commands.

## Requirements

- Backend virtualenv (.venv) already created and dependencies installed.
- Node/npm installed (for the frontend dev server).

## Usage

`ash
# Start backend (uvicorn) with default host/port (0.0.0.0:8000)
python launcher.py start backend

# Start frontend dev server (defaults to 0.0.0.0:5173)
python launcher.py start frontend --host 0.0.0.0 --port 5176

# Show status of managed processes
python launcher.py status

# Stop processes
python launcher.py stop backend
python launcher.py stop frontend

# Run tests (pytest -> logs/tests.log)
python launcher.py tests
`

Logs are saved to logs/backend.log and logs/frontend.log. PID files live inside .launcher/, so the script knows whether a process is already running.

## GUI version

If you prefer a small graphical interface, run:

`ash
python launcher_gui.py
`

This Tkinter window exposes buttons to start/stop backend and frontend, run the automated tests, shows status, and tails recent backend logs. Ideal for hooking up to the Pi's desktop/kiosk mode.

> **Tip**: On Raspberry Pi you can add systemd services later, but the CLI launcher + GUI are handy for development/testing on both the Pi and your PC.
