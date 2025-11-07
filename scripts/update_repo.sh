#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
SERVICE_NAME="${PI_ADMIN_SERVICE:-pi-admin}"
VENV_BIN="${PROJECT_ROOT}/.venv/bin"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
SERVICE_EXISTS=0
SERVICE_WAS_RUNNING=0

cd "${PROJECT_ROOT}"

log "Iniciando actualización en ${PROJECT_ROOT}"

if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files | grep -Fq "${SERVICE_NAME}.service"; then
    SERVICE_EXISTS=1
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
      SERVICE_WAS_RUNNING=1
      log "Deteniendo servicio ${SERVICE_NAME}"
      sudo systemctl stop "${SERVICE_NAME}"
    fi
  fi
fi

if command -v git >/dev/null 2>&1; then
  log "Actualizando repositorio (git pull --ff-only)"
  git fetch --all --prune
  git pull --ff-only
else
  log "git no está disponible en PATH. Abortando."
  exit 1
fi

if [[ -x "${VENV_BIN}/pip" ]]; then
  log "Actualizando dependencias de Python"
  "${VENV_BIN}/pip" install --upgrade pip
  "${VENV_BIN}/pip" install -e .
else
  log "No se encontró entorno virtual en ${PROJECT_ROOT}/.venv. Saltando paso de Python."
fi

EXTRA_REQ="${PROJECT_ROOT}/requirements.txt"
if [[ -x "${VENV_BIN}/pip" && -f "${EXTRA_REQ}" ]]; then
  log "Instalando requirements.txt"
  "${VENV_BIN}/pip" install -r "${EXTRA_REQ}"
fi

if [[ -d "${FRONTEND_DIR}" ]]; then
  if command -v npm >/dev/null 2>&1; then
    log "Instalando dependencias frontend"
    pushd "${FRONTEND_DIR}" >/dev/null
    npm install
    log "Compilando frontend (npm run build)"
    npm run build
    popd >/dev/null
  else
    log "npm no está disponible. Saltando build del frontend."
  fi
else
  log "Directorio frontend no encontrado. Saltando build."
fi

if [[ ${SERVICE_EXISTS} -eq 1 ]]; then
  log "Recargando systemd"
  sudo systemctl daemon-reload
  if [[ ${SERVICE_WAS_RUNNING} -eq 1 ]]; then
    log "Reiniciando servicio ${SERVICE_NAME}"
    sudo systemctl start "${SERVICE_NAME}"
  fi
fi

log "Actualización completada."
