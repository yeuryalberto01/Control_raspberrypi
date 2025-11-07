"""Panel de control y descubrimiento de dispositivos para Raspberry Pi.

Proporciona una interfaz web y API para localizar dispositivos en la red local
mediante diferentes métodos: Ping (ICMP), ARP (búsqueda de MAC) y escaneo de
puerto SSH.
"""

import asyncio
import contextlib
import ipaddress
import json
import platform
import re
import socket
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional

import fabric
import ifaddr
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Header,
    File,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr

from . import exec_local
from .auth import AuthContext, create_jwt, credential_checker, require_role, validate_token
from .backup_api import make_backup_tar
from .deploy_api import deploy_archive, deploy_git_pull
from .deps import get_settings
from .logs_ws import download_logs, journal_stream
from .metrics import collect_metrics, metrics_stream
from .rate_limit import SimpleRateLimit

from .schemas import ExecCommand, ExecResult, HostInfo, Metrics, ServiceAction, ServiceStatus
from .services import get_multiple_status, list_available_services, manage_service
from .system_ops import collect_host_info, poweroff, reboot
from . import ssh_ws
from . import ai_analyzer
from . import devices_api

# --- Aplicación FastAPI ---
settings = get_settings()

app = FastAPI(
    title="Panel de Descubrimiento Raspberry Pi",
    description="Una herramienta para localizar dispositivos en la red.",
)

app.add_middleware(SimpleRateLimit, limit_per_min=300)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ssh_ws.router, prefix="/ssh", tags=["ssh"])
app.include_router(ai_analyzer.router, prefix="/api/ai", tags=["ai"])
app.include_router(devices_api.router, prefix="/api") # Maneja /api/devices




@app.get("/api/local-networks", response_model=List[str])
def get_local_networks():
    """Detecta y devuelve las redes locales (IPv4 privadas) en notación CIDR."""
    networks = set()
    adapters = ifaddr.get_adapters()

    for adapter in adapters:
        for ip in adapter.ips:
            # Nos interesan las IPs IPv4 que no sean de loopback
            if ip.is_IPv4 and not ip.ip.startswith("127."):
                try:
                    # Construye un objeto de interfaz de red
                    net_interface = ipaddress.ip_interface(f"{ip.ip}/{ip.network_prefix}")
                    # Nos quedamos solo con las redes privadas
                    if net_interface.network.is_private:
                        networks.add(str(net_interface.network))
                except ValueError:
                    continue  # Ignora configuraciones de red inválidas

    if not networks:
        raise HTTPException(
            status_code=404,
            detail="No se pudo detectar ninguna red local privada activa."
        )

    return sorted(list(networks), key=lambda n: ipaddress.ip_network(n).prefixlen, reverse=True)


# --- Constantes y Modelos ---

# Prefijos de MAC asignados a la Raspberry Pi Foundation/Trading Ltd.
# Fuentes: wireshark.org, netify.ai, etc.
RPI_MAC_PREFIXES = {
    "28:CD:C1",
    "B8:27:EB",
    "DC:A6:32",
    "E4:5F:01",
    "D8:3A:DD",
    "2C:CF:67",
    "88:A2:9E",
}

ScanMethod = Literal["ssh", "ping", "arp"]


class DiscoverRequest(BaseModel):
    """Define los parámetros para una solicitud de descubrimiento."""

    scan_method: ScanMethod = Field(
        "ssh", description="Método de escaneo a utilizar."
    )
    network: Optional[str] = Field(
        None, description="Red en formato CIDR, ej: 192.168.1.0/24."
    )
    hosts: Optional[List[str]] = Field(
        None, description="Lista de direcciones IP específicas a analizar."
    )
    timeout: float = Field(
        1.5, gt=0.1, le=10.0, description="Timeout para operaciones de red por host."
    )
    max_concurrency: int = Field(
        100, ge=1, le=512, description="Máximo de tareas de escaneo simultáneas."
    )
    include_reverse_dns: bool = Field(
        True, description="Intentar resolver el nombre de host (DNS inverso)."
    )


class DiscoverResult(BaseModel):
    """Representa el resultado de un descubrimiento para un host."""

    ip: str
    status: Literal["active", "inactive"]
    method: ScanMethod
    hostname: Optional[str] = None
    mac: Optional[str] = None
    ssh_banner: Optional[str] = None
    is_raspberry_pi: bool = False
    details: str


class SSHCredentials(BaseModel):
    """Credenciales para la conexión SSH."""

    user: str = "pi"
    password: SecretStr


class CommandRequest(BaseModel):
    """Solicitud para ejecutar un comando SSH."""

    command: str = Field(..., description="Comando a ejecutar en el dispositivo.")


