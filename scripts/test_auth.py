from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import AuthSettings, create_session_token, hash_password, safe_next_path, session_username, verify_password  # noqa: E402


def main() -> None:
    password_hash = hash_password("Strong-Test-Password-42", salt="fixed-test-salt")
    assert verify_password("Strong-Test-Password-42", password_hash)
    assert not verify_password("wrong-password", password_hash)

    settings = AuthSettings(
        enabled=True,
        username="cardsabi",
        password_hash=password_hash,
        session_secret="test-session-secret-that-is-longer-than-32-characters",
        cookie_secure=False,
        session_hours=12,
    )
    token = create_session_token("cardsabi", settings, now=1_000)
    assert session_username(token, settings, now=1_001) == "cardsabi"
    assert session_username(token, settings, now=1_000 + 12 * 3600) is None
    assert session_username(token + "tampered", settings, now=1_001) is None
    assert safe_next_path("/quotes?tab=needs") == "/quotes?tab=needs"
    assert safe_next_path("https://example.com") == "/"
    assert safe_next_path("//example.com") == "/"
    print("auth regression passed")


if __name__ == "__main__":
    main()
