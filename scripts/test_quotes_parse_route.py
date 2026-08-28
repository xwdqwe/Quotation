from __future__ import annotations

import asyncio
import sys
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
    def __init__(self, merchant_number: str = "") -> None:
        self.merchant_number = merchant_number

    async def form(self, **_: Any) -> dict[str, str]:
        result = {
            "merchant_number": self.merchant_number,
            "operator": "测试客服",
            "source_text": SAMPLE,
            "default_brand": "",
            "default_market": "",
            "default_processing_method": "",
            "default_multiplier": "",
            "default_subtype": "",
        }
        return result


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def close(self):
        return None


def test_quotes_parse_route() -> None:
    original_render = main_module.render
    original_get_connection = main_module.get_connection
    original_quote_context = main_module._quote_context
    main_module.render = lambda request, template, context: context
    main_module.get_connection = FakeConnection
    main_module._quote_context = lambda conn: {
        "brand_options": [],
        "market_options": [],
        "merchant_options": [],
        "brand_mappings": {},
        "catalog_status": {},
        "api_configured": False,
    }
    try:
        context = asyncio.run(main_module.parse_quotes(FakeRequest()))
    finally:
        main_module.render = original_render
        main_module.get_connection = original_get_connection
        main_module._quote_context = original_quote_context

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

    assert context["merchant_number"] == ""
    assert context["operator"] == "测试客服"


if __name__ == "__main__":
    test_quotes_parse_route()
    print("quotes parse route regression passed: 6 rows")