class StorageInfo(BaseModel):
    """Información de almacenamiento del dispositivo."""

    total: str
    used: str
    free: str
    percent: int


class DeviceDetails(BaseModel):
    """Detalles completos de un dispositivo."""

    storage: Optional[StorageInfo] = None
    uptime: Optional[str] = None
    temp: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: SecretStr


class LoginResponse(BaseModel):
    token: str
    role: str


class ServiceStatusRequest(BaseModel):
    services: List[str] = Field(
        ..., min_length=1, description="Lista de servicios a consultar."
    )


class DeployGitRequest(BaseModel):
    target_dir: str = Field(
        ..., description="Directorio destino whitelisteado para git pull."
    )
    branch: Optional[str] = Field(
        None, description="Nombre de la rama a actualizar (opcional)."
    )

@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
async def auth_login(payload: LoginRequest) -> LoginResponse:
    """Genera un JWT a partir de las credenciales definidas en .env."""
    secret_value = payload.password.get_secret_value()
    context = credential_checker(payload.username, secret_value)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )

    try:
        token = create_jwt(context.subject or payload.username, context.role)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return LoginResponse(token=token, role=context.role)


@app.get("/health", tags=["system"])
async def health_check() -> Dict[str, Any]:
    """Endpoint simple para verificar que la API esta viva."""
    return {
        "status": "ok",
        "uptime_seconds": collect_host_info().uptime_seconds,
        "metrics_interval_hint": settings.metrics_suggested_interval,
    }


@app.get(
    "/info",
    response_model=HostInfo,
    tags=["system"],
)
async def get_host_info(
    # _: AuthContext = Depends(require_role("readonly")),
) -> HostInfo:
    """Devuelve informacion esencial del host."""
    return collect_host_info()


@app.get(
    "/metrics",
    response_model=Metrics,
    tags=["system"],
)
async def get_metrics(
    # _: AuthContext = Depends(require_role("readonly")),
) -> Metrics:
    """Recoge metricas basicas del sistema."""
    return collect_metrics()


@app.get(
    "/service",
    response_model=List[str],
    tags=["system"],
)
async def service_list(
    _: AuthContext = Depends(require_role("readonly")),
) -> List[str]:
    """Lista los servicios disponibles segun la whitelist."""
    try:
        return await list_available_services()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@app.post(
    "/service",
    response_model=ExecResult,
    tags=["system"],
)
async def service_action(
    action: ServiceAction,
    _: AuthContext = Depends(require_role("admin")),
) -> ExecResult:
    """Ejecuta acciones de systemd para un servicio dado."""
    try:
        return await manage_service(action)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc


@app.post(
    "/service/status",
    response_model=List[ServiceStatus],
    tags=["system"],
)
async def service_status(
    payload: ServiceStatusRequest,
    _: AuthContext = Depends(require_role("readonly")),
) -> List[ServiceStatus]:
    """Devuelve el estado de multiples servicios."""
    try:
        return await get_multiple_status(payload.services)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc



@app.post(
    "/deploy/archive",
    tags=["deploy"],
)
async def deploy_archive_endpoint(
    target_dir: str = Query(..., description="Directorio destino whitelisteado."),
    file: UploadFile = File(...),
    _: AuthContext = Depends(require_role("admin")),
) -> Dict[str, object]:
    """Descomprime un paquete en un destino permitido y reinicia el servicio si aplica."""
    return await deploy_archive(file, target_dir)


@app.post(
    "/deploy/git",
    tags=["deploy"],
)
async def deploy_git_endpoint(
    payload: DeployGitRequest,
    _: AuthContext = Depends(require_role("admin")),
) -> Dict[str, object]:
    """Ejecuta git pull en un destino permitido y reinicia el servicio si aplica."""
    return await deploy_git_pull(payload.target_dir, payload.branch)


@app.get(
    "/backup/download",
    tags=["system"],
)
async def backup_download(
    _: AuthContext = Depends(require_role("admin")),
):
    """Genera un archivo tar.gz con configuraciones clave."""
    return await make_backup_tar()


@app.get(
    "/logs/download",
    response_class=PlainTextResponse,
    tags=["system"],
)
async def logs_download_route(
    unit: Optional[str] = Query(None, description="Unidad systemd a consultar."),
    lines: int = Query(
        500,
        ge=10,
        le=5000,
        description="Cantidad de lineas a recuperar del journal.",
    ),
    _: AuthContext = Depends(require_role("readonly")),
) -> PlainTextResponse:
    """Descarga logs recientes de journalctl respetando la whitelist."""
    try:
        content = await download_logs(unit, lines)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return PlainTextResponse(content, media_type="text/plain")


