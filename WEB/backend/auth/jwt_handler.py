import os
from datetime import datetime, timedelta, timezone

import jwt


def _secret() -> str:
    value = os.getenv("AUTH_JWT_SECRET", "")
    if not value:
        raise RuntimeError("Falta AUTH_JWT_SECRET en variables de entorno")
    return value


def _issuer() -> str:
    return os.getenv("AUTH_JWT_ISSUER", "productividad-web")


def _access_minutes() -> int:
    return int(os.getenv("AUTH_ACCESS_MINUTES", "30"))


def _refresh_days() -> int:
    return int(os.getenv("AUTH_REFRESH_DAYS", "7"))


def create_access_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(minutes=_access_minutes()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def create_refresh_token(user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "iss": _issuer(),
        "iat": now,
        "exp": now + timedelta(days=_refresh_days()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_token(token: str, expected_type: str) -> dict:
    payload = jwt.decode(token, _secret(), algorithms=["HS256"], issuer=_issuer())
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Tipo de token invalido")
    return payload
