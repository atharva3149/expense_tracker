"""Authentication helpers for the API.

JWT is the primary authentication mechanism used by the React client.  The
existing API-key mode remains available for simple scripts and deployments
that already use it.  Passwords are stored as salted scrypt hashes; plaintext
passwords never reach the database or a response.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

_JWT_ALGORITHM = "HS256"
_PASSWORD_SALT_BYTES = 16
_PASSWORD_HASH_BYTES = 32


def hash_password(password: str) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)`` for a password."""

    salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=_PASSWORD_HASH_BYTES,
    )
    return salt.hex(), password_hash.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    """Verify a password using constant-time comparison."""

    try:
        password_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2**14,
            r=8,
            p=1,
            dklen=_PASSWORD_HASH_BYTES,
        )
        expected_hash = bytes.fromhex(expected_hash_hex)
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(password_hash, expected_hash)


class AuthConfig:
    def __init__(
        self,
        api_key: str | None = None,
        jwt_secret: str | None = None,
        jwt_expire_minutes: int = 1440,
    ):
        self._api_key = api_key
        self._jwt_secret = jwt_secret
        self.jwt_expire_minutes = max(jwt_expire_minutes, 1)

    @property
    def api_key_enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def jwt_enabled(self) -> bool:
        return bool(self._jwt_secret)

    def require_jwt_configured(self) -> None:
        if not self.jwt_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWT authentication is not configured",
            )

    def create_access_token(self, user_id: int, username: str) -> str:
        self.require_jwt_configured()
        now = dt.datetime.now(dt.timezone.utc)
        expires = now + dt.timedelta(minutes=self.jwt_expire_minutes)
        payload = {
            "sub": str(user_id),
            "username": username,
            "iat": now,
            "exp": expires,
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=_JWT_ALGORITHM)

    def decode_access_token(self, token: str) -> int:
        self.require_jwt_configured()
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[_JWT_ALGORITHM],
                options={"require": ["sub", "exp"]},
            )
            user_id = int(payload["sub"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id

    def _check_api_key(self, provided: str | None) -> None:
        if not self.api_key_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        if provided is None or not secrets.compare_digest(provided, self._api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    def authenticate(
        self, authorization: str | None, x_api_key: str | None
    ) -> int | None:
        """Authenticate a request and return its user id when JWT is used.

        API-key requests intentionally return ``None`` because that legacy
        authentication mode represents one shared namespace.  An unconfigured
        app also returns ``None`` so local development remains frictionless.
        """

        if authorization is not None:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization header must use Bearer tokens",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return self.decode_access_token(token.strip())

        if x_api_key is not None:
            self._check_api_key(x_api_key)
            return None

        if self.jwt_enabled:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if self.api_key_enabled:
            self._check_api_key(None)
        return None


def auth_dependency(auth: AuthConfig):
    """Create a FastAPI dependency that stores the authenticated user on state."""

    def _dep(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> None:
        request.state.user_id = auth.authenticate(authorization, x_api_key)

    return Depends(_dep)


# Kept as an alias for callers that used the original API-key dependency name.
api_key_dependency = auth_dependency
