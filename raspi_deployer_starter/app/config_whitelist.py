"""
Whitelist loader for services and log units.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List, Optional, Set

import yaml

from .deps import get_settings


class _Whitelist:
    def __init__(
        self,
        services: Optional[Set[str]],
        logs_units: Optional[Set[str]],
        raw: Dict[str, object],
    ) -> None:
        self.services = services
        self.logs_units = logs_units
        self.raw = raw

    def deploy_config(self) -> Dict[str, object]:
        deploy = self.raw.get("deploy")
        if isinstance(deploy, dict):
            return deploy
        return {}


def _normalise(items: Optional[List[str]]) -> Optional[Set[str]]:
    if not items:
        return None
    cleaned = {entry.strip() for entry in items if entry and entry.strip()}
    return cleaned or None


@lru_cache()
def load_whitelist() -> _Whitelist:
    settings = get_settings()
    path = os.path.abspath(settings.whitelist_path)
    if not os.path.exists(path):
        return _Whitelist(None, None)

    with open(path, "r", encoding="utf-8") as handler:
        data: Dict[str, object] = yaml.safe_load(handler) or {}

    services = _normalise(data.get("services"))  # type: ignore[arg-type]
    logs_units = _normalise(data.get("logs_units"))  # type: ignore[arg-type]
    return _Whitelist(services, logs_units, data)


def refresh_whitelist() -> None:
    load_whitelist.cache_clear()


def list_services() -> List[str]:
    whitelist = load_whitelist()
    if whitelist.services is None:
        return []
    return sorted(whitelist.services)


def list_log_units() -> List[str]:
    whitelist = load_whitelist()
    if whitelist.logs_units is None:
        return []
    return sorted(whitelist.logs_units)


def allowed_service(name: str) -> bool:
    whitelist = load_whitelist()
    if whitelist.services is None:
        return True
    return name in whitelist.services


def allowed_log_unit(unit: Optional[str]) -> bool:
    if unit is None:
        return True
    whitelist = load_whitelist()
    if whitelist.logs_units is None:
        return True
    return unit in whitelist.logs_units


def allowed_deploy_target(target: str) -> bool:
    whitelist = load_whitelist()
    targets = whitelist.deploy_config().get("allowed_targets", [])
    if not targets or not isinstance(targets, list):
        return False
    target_abs = os.path.abspath(target)
    allowed = {os.path.abspath(str(item)) for item in targets}
    return target_abs in allowed


def deploy_service_to_restart() -> Optional[str]:
    whitelist = load_whitelist()
    service = whitelist.deploy_config().get("service_to_restart")
    return service if isinstance(service, str) and service.strip() else None


def deploy_config() -> Dict[str, object]:
    return load_whitelist().deploy_config()
