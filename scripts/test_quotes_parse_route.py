from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import main as main_module  # noqa: E402


SAMPLE = """苹果卡：卡图
香港HK 0.75 （500-1500 包50H）只要稳卡
香港HK 0.75 （1501-3000 包50h）只要稳卡
香港HK 0.75 （3001-5000 包50h）只要稳卡
香港HK 0.715（150-490 包6H）只要稳卡
香港批量卡问~
美区US 5.35（15-100）
加拿大CAD 3.7（15-100）
"""


class FakeRequest:
    def __init__(self, supplier_group: str = "路由回归测试群", expire_hours: str | None = "6") -> None:
        self.supplier_group = supplier_group
        self.expire_hours = expire_hours

    async def form(self, **_: Any) -> dict[str, str]:
        result = {
            "supplier_group": self.supplier_group,
            "source_text": SAMPLE,
            "default_brand": "",
            "default_market": "",
            "default_processing_method": "",
            "default_multiplier": "",
            "default_subtype": "",
        }
        if self.expire_hours is not None:
            result["default_expire_hours"] = self.expire_hours
        return result


def test_quotes_parse_route() -> None:
    original_render = main_module.render
    main_module.render = lambda request, template, context: context
    try:
        context = asyncio.run(main_module.parse_quotes(FakeRequest()))
    finally:
        main_module.render = original_render

    rows = context["parsed_rows"]
    assert len(rows) == 6, len(rows)
    assert not any(row["source_line"] == "苹果卡：卡图" for row in rows)
    assert not any(row["source_line"] == "香港批量卡问~" for row in rows)
    assert all(row["brand"] == "Apple" for row in rows)
    assert all(row["frontend_type"] == "physical" for row in rows)
    assert all(row["subtype"] == "卡图" for row in rows)
    assert all(row["processing_method"] == "fast_card" for row in rows)
    assert all(row["multiplier"] is None for row in rows)

    actual = [
        (
            row["country"],
            row["currency"],
            row["denom_min"],
            row["denom_max"],
            str(row["supplier_rate"]),
            row["requirements"],
        )
        for row in rows
    ]
    expected = [
        ("Hong Kong", "HKD", 500.0, 1500.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 1501.0, 3000.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 3001.0, 5000.0, "0.75", "包50H；只要稳卡"),
        ("Hong Kong", "HKD", 150.0, 490.0, "0.715", "包6H；只要稳卡"),
        ("US", "USD", 15.0, 100.0, "5.35", ""),
        ("Canada", "CAD", 15.0, 100.0, "3.7", ""),
    ]
    assert actual == expected

    original_render = main_module.render
    main_module.render = lambda request, template, context: context
    try:
        empty_group_context = asyncio.run(main_module.parse_quotes(FakeRequest("", None)))
    finally:
        main_module.render = original_render
    assert empty_group_context["supplier_group"] == ""
    assert empty_group_context["default_expire_hours"] == 24
    assert len(empty_group_context["parsed_rows"]) == 6
    for row in empty_group_context["parsed_rows"]:
        received = datetime.fromisoformat(row["received_at"])
        expires = datetime.fromisoformat(row["expires_at"])
        assert (expires - received).total_seconds() == 24 * 60 * 60


if __name__ == "__main__":
    test_quotes_parse_route()
    print("quotes parse route regression passed: 6 rows")
