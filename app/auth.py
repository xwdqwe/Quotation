from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass


AUTH_ENABLED_ENV = "CARDSABI_AUTH_ENABLED"
AUTH_USERNAME_ENV = "CARDSABI_ADMIN_USERNAME"
AUTH_PASSWORD_HASH_ENV = "CARDSABI_ADMIN_PASSWORD_HASH"
SESSION_SECRET_ENV = "CARDSABI_SESSION_SECRET"
COOKIE_SECURE_ENV = "CARDSABI_COOKIE_SECURE"
SESSION_HOURS_ENV = "CARDSABI_SESSION_HOURS"

SESSION_COOKIE_NAME = "cardsabi_session"
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    username: str
    password_hash: str
    session_secret: str
    cookie_secure: bool
    session_hours: int


def get_auth_settings() -> AuthSettings:
    return AuthSettings(
        enabled=_is_truthy(os.getenv(AUTH_ENABLED_ENV, "0")),
        username=os.getenv(AUTH_USERNAME_ENV, "").strip(),
        password_hash=os.getenv(AUTH_PASSWORD_HASH_ENV, "").strip(),
        session_secret=os.getenv(SESSION_SECRET_ENV, "").strip(),
        cookie_secure=_is_truthy(os.getenv(COOKIE_SECURE_ENV, "0")),
        session_hours=_session_hours(os.getenv(SESSION_HOURS_ENV, "12")),
    )


def validate_auth_configuration(settings: AuthSettings | None = None) -> None:
    settings = settings or get_auth_settings()
    if not settings.enabled:
        return
    missing = []
    if not settings.username:
        missing.append(AUTH_USERNAME_ENV)
    if not settings.password_hash:
        missing.append(AUTH_PASSWORD_HASH_ENV)
    if len(settings.session_secret) < 32:
        missing.append(f"{SESSION_SECRET_ENV}（至少32个字符）")
    if missing:
        raise RuntimeError("已启用登录认证，但缺少配置：" + "、".join(missing))


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS, salt: str | None = None) -> str:
    if len(password) < 12:
        raise ValueError("密码至少需要12个字符")
    salt = salt or secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{PASSWORD_SCHEME}${iterations}${salt}${_b64encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, expected = encoded_hash.split("$", 3)
        iterations = int(iterations_text)
    except (TypeError, ValueError):
        return False
    if scheme != PASSWORD_SCHEME or iterations < 100_000 or iterations > 2_000_000:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return hmac.compare_digest(_b64encode(actual), expected)


def create_session_token(username: str, settings: AuthSettings | None = None, *, now: int | None = None) -> str:
    settings = settings or get_auth_settings()
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + settings.session_hours * 3600
    payload = f"{username}\n{expires_at}".encode("utf-8")
    signature = hmac.new(settings.session_secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def session_username(token: str, settings: AuthSettings | None = None, *, now: int | None = None) -> str | None:
    settings = settings or get_auth_settings()
    try:
        payload_text, signature_text = token.split(".", 1)
        payload = _b64decode(payload_text)
        signature = _b64decode(signature_text)
        expected = hmac.new(settings.session_secret.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        username, expires_text = payload.decode("utf-8").split("\n", 1)
        expires_at = int(expires_text)
    except (UnicodeDecodeError, ValueError):
        return None
    current_time = int(time.time() if now is None else now)
    if current_time >= expires_at or not hmac.compare_digest(username, settings.username):
        return None
    return username


def safe_next_path(value: str | None) -> str:
    value = (value or "").strip()
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _session_hours(value: str) -> int:
    try:
        hours = int(value)
    except ValueError:
        return 12
    return min(max(hours, 1), 168)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
