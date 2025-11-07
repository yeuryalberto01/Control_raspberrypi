#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/pi/raspi_deployer_starter"
VENV="/home/pi/.venvs/pi-admin"

sudo apt update
sudo apt install -y python3-venv python3-pip nginx

mkdir -p "$(dirname "$VENV")"
python3 -m venv "$VENV"
source "$VENV/bin/activate"

cd "$APP_DIR"
pip install -U pip
pip install -r requirements.txt

sudo cp deploy/rpi.service /etc/systemd/system/pi-admin.service
sudo systemctl daemon-reload
sudo systemctl enable --now pi-admin
sudo systemctl status pi-admin --no-pager -l || true

if [ -f nginx/site-pi-admin.conf ]; then
  sudo cp nginx/site-pi-admin.conf /etc/nginx/sites-available/pi-admin.conf
  sudo ln -sf /etc/nginx/sites-available/pi-admin.conf /etc/nginx/sites-enabled/pi-admin.conf
  sudo nginx -t && sudo systemctl reload nginx
fi

echo "API lista en http://<ip-pi>:8000/ (o via Nginx en :80)."
