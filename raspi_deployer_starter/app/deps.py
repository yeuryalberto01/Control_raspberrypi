"""
Application configuration helpers.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from dotenv import load_dotenv

# Load .env so os.getenv can pick values defined there.
load_dotenv()


class Settings:
    """Runtime settings loaded from environment variables."""

    def __init__(
        self,
        *,
        app_host: str,
        app_port: int,
        app_token: str,
        cors_allow_origins: str,
        metrics_suggested_interval: int,
        admin_user: str,
        admin_pass: str,
        readonly_user: str,
        readonly_pass: str,
        jwt_secret: str,
        jwt_ttl_seconds: int,
        whitelist_path: str,
        devices_reg_path: str,
        jwt_algorithm: str = "HS256",
        ai_api_endpoint: str = "",
        ai_api_key: str = "",
        docker_host: str = "",
        portainer_url: str = "",
        portainer_api_key: str = "",
        portainer_verify_ssl: bool = False,
    ) -> None:
        self.app_host = app_host
        self.app_port = app_port
        self.app_token = app_token
        self.cors_allow_origins = cors_allow_origins
        self.metrics_suggested_interval = metrics_suggested_interval
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.readonly_user = readonly_user
        self.readonly_pass = readonly_pass
        self.jwt_secret = jwt_secret
        self.jwt_ttl_seconds = jwt_ttl_seconds
        self.jwt_algorithm = jwt_algorithm
        self.whitelist_path = whitelist_path
        self.devices_reg_path = devices_reg_path
        self.ai_api_endpoint = ai_api_endpoint
        self.ai_api_key = ai_api_key
        self.docker_host = docker_host
        self.portainer_url = portainer_url
        self.portainer_api_key = portainer_api_key
        self.portainer_verify_ssl = portainer_verify_ssl

    @classmethod
    def from_env(cls) -> "Settings":
        def _get_int(key: str, default: int) -> int:
            raw = os.getenv(key)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _get_bool(key: str, default: bool) -> bool:
            raw = os.getenv(key)
            if raw is None:
                return default
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_get_int("APP_PORT", 8000),
            app_token=os.getenv("APP_TOKEN", ""),
            cors_allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*"),
            metrics_suggested_interval=_get_int("METRICS_SUGGESTED_INTERVAL", 3),
            admin_user=os.getenv("ADMIN_USER", "admin"),
            admin_pass=os.getenv("ADMIN_PASS", ""),
            readonly_user=os.getenv("READONLY_USER", ""),
            readonly_pass=os.getenv("READONLY_PASS", ""),
            jwt_secret=os.getenv("JWT_SECRET", ""),
            jwt_ttl_seconds=_get_int("JWT_TTL_SECONDS", 43200),
            whitelist_path=os.getenv("WHITELIST_PATH", "config/whitelist.yaml"),
            devices_reg_path=os.getenv("DEVICES_REG_PATH", "data/devices.yaml"),
            ai_api_endpoint=os.getenv("AI_API_ENDPOINT", ""),
            ai_api_key=os.getenv("AI_API_KEY", ""),
            docker_host=os.getenv("DOCKER_HOST", ""),
            portainer_url=os.getenv("PORTAINER_URL", ""),
            portainer_api_key=os.getenv("PORTAINER_API_KEY", ""),
            portainer_verify_ssl=_get_bool("PORTAINER_VERIFY_SSL", False),
        )

    def allowed_origins(self) -> List[str]:
        items = [origin.strip() for origin in self.cors_allow_origins.split(",")]
        return [origin for origin in items if origin] or ["*"]


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings.from_env()
