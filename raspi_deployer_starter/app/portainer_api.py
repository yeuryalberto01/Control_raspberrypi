"""
Integracion ligera con el API de Portainer (endpoints, stacks y healthcheck).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import AuthContext, require_role
from .deps import Settings, get_settings
from .schemas import PortainerEndpoint, PortainerStack

router = APIRouter(prefix="/portainer", tags=["portainer"])


def _get_portainer_base(settings: Settings) -> str:
    base = (settings.portainer_url or "").strip()
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Configura PORTAINER_URL y PORTAINER_API_KEY en el archivo .env para habilitar esta funcion.",
        )
    return base.rstrip("/")


def _get_portainer_headers(settings: Settings) -> Dict[str, str]:
    api_key = (settings.portainer_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="PORTAINER_API_KEY no esta definido en .env.",
        )
    return {"X-API-Key": api_key}


async def _portainer_request(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> Any:
    base_url = _get_portainer_base(settings)
    headers = _get_portainer_headers(settings)
    url = f"{base_url}{path}"
    async with httpx.AsyncClient(timeout=15, verify=settings.portainer_verify_ssl) as client:
        try:
            response = await client.request(method, url, headers=headers, params=params, json=json)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"No se pudo contactar Portainer: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Portainer respondio con {response.status_code}: {response.text}",
        )
    if not response.content:
        return None
    return response.json()


def _to_endpoint(data: Dict[str, Any]) -> PortainerEndpoint:
    return PortainerEndpoint(
        id=data.get("Id", 0),
        name=data.get("Name", ""),
        status=str(data.get("Status", "")),
        url=data.get("URL"),
        group_id=data.get("GroupId"),
    )


def _to_stack(data: Dict[str, Any]) -> PortainerStack:
    return PortainerStack(
        id=data.get("Id", 0),
        name=data.get("Name", ""),
        endpoint_id=data.get("EndpointId", 0),
        status=str(data.get("Status")) if data.get("Status") is not None else None,
        created=data.get("Created"),
        updated=data.get("Updated"),
        project_path=data.get("ProjectPath"),
    )


@router.get("/health")
async def portainer_health(
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Devuelve el estado general de Portainer."""
    data = await _portainer_request(settings, "GET", "/system/status")
    return data


@router.get("/endpoints", response_model=List[PortainerEndpoint])
async def portainer_endpoints(
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> List[PortainerEndpoint]:
    """Lista los endpoints registrados en Portainer."""
    data = await _portainer_request(settings, "GET", "/endpoints")
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Respuesta inesperada de Portainer.")
    return [_to_endpoint(item) for item in data]


@router.get("/stacks", response_model=List[PortainerStack])
async def portainer_stacks(
    endpoint_id: Optional[int] = Query(None, description="Filtra stacks por endpointId."),
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> List[PortainerStack]:
    """Devuelve los stacks conocidos en Portainer."""
    data = await _portainer_request(settings, "GET", "/stacks")
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Respuesta inesperada de Portainer.")
    stacks = [_to_stack(item) for item in data]
    if endpoint_id is not None:
        stacks = [stack for stack in stacks if stack.endpoint_id == endpoint_id]
    return stacks


@router.get("/stacks/{stack_id}", response_model=PortainerStack)
async def portainer_stack_detail(
    stack_id: int,
    _: AuthContext = Depends(require_role("readonly")),
    settings: Settings = Depends(get_settings),
) -> PortainerStack:
    """Obtiene la descripcion completa de un stack."""
    data = await _portainer_request(settings, "GET", f"/stacks/{stack_id}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Respuesta inesperada de Portainer.")
    return _to_stack(data)


@router.post("/stacks/{stack_id}/redeploy", response_model=PortainerStack)
async def portainer_stack_redeploy(
    stack_id: int,
    pull_image: bool = Query(True, description="Forzar pull de imagenes antes de desplegar."),
    prune: bool = Query(False, description="Eliminar recursos hu��rfanos tras el despliegue."),
    endpoint_id: Optional[int] = Query(
        None,
        description="Endpoint ID (solo necesario si el stack esta asociado a varios endpoints).",
    ),
    _: AuthContext = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
) -> PortainerStack:
    """Re-despliega un stack basado en Git utilizando el API de Portainer."""
    stack_data: Optional[Dict[str, Any]] = None
    if endpoint_id is None:
        stack_data = await _portainer_request(settings, "GET", f"/stacks/{stack_id}")
        if not isinstance(stack_data, dict):
            raise HTTPException(status_code=502, detail="Respuesta inesperada de Portainer.")
        endpoint_id = stack_data.get("EndpointId")
    if endpoint_id is None:
        raise HTTPException(
            status_code=400,
            detail="No se pudo determinar el endpointId del stack. Indicalo manualmente.",
        )
    await _portainer_request(
        settings,
        "POST",
        f"/stacks/{stack_id}/git/redeploy",
        params={"endpointId": endpoint_id},
        json={"PullImage": pull_image, "Prune": prune},
    )
    if stack_data is None:
        stack_data = await _portainer_request(settings, "GET", f"/stacks/{stack_id}")
    return _to_stack(stack_data)