@app.post(
    "/exec",
    response_model=ExecResult,
    tags=["system"],
)
async def exec_command(
    payload: ExecCommand,
    _: AuthContext = Depends(require_role("admin")),
) -> ExecResult:
    """Ejecuta comandos controlados en la Raspberry Pi."""
    return await exec_local.run_command_async(payload.command)


@app.post(
    "/system/reboot",
    response_model=ExecResult,
    tags=["system"],
)
async def system_reboot(
    _: AuthContext = Depends(require_role("admin")),
    confirm: Optional[str] = Header(None, alias="X-Confirm"),
) -> ExecResult:
    """Solicita el reinicio del dispositivo."""
    if confirm != "REBOOT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirma el reinicio enviando X-Confirm: REBOOT",
        )
    return await reboot()


@app.post(
    "/system/poweroff",
    response_model=ExecResult,
    tags=["system"],
)
async def system_poweroff(
    _: AuthContext = Depends(require_role("admin")),
    confirm: Optional[str] = Header(None, alias="X-Confirm"),
) -> ExecResult:
    """Solicita el apagado del dispositivo."""
    if confirm != "POWEROFF":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirma el apagado enviando X-Confirm: POWEROFF",
        )
    return await poweroff()


def _token_from_websocket(websocket: WebSocket) -> Optional[str]:
    token_param = websocket.query_params.get("token")
    if token_param:
        if token_param.lower().startswith("bearer "):
            return token_param.split(" ", 1)[1].strip()
        return token_param.strip()
    auth_header = websocket.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


@app.websocket("/logs/ws")
async def logs_websocket(websocket: WebSocket) -> None:
    """
    WebSocket que transmite los logs en vivo via journalctl.

    El token se puede proporcionar como query string (?token=Bearer%20xxx) o
    cabecera Authorization estandar.
    """

    token = _token_from_websocket(websocket)
    if not validate_token(token, required="readonly"):
        await websocket.close(code=1008, reason="Token invalido o ausente.")
        return

    await websocket.accept()
    unit = websocket.query_params.get("unit")
    stream = None
    try:
        stream = journal_stream(unit)
    except PermissionError as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    try:
        async for line in stream:
            text = line.rstrip()
            if not text:
                continue
            await websocket.send_text(text)
    except WebSocketDisconnect:
        pass
    finally:
        if stream is not None:
            with contextlib.suppress(Exception):
                await stream.aclose()


@app.websocket("/metrics/ws")
async def metrics_websocket(websocket: WebSocket) -> None:
    """WebSocket que emite metricas periodicas."""
    # token = _token_from_websocket(websocket)
    # if not validate_token(token, required="readonly"):
    #     await websocket.close(code=1008, reason="Token invalido o ausente.")
    #     return

    await websocket.accept()
    interval_param = websocket.query_params.get("interval")
    try:
        interval = (
            float(interval_param) if interval_param else settings.metrics_suggested_interval
        )
    except (TypeError, ValueError):
        interval = settings.metrics_suggested_interval

    stream = metrics_stream(interval)
    try:
        async for metric in stream:
            await websocket.send_json(metric.dict())
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await stream.aclose()


# --- L��gica de Descubrimiento (Backend) ---

# --- Lógica de Descubrimiento (Backend) ---


async def stream_event(event_type: str, data: Dict[str, Any]) -> str:
    """Formatea un diccionario como un Server-Sent Event (SSE)."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

def get_targets_from_request(payload: DiscoverRequest) -> List[str]:
    """Extrae y valida las IPs objetivo desde la solicitud."""
    targets: List[str] = []
    if payload.network:
        try:
            network = ipaddress.ip_network(payload.network, strict=False)
            # Para redes grandes, limitamos a un número razonable de hosts
            # para evitar abusos. El generador de hosts es eficiente.
            num_hosts = network.num_addresses
            if num_hosts > 4096:
                raise HTTPException(
                    status_code=400,
                    detail=f"La red especificada es demasiado grande "
                           f"({num_hosts} hosts). Límite: 4096.",
                )
            targets.extend(str(ip) for ip in network.hosts())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Red inválida: {exc}") from exc
    if payload.hosts:
        for host in payload.hosts:
            host = host.strip()
            if not host:
                continue
            try:
                # Valida que sea una IP, pero no la resuelve aún
                ipaddress.ip_address(host)
                targets.append(host)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail=f"Dirección IP inválida: {host}"
                ) from exc

    unique_targets = list(dict.fromkeys(targets))
    if not unique_targets:
        raise HTTPException(
            status_code=400,
            detail="Debe indicar al menos una red o una lista de IPs.",
        )
    return unique_targets


async def run_command(command: str) -> tuple[str, str]:
    """Ejecuta un comando de shell y devuelve su salida."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(errors="ignore"), stderr.decode(errors="ignore")


