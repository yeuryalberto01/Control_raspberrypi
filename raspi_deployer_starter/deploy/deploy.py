import os, sys, tempfile
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent

from fabric import Connection
from invoke import task
from jinja2 import Template
from dotenv import load_dotenv
from pi_ssh import RaspberryPiDiscoverer, RaspberryPiDiscoveryError

load_dotenv(ROOT / ".env")

APP_NAME = os.getenv("APP_NAME", "mi_app")
PI_HOST  = os.getenv("PI_HOST", "raspberrypi.local")
PI_USER  = os.getenv("PI_USER", "pi")
PI_DIR   = f"/opt/{APP_NAME}"
VENV     = f"{PI_DIR}/.venv"
SERVICE  = f"{APP_NAME}.service"
PORT     = int(os.getenv("APP_PORT", "9090"))
FINDER   = RaspberryPiDiscoverer(user=PI_USER)


@lru_cache(maxsize=1)
def resolve_pi_host() -> str:
    """Return the reachable Raspberry Pi host using discovery fallbacks."""

    try:
        result = FINDER.ensure_host(host=PI_HOST)
    except RaspberryPiDiscoveryError as exc:
        raise RuntimeError(
            "No fue posible descubrir la Raspberry Pi. Ajusta PI_HOST o habilita mDNS/SSH."
        ) from exc
    return result.host

def conn():
    key = os.path.expanduser("~/.ssh/id_rsa")
    host = resolve_pi_host()
    return Connection(host=host, user=PI_USER, connect_kwargs={"key_filename": key})

def render_service():
    tpl_path = HERE / "rpi.service.j2"
    tpl = Template(tpl_path.read_text(encoding="utf-8"))
    return tpl.render(app_name=APP_NAME, workdir=PI_DIR, venv=VENV, port=PORT)

@task
def ping(c):
    "Prueba SSH y quién soy en la Pi."
    with conn() as r:
        r.run("uname -a && whoami")

@task
def sync(c):
    "Sincroniza código al Pi (rsync vía ssh)."
    excludes = ["__pycache__", ".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache", "dist"]
    ex = " ".join([f'--exclude="{e}"' for e in excludes])
    host = resolve_pi_host()
    os.system(f'rsync -avz {ex} -e "ssh" "{ROOT}/" {PI_USER}@{host}:{PI_DIR}/')

@task
def setup(c):
    "Crea carpetas, venv e instala dependencias."
    with conn() as r:
        r.run(f"sudo mkdir -p {PI_DIR} && sudo chown -R {PI_USER}:{PI_USER} {PI_DIR}")
        r.run(f"python3 -m venv {VENV}")
        r.run(f"{VENV}/bin/pip -q install --upgrade pip")
        if (ROOT / "requirements.txt").exists():
            r.run(f"{VENV}/bin/pip install -r {PI_DIR}/requirements.txt")
        else:
            r.run(f"{VENV}/bin/pip install fastapi uvicorn[standard] requests")

@task
def service_install(c):
    "Instala/recarga service systemd."
    unit = render_service()
    tmp = Path(tempfile.gettempdir()) / f"{SERVICE}"
    tmp.write_text(unit, encoding="utf-8")
    host = resolve_pi_host()
    os.system(f'scp "{tmp}" {PI_USER}@{host}:/tmp/{SERVICE}')
    with conn() as r:
        r.run(f"sudo mv /tmp/{SERVICE} /etc/systemd/system/{SERVICE}")
        r.run("sudo systemctl daemon-reload")
        r.run(f"sudo systemctl enable {SERVICE}")

@task
def restart(c):
    "Reinicia el servicio."
    with conn() as r:
        r.run(f"sudo systemctl restart {SERVICE}")
        r.run(f"sleep 1 && sudo systemctl status {SERVICE} --no-pager || true")

@task
def logs(c):
    "Muestra logs de systemd."
    with conn() as r:
        r.run(f"sudo journalctl -u {SERVICE} -n 100 --no-pager || true")
        r.run(f"sudo journalctl -u {SERVICE} -f")

@task
def test(c):
    "Corre pytest en la Pi."
    with conn() as r:
        r.run(f"cd {PI_DIR} && {VENV}/bin/pytest -q || true")

@task
def health(c):
    "Health-check HTTP simple desde tu PC."
    import requests, time
    host = resolve_pi_host()
    url = f"http://{host}:{PORT}/health"
    try:
        resp = requests.get(url, timeout=5)
        print("HEALTH:", resp.status_code, resp.text[:200])
    except Exception as e:
        print("HEALTH FAIL:", e)
        sys.exit(1)

@task
def deploy_all(c):
    "Pipeline completo: sync -> setup -> service -> restart -> test -> health."
    sync(c)
    setup(c)
    service_install(c)
    restart(c)
    test(c)
    health(c)
