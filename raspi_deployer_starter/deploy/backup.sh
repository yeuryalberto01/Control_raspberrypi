#!/usr/bin/env bash
set -euo pipefail

DST="/home/pi/backups"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DST"

tar -czf "$DST/pi_backup_${TS}.tgz" \
  config/whitelist.yaml \
  data/devices.yaml \
  .env || true

ls -1t "$DST"/pi_backup_*.tgz | sed -e '1,7d' | xargs -r rm -f
