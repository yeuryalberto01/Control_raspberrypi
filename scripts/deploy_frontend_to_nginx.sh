#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"
DIST_DIR="${FRONTEND_DIR}/dist"
TARGET_DIR="/var/www/pi-admin"
NGINX_SITE="/etc/nginx/sites-available/pi-admin"
NGINX_LINK="/etc/nginx/sites-enabled/pi-admin"

if [[ ! -d "${FRONTEND_DIR}" ]]; then
  echo "frontend/ directory not found. Run this script from the repo root." >&2
  exit 1
fi

pushd "${FRONTEND_DIR}" >/dev/null
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build
popd >/dev/null

sudo mkdir -p "${TARGET_DIR}"
sudo rm -rf "${TARGET_DIR:?}"/*
sudo cp -r "${DIST_DIR}/." "${TARGET_DIR}/"

sudo tee "${NGINX_SITE}" >/dev/null <<EOF
server {
    listen 80;
    server_name _;

    root ${TARGET_DIR};
    index index.html;

    location /api {
        proxy_pass http://127.0.0.1:8000/api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ssh {
        proxy_pass http://127.0.0.1:8000/ssh;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        try_files \$uri /index.html;
    }
}
EOF

sudo ln -sf "${NGINX_SITE}" "${NGINX_LINK}"
sudo nginx -t
sudo systemctl reload nginx
echo "Frontend deployed to ${TARGET_DIR} and served via Nginx."
