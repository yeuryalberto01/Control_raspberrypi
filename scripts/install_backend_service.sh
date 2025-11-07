#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${SCRIPT_DIR}"
VENV_DIR="${APP_DIR}/.venv"
SERVICE_NAME="pi-admin"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Virtualenv not found at ${VENV_DIR}. Create it first (python3 -m venv .venv && pip install -r requirements)." >&2
  exit 1
fi

sudo tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Pi Admin Backend
After=network.target

[Service]
User=pi
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/uvicorn raspi_deployer_starter.app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"
echo "Backend service installed and started (systemctl status ${SERVICE_NAME})."