async def discover_by_arp(
    targets: List[str],
    payload: DiscoverRequest
) -> AsyncGenerator[str, None]:
    """Descubre hosts usando la tabla ARP y heurísticas de MAC."""
    yield await stream_event(
        "log", {"message": "Iniciando escaneo ARP..."}
    )
    # 1. Hacer ping a todos los hosts para poblar la tabla ARP
    ping_command = "ping -n 1 -w 100" if platform.system() == "Windows" else "ping -c 1 -W 0.1"

    async def ping_host(ip):
        await run_command(f"{ping_command} {ip}")

    semaphore = asyncio.Semaphore(payload.max_concurrency)
    async def safe_ping(ip):
        async with semaphore:
            await ping_host(ip)

    await asyncio.gather(*(safe_ping(ip) for ip in targets), return_exceptions=True)
    yield await stream_event("log", {"message": "Tabla ARP actualizada. Obteniendo datos..."})

    # 2. Leer la tabla ARP
    stdout, _ = await run_command("arp -a")

    # 3. Procesar resultados
    # Expresión regular para encontrar IPs y MACs en la salida de 'arp -a'
    # Funciona tanto en Windows como en Linux.
    arp_pattern = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[\s\t]+([\w\:-]+)")

    found_hosts = set()
    for ip, mac in arp_pattern.findall(stdout):
        if ip not in targets:
            continue

        mac = mac.replace("-", ":").upper()
        is_rpi = any(mac.startswith(prefix) for prefix in RPI_MAC_PREFIXES)

        result = DiscoverResult(
            ip=ip,
            status="active",
            method="arp",
            mac=mac,
            is_raspberry_pi=is_rpi,
            details=f"MAC: {mac}",
        )
        yield await stream_event("result", result.dict())
        found_hosts.add(ip)

    # Reportar hosts inactivos
    for ip in set(targets) - found_hosts:
        result = DiscoverResult(ip=ip, status="inactive", method="arp", details="No responde a ARP")
        yield await stream_event("result", result.dict())


async def discover_by_ping(
    targets: List[str],
    payload: DiscoverRequest
) -> AsyncGenerator[str, None]:
    """Descubre hosts activos mediante ping (ICMP)."""
    yield await stream_event("log", {"message": "Iniciando escaneo con Ping..."})
    ping_command = "ping -n 1 -w 500" if platform.system() == "Windows" else "ping -c 1 -W 0.5"

    semaphore = asyncio.Semaphore(payload.max_concurrency)

    async def worker(ip: str):
        async with semaphore:
            yield await stream_event("log", {"message": f"Haciendo ping a {ip}..."})
            stdout, _ = await run_command(f"{ping_command} {ip}")

            # Heurística simple para determinar si el host está activo
            is_active = "ttl" in stdout.lower() or "bytes from" in stdout.lower()

            result = DiscoverResult(
                ip=ip,
                status="active" if is_active else "inactive",
                method="ping",
                details="Responde a Ping" if is_active else "No responde a Ping",
            )
            yield await stream_event("result", result.dict())

    for task in asyncio.as_completed([worker(ip) for ip in targets]):
        async for item in task.result():
            yield item


async def discover_by_ssh(
    targets: List[str],
    payload: DiscoverRequest
) -> AsyncGenerator[str, None]:
    """Descubre hosts con puerto SSH abierto."""
    yield await stream_event("log", {"message": "Iniciando escaneo de puerto SSH (22)..."})
    semaphore = asyncio.Semaphore(payload.max_concurrency)

    async def worker(ip: str):
        async with semaphore:
            yield await stream_event("log", {"message": f"Probando SSH en {ip}..."})

            result_data = {
                "ip": ip, "status": "inactive", "method": "ssh",
                "details": "Puerto 22 cerrado o filtrado"
            }

            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, 22), payload.timeout
                )

                result_data["status"] = "active"
                result_data["details"] = "Puerto 22 abierto"

                banner = ""
                try:
                    banner_bytes = await asyncio.wait_for(reader.readline(), 0.5)
                    banner = banner_bytes.decode("utf-8", errors="ignore").strip()
                    if banner:
                        result_data["ssh_banner"] = banner
                        result_data["details"] += f" ({banner})"
                finally:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await writer.wait_closed()

                # Heurísticas para detectar RPi
                is_rpi = "raspbian" in (banner or "").lower()

                if payload.include_reverse_dns:
                    hostname = None
                    try:
                        hostname, *_ = await asyncio.to_thread(socket.gethostbyaddr, ip)
                        result_data["hostname"] = hostname
                        if not is_rpi:
                            is_rpi = "raspberry" in (hostname or "").lower()
                    except (socket.herror, socket.gaierror):
                        pass

                result_data["is_raspberry_pi"] = is_rpi

            except (asyncio.TimeoutError, OSError):
                pass # Mantiene el estado inactivo

            result = DiscoverResult(**result_data)
            yield await stream_event("result", result.dict())

    for task in asyncio.as_completed([worker(ip) for ip in targets]):
        async for item in task.result():
            yield item


