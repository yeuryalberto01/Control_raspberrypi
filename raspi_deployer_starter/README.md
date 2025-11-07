# Raspi Deployer Starter

Plataforma mínima para desplegar una app FastAPI a una Raspberry Pi vía SSH + systemd.

## Uso rápido
1) Instala dependencias en tu PC:
```bash
pip install -r requirements.txt
```

2) Copia `.env.example` a `.env` y ajusta:
```
APP_NAME=mi_app
PI_HOST=raspberrypi.local
PI_USER=pi
APP_PORT=8080
```

3) Despliegue completo:
```bash
invoke -f deploy/deploy.py deploy-all
```

Comandos útiles:
```bash
invoke -f deploy/deploy.py sync
invoke -f deploy/deploy.py restart
invoke -f deploy/deploy.py logs
invoke -f deploy/deploy.py test
invoke -f deploy/deploy.py health
```

## Docker (opcional)
Incluye `Dockerfile` y `docker-compose.yml` por si prefieres contenedores.

## Descubrimiento de la Raspberry Pi
El helper `deploy/pi_ssh.py` intenta localizar la Raspberry Pi antes de abrir la sesion SSH. Las estrategias incluyen:
- Host indicado en `PI_HOST`.
- Lista extra en `PI_HOST_CANDIDATES` (separada por comas).
- Descubrimiento mDNS utilizando zeroconf.
- Escaneo opcional de subred si defines `PI_SUBNET` (por ejemplo `192.168.0.0/24`, se limita a 64 hosts por defecto).

Puedes reutilizar `RaspberryPiDiscoverer` dentro de otros scripts para obtener un `paramiko.SSHClient` o para consultar los candidatos disponibles.

## Nueva API de administracion

El backend FastAPI ahora expone endpoints con autenticacion JWT y roles (`admin` / `readonly`). Copia `config/settings.example.env` a `.env`, define credenciales (`ADMIN_*`, `READONLY_*`) y un `JWT_SECRET` antes de desplegar. Ajusta tambien `config/whitelist.yaml` y `data/devices.yaml` para declarar servicios/unidades permitidos y habilitar el registro multi-Pi.

- `POST /auth/login` entrega un JWT con el rol correspondiente.
- `GET /health` comprueba que la API este viva (sin auth).
- `GET /info` y `GET /metrics` requieren al menos rol `readonly`.
- `GET /service` lista servicios gestionables; `POST /service/status` consulta varios estados a la vez.
- `POST /service` (rol `admin`) permite start/stop/restart.
- `GET /logs/download` devuelve un tail controlado del journal; `WS /logs/ws` transmite en vivo.
- `WS /metrics/ws` expone metricas periodicas; el cliente puede indicar `?interval=` en segundos.
- `POST /exec`, `POST /system/reboot` y `/system/poweroff` requieren rol `admin`. Reboot/Poweroff exigen un header `X-Confirm` con `REBOOT` o `POWEROFF`.
- Registro multi-Pi: `/registry/devices` gestiona Pis (GET/POST/DELETE) y `/registry/{id}/proxy/...` permite consultar metricas remotas a traves del panel.
- Despliegues rapidos: `/deploy/archive?target_dir=...` acepta ZIP/TAR en rutas whitelisteadas; `/deploy/git` ejecuta `git pull` y reinicia el servicio configurado.
- Rate-limit basico (300 req/min por IP) protege contra abusos en LAN.
- `GET /backup/download` genera un tar.gz con config, whitelist, registro y logs.

Para instalar en la Raspberry Pi ejecuta `deploy/install_pi.sh` y opcionalmente habilita el reverse proxy `nginx/site-pi-admin.conf` (incluye los bloques para los WebSocket de logs y metricas).

### Watchdog opcional

El script `app/healthcheck.py` y las unidades `deploy/pi-watchdog.service` + `.timer` permiten que systemd revise la salud del panel cada dos minutos y reinicie el servicio configurado (`WATCHDOG_SERVICE`). Copia ambos archivos a `/etc/systemd/system/`, recarga systemd y habilita `pi-watchdog.timer`.

## Frontend (Vite + React)

El directorio `frontend/` contiene el panel web. Para levantarlo:

```bash
cd frontend
cp .env.example .env   # Ajusta VITE_API_BASE
npm install
npm run dev            # Desarrollo
npm run build          # Genera dist/ para Nginx
```

Publica el contenido de `frontend/dist` en tu Nginx (por ejemplo en `/var/www/pi-admin`) y apunta el sitio estatico al build. El front asume el backend expuesto en `VITE_API_BASE` e incluye login con JWT, selector multi-Pi, dashboards en vivo, servicios, logs, deploy y descargas de backup.

## Backups programados

- Script manual/programado: `deploy/backup.sh`.
- Servicio/Timer systemd: `deploy/pi-backup.service` y `deploy/pi-backup.timer`. Instala copiando a `/etc/systemd/system/`, luego `systemctl daemon-reload` y `systemctl enable --now pi-backup.timer`.
- Los artefactos se guardan en `/home/pi/backups` reteniendo los 7 mas recientes.

## QA y monitoreo

- Pruebas unitarias: `pytest` (incluye `tests/test_api.py`, `tests/test_auth.py`, `tests/test_service.py`).
- Carga basica con k6: `k6 run load.js`.
- Runbook operativo: consulta `docs/RUNBOOK.md` para procedimientos de reinicio, incidencias y restauracion.

## GUI de control desde tu PC

El script `pi_admin_gui.py` ofrece una interfaz Tkinter para gestionar la Raspberry desde tu escritorio:

```bash
pip install requests paramiko
python pi_admin_gui.py
```

Funciones cubiertas:
- Login JWT contra el backend (`/auth/login`)
- Consultas de `/info`, `/metrics`, servicios, status, descargas de logs y backups
- Restart/Poweroff con confirmacion
- Deploy ZIP/TAR o git pull utilizando los endpoints existentes
- Ejecucion de comandos SSH (opcional) usando `paramiko`

Cada accion queda registrada en `pi_admin_gui.log`.
