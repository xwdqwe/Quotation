from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_TEST_BASE_URL = "http://18.232.59.40:8001/cardsabi"


class CardsabiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class CardsabiSettings:
    base_url: str
    username: str
    password: str
    timeout_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)

    @property
    def is_secure(self) -> bool:
        return self.base_url.lower().startswith("https://")


def get_cardsabi_settings() -> CardsabiSettings:
    timeout_raw = os.getenv("CARDSABI_API_TIMEOUT_SECONDS", "30")
    try:
        timeout = max(1.0, float(timeout_raw))
    except ValueError:
        timeout = 30.0
    return CardsabiSettings(
        base_url=os.getenv("CARDSABI_API_BASE_URL", DEFAULT_TEST_BASE_URL).strip().rstrip("/"),
        username=os.getenv("CARDSABI_API_USERNAME", "").strip(),
        password=os.getenv("CARDSABI_API_PASSWORD", ""),
        timeout_seconds=timeout,
    )


class CardsabiClient:
    def __init__(self, settings: CardsabiSettings | None = None) -> None:
        self.settings = settings or get_cardsabi_settings()

    def query_categories(self) -> list[str]:
        response = self._post("/openapi/query-category-name-list", {})
        return [str(item) for item in response.get("content") or []]

    def query_merchants(self) -> list[dict[str, Any]]:
        response = self._post("/openapi/query-merchant-list", {})
        return [dict(item) for item in response.get("content") or []]

    def query_countries(self) -> list[str]:
        response = self._post("/openapi/query-country-name-list", {})
        return [str(item) for item in response.get("content") or []]

    def query_bins(self, category_name: str) -> list[str]:
        response = self._post(
            "/openapi/query-bin-list-by-category-name",
            {"categoryName": category_name},
        )
        values = [str(item).strip() for item in response.get("content") or []]
        return list(dict.fromkeys(item for item in values if item))

    def submit_quotes(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/openapi/merchant-quote", payload, allow_business_error=True)

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        allow_business_error: bool = False,
    ) -> dict[str, Any]:
        if not self.settings.configured:
            raise CardsabiClientError("Cardsabi 接口账号尚未配置。")
        body = {
            "userName": self.settings.username,
            "password": self.settings.password,
            **payload,
        }
        request = Request(
            f"{self.settings.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise CardsabiClientError(f"Cardsabi 接口返回 HTTP {exc.code}：{raw[:500]}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CardsabiClientError(f"无法连接 Cardsabi 接口：{exc}") from exc

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CardsabiClientError("Cardsabi 接口返回了无法识别的内容。") from exc
        if not isinstance(result, dict):
            raise CardsabiClientError("Cardsabi 接口响应格式错误。")
        if result.get("code") != "00000" and not allow_business_error:
            raise CardsabiClientError(
                f"Cardsabi 接口错误 {result.get('code') or '-'}：{result.get('message') or '未知错误'}"
            )
        return result
