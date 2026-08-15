from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import hash_password  # noqa: E402


def generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(char.islower() for char in password) and any(char.isupper() for char in password) and any(
            char.isdigit() for char in password
        ):
            return password


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Cardsabi 管理员账号配置")
    parser.add_argument("--username", default="cardsabi", help="管理员账号，默认 cardsabi")
    args = parser.parse_args()

    username = args.username.strip()
    if not username or any(char.isspace() for char in username):
        raise SystemExit("账号不能为空或包含空格")

    password = generate_password()
    print("请立即保存以下登录信息，程序不会保存明文密码：")
    print(f"账号：{username}")
    print(f"密码：{password}")
    print("\n服务器环境变量：")
    print("CARDSABI_AUTH_ENABLED=1")
    print(f"CARDSABI_ADMIN_USERNAME={username}")
    print(f"CARDSABI_ADMIN_PASSWORD_HASH={hash_password(password)}")
    print(f"CARDSABI_SESSION_SECRET={secrets.token_urlsafe(48)}")
    print("CARDSABI_COOKIE_SECURE=0")
    print("CARDSABI_SESSION_HOURS=12")


if __name__ == "__main__":
    main()
