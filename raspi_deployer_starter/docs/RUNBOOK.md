# Runbook Operativo

## Reinicio controlado

- Reiniciar solo el servicio FastAPI: `sudo systemctl restart pi-admin`
- Reiniciar la Raspberry completa: `sudo reboot`

## Recuperacion

1. Verificar salud del backend: `curl http://127.0.0.1:8000/health`
2. Consultar logs del servicio: `sudo journalctl -u pi-admin -n 200`
3. Revisar Nginx si el front no responde: `sudo journalctl -u nginx -n 200`

## Despliegue

- Empaquetar y subir un ZIP/TAR mediante el panel (`/deploy/archive`) o via API.
- Usar `/deploy/git` para ejecutar `git pull` en la ruta whitelisteada; el servicio configurado se reinicia automaticamente.

## Rotacion de secretos

1. Actualizar valores en `.env` (`JWT_SECRET`, credenciales admin/readonly).
2. Reiniciar `pi-admin` para que los cambios apliquen: `sudo systemctl restart pi-admin`.

## Incidentes

- Revisar fail2ban: `sudo fail2ban-client status`
- Revisar firewall: `sudo ufw status verbose`
- Analizar logs de Nginx: `sudo tail -n 200 /var/log/nginx/error.log`

## Backups

- Manual: descargar desde `/backup/download` en el panel.
- Programado: revisar archivos en `/home/pi/backups`.
- Restaurar: descomprimir el tar mas reciente en la raiz del proyecto (`tar -xzf archivo -C /home/pi/raspi_deployer_starter`).

## Monitoreo

- Endpoint health: `http://<pi>/health`
- Exportador Prometheus (si esta habilitado): `/metrics_prom`
- Grafana/otros dashboards externos pueden consumir el API y WebSockets del panel.