# --- Endpoints de la API ---


@app.get("/health/legacy")
def legacy_health() -> Dict[str, bool]:
    """Endpoint de health check para monitoreo básico."""
    return {"ok": True}


@app.post("/api/discover")
async def discover_stream(request: Request, payload: DiscoverRequest) -> StreamingResponse:
    """
    Inicia un escaneo de descubrimiento y transmite los resultados en tiempo real
    usando Server-Sent Events (SSE).
    """
    targets = get_targets_from_request(payload)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Elige el generador de descubrimiento basado en el método
        discovery_methods = {
            "ssh": discover_by_ssh,
            "ping": discover_by_ping,
            "arp": discover_by_arp,
        }
        discover_func = discovery_methods[payload.scan_method]

        # Itera sobre el generador y transmite cada evento
        async for event_str in discover_func(targets, payload):
            if await request.is_disconnected():
                break
            yield event_str

        yield await stream_event("log", {"message": "FIN_ESCANEADO"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/device/details/{ip}", response_model=DeviceDetails)
async def get_device_details(ip: str, creds: SSHCredentials):
    """
    Obtiene detalles de un dispositivo específico (almacenamiento, etc.)
    mediante una conexión SSH.
    """
    connect_kwargs = {"password": creds.password.get_secret_value()}
    conn = fabric.Connection(host=ip, user=creds.user, connect_kwargs=connect_kwargs)
    details = DeviceDetails()

    try:
        # Usar un timeout corto para la conexión inicial
        conn.open()

        # 1. Obtener uso de disco
        # Formato: Total Usado Libre Porcentaje
        cmd_df = "df --output=size,used,avail,pcent / | tail -n 1"
        result_df = await asyncio.to_thread(conn.run, cmd_df, hide=True, timeout=5)
        stdout_df = result_df.stdout.strip()
        match = re.search(r"\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%", stdout_df)
        if match:
            total_kb, used_kb, _, percent = match.groups()
            details.storage = StorageInfo(
                total=f"{int(total_kb) / 1024 / 1024:.1f}G",
                used=f"{int(used_kb) / 1024 / 1024:.1f}G",
                free=f"{(int(total_kb) - int(used_kb)) / 1024 / 1024:.1f}G",
                percent=int(percent),
            )

        # 2. Obtener uptime
        cmd_uptime = "uptime -p"
        result_uptime = await asyncio.to_thread(conn.run, cmd_uptime, hide=True, timeout=5)
        details.uptime = result_uptime.stdout.strip().replace("up ", "")

        # 3. Obtener temperatura (solo en RPi)
        cmd_temp = "vcgencmd measure_temp"
        # Usar `warn=True` para que no lance excepción si el comando no existe
        result_temp = await asyncio.to_thread(conn.run, cmd_temp, hide=True, warn=True, timeout=5)
        if result_temp.ok:
            details.temp = result_temp.stdout.strip().replace("temp=", "")

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error en {ip}: {e}"
        ) from e
    finally:
        if conn.is_connected:
            await asyncio.to_thread(conn.close)

    return details


@app.post("/api/device/command/{ip}", response_model=Dict[str, str])
async def execute_command(ip: str, creds: SSHCredentials, payload: CommandRequest):
    """
    Ejecuta un comando en un dispositivo específico mediante SSH.
    """
    connect_kwargs = {"password": creds.password.get_secret_value()}
    conn = fabric.Connection(host=ip, user=creds.user, connect_kwargs=connect_kwargs)

    try:
        conn.open()
        result = await asyncio.to_thread(conn.run, payload.command, hide=True, timeout=10)
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": str(result.exited)}
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error ejecutando comando en {ip}: {e}"
        ) from e
    finally:
        if conn.is_connected:
            await asyncio.to_thread(conn.close)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Devuelve la interfaz principal del panel de descubrimiento."""
    return '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Panel de Descubrimiento</title>
        <style>
            :root {
                --color-primary: #0f766e; --color-primary-dark: #115e59;
                --color-bg: #f3f4f6; --color-fg: #1f2937;
                --color-card-bg: white; --color-border: #d1d5db;
                --color-success: #047857; --color-error: #b91c1c;
                --shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1);
                font-family: "Segoe UI", system-ui, sans-serif;
            }
            @media (prefers-color-scheme: dark) {
                :root {
                    --color-primary: #5eead4; --color-primary-dark: #0d9488;
                    --color-bg: #111827; --color-fg: #d1d5db;
                    --color-card-bg: #1f2937; --color-border: #4b5563;
                }
            }
            body { margin: 0; background-color: var(--color-bg); color: var(--color-fg); }
            header { background: var(--color-primary); color: white; padding: 1.5rem; text-align: center; }
            @media (prefers-color-scheme: dark) { header { color: #111827; } }
            main { max-width: 1024px; margin: 2rem auto; padding: 0 1rem; }
            .card { background: var(--color-card-bg); border-radius: 0.5rem; box-shadow: var(--shadow); padding: 1.5rem; margin-bottom: 2rem; }
            form { display: grid; gap: 1rem; }
            .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
            label { font-weight: 600; display: block; margin-bottom: 0.25rem; }
            input, textarea, select, button {
                width: 100%; padding: 0.65rem; border-radius: 0.375rem;
                border: 1px solid var(--color-border); font-size: 1rem;
                background-color: var(--color-card-bg); color: var(--color-fg);
                box-sizing: border-box;
            }
            button { background: var(--color-primary); color: white; border: none; cursor: pointer; transition: background 0.2s; }
            @media (prefers-color-scheme: dark) { button { color: #111827; } }
            button:hover { background: var(--color-primary-dark); }
            button:disabled { background: #9ca3af; cursor: not-allowed; }
            #console {
                background-color: #111827; color: #d1d5db; font-family: monospace;
                height: 150px; overflow-y: scroll; padding: 1rem;
                border-radius: 0.375rem; margin-top: 1.5rem; font-size: 0.875rem;
                border: 1px solid var(--color-border);
            }
            #console div { white-space: pre-wrap; }
            table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
            th, td { border-bottom: 1px solid var(--color-border); padding: 0.75rem; text-align: left; }
            th { font-weight: 700; }
            .badge {
                display: inline-block; padding: 0.25rem 0.6rem; border-radius: 99px;
                font-size: 0.8rem; font-weight: 600;
            }
            .badge-rpi { background-color: #dcfce7; color: #166534; }
            @media (prefers-color-scheme: dark) { .badge-rpi { background-color: #166534; color: #dcfce7; } }
            .badge-neutral { background-color: #e5e7eb; color: #374151; }
            @media (prefers-color-scheme: dark) { .badge-neutral { background-color: #4b5563; color: #d1d5db; } }
            .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 0.5rem; }
            .status-active { background-color: #22c55e; }
            .status-inactive { background-color: #ef4444; }
            .progress-bar {
                width: 100%;
                background-color: #e9ecef;
                border-radius: 0.25rem;
                overflow: hidden;
                height: 1.5rem;
                display: flex;
                font-size: 0.8rem;
                line-height: 1.5rem;
            }
            .progress-bar-inner {
                background-color: var(--color-primary);
                color: white;
                text-align: center;
                white-space: nowrap;
                padding: 0 0.5rem;
                transition: width 0.6s ease;
            }
            @media (prefers-color-scheme: dark) {
                .progress-bar { background-color: #4b5563; }
                .progress-bar-inner { color: #111827; }
            }
            .details-btn {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
                border-width: 0;
            }
        </style>
    </head>
    <body>
        <header><h1>Panel de Descubrimiento de Dispositivos</h1></header>
        <main>
            <div class="card">
                <h2>Configuración del Escaneo</h2>
                <form id="scan-form">
                    <div class="form-grid">
                        <div>
                            <label for="scan-method">Método</label>
                            <select id="scan-method">
                                <option value="ssh">SSH (Verificar Servicio)</option>
                                <option value="arp">ARP (Identificar Hardware)</option>
                                <option value="ping">Ping (Verificar Actividad)</option>
                            </select>
                        </div>
                        <div>
                            <label for="network">Red (CIDR)</label>
                            <div style="display: flex; gap: 0.5rem;">
                                <input type="text" id="network" placeholder="192.168.1.0/24" autocomplete="off" style="width: 100%;" />
                                <button type="button" id="detect-network-btn" title="Detectar red local automáticamente" style="padding: 0 0.8rem;">?</button>
                            </div>
                        </div>
                        <div>
                            <label for="ssh-user">Usuario SSH</label>
                            <input type="text" id="ssh-user" value="pi" autocomplete="off" />
                        </div>
                        <div>
                            <label for="ssh-pass">Contraseña SSH</label>
                            <input type="password" id="ssh-pass" autocomplete="off" />
                        </div>
                    </div>
                    <div>
                        <label for="hosts">Hosts específicos (separados por coma o espacio)</label>
                        <textarea id="hosts" rows="2" placeholder="192.168.1.10, 192.168.1.11"></textarea>
                    </div>
                    <button type="submit" id="scan-button">Buscar Dispositivos</button>
                </form>
            </div>

            <div class="card">
                <h2>Consola en Tiempo Real</h2>
                <div id="console"><div style="color: #6b7280;">La salida del escaneo aparecerá aquí...</div></div>
            </div>

            <div class="card">
                <h2>Resultados</h2>
                <table id="results-table">
                    <thead>
                        <tr>
                            <th>Estado</th>
                            <th>IP</th>
                            <th>Hostname</th>
                            <th>MAC</th>
                            <th>Identificado como</th>
                            <th>Almacenamiento</th>
                            <th>Acciones</th>
                            <th>Comandos</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Los resultados se insertarán aquí dinámicamente -->
                    </tbody>
                </table>
            </div>
        </main>

        <script>
            const form = document.getElementById("scan-form");
            const scanButton = document.getElementById("scan-button");
            const consoleLog = document.getElementById("console");
            const tableBody = document.querySelector("#results-table tbody");
            const detectNetworkBtn = document.getElementById("detect-network-btn");
            let eventSource;

            function addToConsole(message, isError = false) {
                const entry = document.createElement("div");
                entry.textContent = `> ${message}`;
                if (isError) {
                    entry.style.color = "var(--color-error)";
                }
                const placeholder = consoleLog.querySelector("div[style]");
                if (placeholder) placeholder.remove();
                consoleLog.appendChild(entry);
                consoleLog.scrollTop = consoleLog.scrollHeight;
            }

            function parseHosts(raw) {
                return raw.split(/[
s,]+/).map(item => item.trim()).filter(Boolean);
            }

            function clearResults() {
                tableBody.innerHTML = "";
                consoleLog.innerHTML = `<div style="color: #6b7280;">Iniciando nuevo escaneo...</div>`;
            }

            function renderResultRow(item) {
                let ipId = item.ip.split('.').join('-');
                let row = tableBody.querySelector(`#ip-${ipId}`);
                if (!row) {
                    row = document.createElement("tr");
                    row.id = `ip-${ipId}`;
                    tableBody.appendChild(row);
                }

                const rpiBadge = `<span class="badge badge-rpi">Raspberry Pi</span>`;
                const neutralBadge = `<span class="badge badge-neutral">Otro</span>`;
                const storageCellId = `storage-${row.id}`;
                const actionsCellId = `actions-${row.id}`;

                // La columna de detalles original ahora es la de acciones/info extra
                row.innerHTML = `
                    <td><span class="status-dot status-${item.status}"></span> ${item.status}</td>
                    <td>${item.ip}</td>
                    <td>${item.hostname || "—"}</td>
                    <td>${item.mac || "—"}</td>
                    <td>${item.is_raspberry_pi ? rpiBadge : neutralBadge}</td>
                    <td id="${storageCellId}">${item.ssh_banner || "—"}</td>
                    <td id="${actionsCellId}">
                        ${item.is_raspberry_pi && item.status === 'active'
                            ? `<button class="details-btn" data-ip="${item.ip}">Detalles</button>`
                            : "N/A"}
                    </td>
                    <td>
                        ${item.status === 'active'
                            ? `<input type="text" placeholder="Comando" id="cmd-${ipId}" style="width: 120px;"> <button class="cmd-btn" data-ip="${item.ip}">Ejecutar</button>`
                            : "N/A"}
                    </td>
                `;
            }

            async function getDeviceDetails(ip) {
                const user = document.getElementById("ssh-user").value;
                const password = document.getElementById("ssh-pass").value;
                let ipId = ip.split('.').join('-');
                const storageCell = document.querySelector(`#storage-ip-${ipId}`);
                const actionCell = document.querySelector(`#actions-ip-${ipId}`);

                if (!password) {
                    addToConsole("Por favor, introduzca la contraseña SSH.", true);
                    return;
                }

                storageCell.innerHTML = "Cargando...";
                actionCell.innerHTML = "...";

                try {
                    const response = await fetch(`/api/device/details/${ip}`, {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({ user, password })
                    });

                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || "Error en la respuesta del servidor");
                    }

                    const data = await response.json();
                    let html = "Error al parsear datos";
                    if (data.storage) {
                        const s = data.storage;
                        html = `
                            <div class="progress-bar" title="${s.used} / ${s.total} (${s.percent}%)">
                                <div class="progress-bar-inner" style="width: ${s.percent}%;">
                                    ${s.percent}%
                                </div>
                            </div>
                        `;
                    }
                    storageCell.innerHTML = html;

                    let detailsText = [];
                    if(data.uptime) detailsText.push(`Activo: ${data.uptime}`);
                    if(data.temp) detailsText.push(`Temp: ${data.temp}`);
                    actionCell.textContent = detailsText.join(', ') || 'OK';

                } catch (error) {
                    console.error("Error obteniendo detalles:", error);
                    storageCell.innerHTML = `<span style="color:var(--color-error)">Falló</span>`;
                    actionCell.textContent = error.message.substring(0, 40) + '...';
                }
            }

            async function executeCommand(ip) {
                const user = document.getElementById("ssh-user").value;
                const password = document.getElementById("ssh-pass").value;
                let ipId = ip.split('.').join('-');
                const cmdInput = document.getElementById(`cmd-${ipId}`);
                const command = cmdInput.value.trim();
                if (!command) {
                    addToConsole("Por favor, ingresa un comando.", true);
                    return;
                }
                if (!password) {
                    addToConsole("Por favor, ingresa la contraseña SSH.", true);
                    return;
                }

                addToConsole(`Ejecutando "${command}" en ${ip}...`);
                try {
                    const response = await fetch(`/api/device/command/${ip}`, {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({ user, password, command })
                    });

                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || "Error en la respuesta del servidor");
                    }

                    const data = await response.json();
                    let output = `Salida de "${command}" en ${ip}:\n`;
                    if (data.stdout) output += `STDOUT: ${data.stdout}\n`;
                    if (data.stderr) output += `STDERR: ${data.stderr}\n`;
                    output += `Código de salida: ${data.exit_code}`;
                    addToConsole(output);

                } catch (error) {
                    console.error("Error ejecutando comando:", error);
                    addToConsole(`Fallo al ejecutar comando en ${ip}: ${error.message}`, true);
                }
            }

            detectNetworkBtn.addEventListener("click", async () => {
                addToConsole("Detectando red local...");
                try {
                    const response = await fetch("/api/local-networks");
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || "Error del servidor");
                    }
                    const networks = await response.json();
                    if (networks.length > 0) {
                        document.getElementById("network").value = networks[0];
                        addToConsole(`Red detectada: ${networks[0]}`);
                    } else {
                        addToConsole("No se encontraron redes locales privadas.", true);
                    }
                } catch (error) {
                    console.error("Error detectando la red:", error);
                    addToConsole(`Fallo al detectar red: ${error.message}`, true);
                }
            });

            tableBody.addEventListener("click", (event) => {
                if (event.target.classList.contains("details-btn")) {
                    const ip = event.target.dataset.ip;
                    getDeviceDetails(ip);
                } else if (event.target.classList.contains("cmd-btn")) {
                    const ip = event.target.dataset.ip;
                    executeCommand(ip);
                }
            });

            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                if (scanButton.disabled) return;

                if (eventSource) {
                    eventSource.close();
                }
                clearResults();
                scanButton.disabled = true;
                scanButton.textContent = "Escaneando...";

                const body = {
                    scan_method: document.getElementById("scan-method").value,
                    network: document.getElementById("network").value.trim(),
                    hosts: parseHosts(document.getElementById("hosts").value),
                    timeout: 1.5,
                    max_concurrency: 100,
                    include_reverse_dns: true,
                };

                eventSource = new EventSource("/api/discover", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(body)
                });

                eventSource.addEventListener("log", (e) => {
                    const data = JSON.parse(e.data);
                    if (data.message === "FIN_ESCANEADO") {
                        eventSource.close();
                        scanButton.disabled = false;
                        scanButton.textContent = "Buscar Dispositivos";
                        addToConsole("Escaneo finalizado.");
                    } else {
                        addToConsole(data.message);
                    }
                });

                eventSource.addEventListener("result", (e) => {
                    const data = JSON.parse(e.data);
                    renderResultRow(data);
                });

                eventSource.onerror = (err) => {
                    console.error("EventSource falló:", err);
                    addToConsole("Error de conexión con el servidor. El escaneo puede haberse interrumpido.", true);
                    eventSource.close();
                    scanButton.disabled = false;
                    scanButton.textContent = "Buscar Dispositivos";
                };
            });

            (function(es) {
                const es_send = es.prototype._send;
                es.prototype._send = function(body) {
                    if (!this.options.body) {
                        return es_send.call(this, body);
                    }
                    const xhr = new XMLHttpRequest();
                    this.xhr = xhr;
                    xhr.open("POST", this.url, true);
                    xhr.withCredentials = this.options.withCredentials;
                    for (const header in this.options.headers) {
                        xhr.setRequestHeader(header, this.options.headers[header]);
                    }
                    xhr.onreadystatechange = () => {
                        if (xhr.readyState === 3 || (xhr.readyState === 4 && xhr.status === 200)) {
                            this._onxhrdata(xhr);
                        } else if (xhr.readyState === 4) {
                            this._onxhrerror(xhr);
                        }
                    };
                    xhr.send(this.options.body);
                };
                const es_close = es.prototype.close;
                es.prototype.close = function() {
                    if (this.xhr) {
                        this.xhr.abort();
                    }
                    es_close.call(this);
                };
            })(EventSource);

        </script>
    </body>
    </html>
    '''
