"""
JWT authentication helpers and FastAPI dependencies for role-based access.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional, TypedDict

try:
    import jwt  # type: ignore[import]
except ImportError:  # pragma: no cover - fallback for environments sin PyJWT
    import base64
    import hashlib
    import hmac
    import json

    class _FallbackJWT:
        class InvalidTokenError(Exception):
            ...

        class ExpiredSignatureError(InvalidTokenError):
            ...

        @staticmethod
        def encode(payload, secret, algorithm="HS256"):
            if algorithm != "HS256":
                raise NotImplementedError("Solo se soporta HS256 en el fallback.")
            header = {"alg": algorithm, "typ": "JWT"}
            segments = []
            for part in (header, payload):
                data = json.dumps(part, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                segments.append(base64.urlsafe_b64encode(data).rstrip(b"="))
            signing_input = b".".join(segments)
            signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
            segments.append(base64.urlsafe_b64encode(signature).rstrip(b"="))
            return ".".join(segment.decode("utf-8") for segment in segments)

        @staticmethod
        def decode(token, secret, algorithms):
            if "HS256" not in algorithms:
                raise _FallbackJWT.InvalidTokenError("Algoritmo no soportado.")
            parts = token.split(".")
            if len(parts) != 3:
                raise _FallbackJWT.InvalidTokenError("Token mal formado.")

            def _b64decode(data: str) -> bytes:
                padding = "=" * (-len(data) % 4)
                return base64.urlsafe_b64decode(data + padding)

            header = json.loads(_b64decode(parts[0]).decode("utf-8"))
            if header.get("alg") != "HS256":
                raise _FallbackJWT.InvalidTokenError("Algoritmo no soportado.")

            signing_input = ".".join(parts[:2]).encode("utf-8")
            expected_signature = hmac.new(
                secret.encode("utf-8"), signing_input, hashlib.sha256
            ).digest()
            signature = _b64decode(parts[2])
            if not hmac.compare_digest(signature, expected_signature):
                raise _FallbackJWT.InvalidTokenError("Firma inválida.")

            payload = json.loads(_b64decode(parts[1]).decode("utf-8"))
            exp = payload.get("exp")
            if exp is not None and int(exp) < int(time.time()):
                raise _FallbackJWT.ExpiredSignatureError("Token expirado.")
            return payload

    jwt = _FallbackJWT()

from fastapi import Depends, Header, HTTPException, status

from .deps import get_settings

Role = Literal["admin", "readonly"]

_ROLE_LEVEL = {"readonly": 0, "admin": 1}


class TokenPayload(TypedDict):
    sub: str
    role: Role
    exp: int
    iat: int


@dataclass(frozen=True)
class AuthContext:
    """Authentication information returned by dependencies."""

    subject: str
    role: Role


def _role_allows(actual: Role, required: Role) -> bool:
    return _ROLE_LEVEL[actual] >= _ROLE_LEVEL[required]


def create_jwt(subject: str, role: Role = "admin") -> str:
    """Issue a JWT with the configured TTL and secret."""
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret:
        raise RuntimeError("JWT_SECRET no configurado.")

    now = int(time.time())
    payload: TokenPayload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    token = jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return token


def _decode_jwt(token: str) -> AuthContext:
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT no configurado en el servidor.",
        )

    try:
        payload: TokenPayload = jwt.decode(
            token, secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        ) from exc

    role = payload.get("role", "readonly")
    if role not in _ROLE_LEVEL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rol no permitido.",
        )

    return AuthContext(subject=payload.get("sub", ""), role=role)  # type: ignore[arg-type]


def _parse_authorization_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return token or None


def _authenticate_token(raw_token: Optional[str]) -> Optional[AuthContext]:
    if not raw_token:
        return None

    settings = get_settings()

    # Static token fallback for transitional usage.
    app_token = settings.app_token.strip()
    if app_token and raw_token == app_token:
        return AuthContext(subject="legacy", role="admin")

    try:
        return _decode_jwt(raw_token)
    except HTTPException:
        raise


def require_role(required: Role) -> Callable[..., AuthContext]:
    """
    FastAPI dependency to enforce role-based access from Authorization header.
    """

    async def dependency(
        authorization: Optional[str] = Header(None),
    ) -> AuthContext:
        token = _parse_authorization_header(authorization)
        context = _authenticate_token(token)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Falta token Bearer.",
            )
        if not _role_allows(context.role, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes.",
            )
        return context

    return dependency


def validate_token(raw_token: Optional[str], required: Role = "readonly") -> bool:
    """
    Validates a token outside of the dependency system (e.g. WebSocket).
    """
    context = _authenticate_token(raw_token)
    if not context:
        return False
    return _role_allows(context.role, required)


def credential_checker(username: str, password: str) -> Optional[AuthContext]:
    """
    Verify username/password from environment credentials.
    Returns an AuthContext with the role if valid.
    """
    settings = get_settings()
    if username == settings.admin_user and password == settings.admin_pass:
        return AuthContext(subject=username, role="admin")
    if (
        settings.readonly_user
        and username == settings.readonly_user
        and password == settings.readonly_pass
    ):
        return AuthContext(subject=username, role="readonly")
    return None
