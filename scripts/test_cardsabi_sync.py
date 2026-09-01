from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from tempfile import TemporaryDirectory
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from app import main as main_module  # noqa: E402
from app.cardsabi_client import CardsabiClientError  # noqa: E402
from app.database import create_tables, get_connection  # noqa: E402
from app.main import QuoteRowPayload, QuoteSyncPayload  # noqa: E402
from app.quote_sync import QuoteSyncValidationError, prepare_sync_payload  # noqa: E402
from app.sync_store import (  # noqa: E402
    cleanup_sync_history,
    init_sync_tables,
    record_sync_history,
)


MERCHANT = {"merchant_number": "M10001", "merchant_name": "测试商家"}
BRAND_MAPPINGS = {
    "Apple": {"category_name": "iTunes", "card_speed": "Fast"},
    "Paysafecard": {"category_name": "Paysafecard", "card_speed": "Slow"},
}
COUNTRY_MAPPINGS = {"US": "US", "Poland": "PL"}


def row(**overrides):
    value = {
        "line_no": 1,
        "source_line": "Apple US 横卡 50=5.50",
        "brand": "Apple",
        "country": "US",
        "frontend_type": "physical",
        "raw_card_subtype": "横卡",
        "normalized_card_subtype": "卡图",
        "processing_method": "fast_card",
        "feedback_note": "",
        "bin": "",
        "multiplier": None,
        "denom_min": 50,
        "denom_max": 50,
        "supplier_rate": "5.50",
        "status": "active",
        "requirements": "",
    }
    value.update(overrides)
    return value


def prepare(rows):
    return prepare_sync_payload(
        merchant=MERCHANT,
        rows=rows,
        brand_mappings=BRAND_MAPPINGS,
        country_mappings=COUNTRY_MAPPINGS,
    )


def test_single_brand_and_card_types() -> None:
    prepared = prepare(
        [
            row(raw_card_subtype="卡图", frontend_type="physical", supplier_rate="5.4"),
            row(raw_card_subtype="代码/卡密", frontend_type="code", normalized_card_subtype="代码", supplier_rate="5.2"),
            row(raw_card_subtype="电子卡", frontend_type="code", normalized_card_subtype="电子卡", supplier_rate="5.1"),
        ]
    )
    quotes = prepared.payload["merchantQuoteList"][0]["quoteList"]
    assert {item["cardType"] for item in quotes} == {"Physical", "Code", "ECode"}
    assert all(item["categoryName"] == "iTunes" for item in quotes)
    assert all(item["cardSpeed"] == "Fast" for item in quotes)
    assert all(item["merchantRemark"] for item in quotes)

    explicit = prepare([row(cardsabi_card_type="ECode", raw_card_subtype="代码/卡密")])
    explicit_quote = explicit.payload["merchantQuoteList"][0]["quoteList"][0]
    assert explicit_quote["cardType"] == "ECode"


def test_multiple_brands_rejected() -> None:
    try:
        prepare([row(), row(brand="Paysafecard")])
    except QuoteSyncValidationError as exc:
        assert any("多个品牌" in message for message in exc.errors)
    else:
        raise AssertionError("混合品牌批次必须被拒绝")


def test_physical_subtypes_use_lower_rate_and_remark() -> None:
    prepared = prepare(
        [
            row(raw_card_subtype="横卡", supplier_rate="5.50"),
            row(raw_card_subtype="白卡", supplier_rate="5.30", source_line="Apple US 白卡 50=5.30"),
        ]
    )
    quotes = prepared.payload["merchantQuoteList"][0]["quoteList"]
    assert len(quotes) == 1
    assert quotes[0]["price"] == "5.30"
    assert "横卡5.50" in quotes[0]["merchantRemark"]
    assert "白卡5.30" in quotes[0]["merchantRemark"]
    assert prepared.merged_count == 1


def test_unlimited_open_and_multiple_ranges() -> None:
    unlimited = prepare([row(denom_min=None, denom_max=None)]).payload["merchantQuoteList"][0]["quoteList"][0]
    assert (unlimited["minimum"], unlimited["maximum"]) == (10, 100000)

    open_range = prepare([row(denom_min=200, denom_max=None)]).payload["merchantQuoteList"][0]["quoteList"][0]
    assert (open_range["minimum"], open_range["maximum"]) == (200, 100000)

    multiple = prepare([row(denom_min=None, denom_max=None, multiplier=50)]).payload["merchantQuoteList"][0]["quoteList"][0]
    assert (multiple["minimum"], multiple["maximum"], multiple["multipleValue"]) == (50, 100000, 50)


def test_invalid_multiple_blocks_whole_batch() -> None:
    try:
        prepare([row(denom_min=10, denom_max=101, multiplier=5)])
    except QuoteSyncValidationError as exc:
        assert any("倍数面额" in message for message in exc.errors)
    else:
        raise AssertionError("不满足整除条件的批次必须被拒绝")


def test_paused_rows_block_whole_batch() -> None:
    try:
        prepare([row(), row(status="paused", supplier_rate="9.9")])
    except QuoteSyncValidationError as exc:
        assert any("系统不会自动关闭报价" in message for message in exc.errors)
    else:
        raise AssertionError("暂停或不可用行必须阻止整批发送")


def test_missing_brand_blocks_whole_batch() -> None:
    try:
        prepare([row(), row(brand="")])
    except QuoteSyncValidationError as exc:
        assert any("缺少品牌" in message for message in exc.errors)
    else:
        raise AssertionError("品牌空白行不得被静默跳过")


def test_price_precision_and_remark_limit() -> None:
    precise = prepare([row(supplier_rate="0.00018")]).payload["merchantQuoteList"][0]["quoteList"][0]
    assert precise["price"] == "0.00018"

    try:
        prepare([row(requirements="长" * 1001)])
    except QuoteSyncValidationError as exc:
        assert any("1000" in message for message in exc.errors)
    else:
        raise AssertionError("超过1000字符的备注必须被拒绝")


def test_history_retention() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    init_sync_tables(conn)
    history_id = record_sync_history(
        conn,
        merchant_number="M10001",
        merchant_name="测试商家",
        category_name="iTunes",
        source_text="Apple US 50=5.4",
        request_payload={"merchantQuoteList": []},
        response_code="00000",
        response_message="成功",
        status="success",
        operator="测试客服",
        parsed_count=2,
        sent_count=2,
    )
    assert history_id == 1
    conn.execute("UPDATE cardsabi_sync_history SET created_at = '2000-01-01 00:00:00'")
    assert cleanup_sync_history(conn) == 1


def test_failed_api_call_is_persisted() -> None:
    class FailingClient:
        def query_merchants(self):
            return [{"merchantNumber": "M10001", "name": "测试商家"}]

        def query_categories(self):
            return ["iTunes"]

        def query_countries(self):
            return ["US"]

        def submit_quotes(self, payload):
            raise CardsabiClientError("测试连接失败")

    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "sync.sqlite3"
        with closing(get_connection(db_path)) as conn, conn:
            create_tables(conn)
            init_sync_tables(conn)
            conn.execute(
                "INSERT INTO cardsabi_merchants VALUES (?, ?, ?)",
                ("M10001", "测试商家", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "INSERT INTO cardsabi_categories VALUES (?, ?)",
                ("iTunes", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "INSERT INTO cardsabi_countries VALUES (?, ?)",
                ("US", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "UPDATE cardsabi_brand_mappings SET category_name = 'iTunes', card_speed = 'Fast' "
                "WHERE parser_brand = 'Apple'"
            )
            conn.execute(
                "UPDATE cardsabi_country_mappings SET cardsabi_country = 'US' WHERE parser_country = 'US'"
            )

        original_get_connection = main_module.get_connection
        original_client = main_module.CardsabiClient
        main_module.get_connection = lambda: get_connection(db_path)
        main_module.CardsabiClient = FailingClient
        try:
            try:
                main_module.send_quotes_json(
                    QuoteSyncPayload(
                        merchant_number="M10001",
                        operator="测试客服",
                        source_text="Apple US 50=5.4",
                        rows=[QuoteRowPayload(**row())],
                    )
                )
            except HTTPException as exc:
                assert exc.status_code == 502
            else:
                raise AssertionError("测试客户端应返回连接失败")
        finally:
            main_module.get_connection = original_get_connection
            main_module.CardsabiClient = original_client

        with closing(get_connection(db_path)) as conn, conn:
            history = conn.execute("SELECT * FROM cardsabi_sync_history").fetchall()
            assert len(history) == 1
            assert history[0]["status"] == "failed"
            assert history[0]["operator"] == "测试客服"


def test_send_refreshes_live_catalogs_before_submit() -> None:
    class FreshCatalogClient:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.submitted_payload = None

        def query_merchants(self):
            self.calls.append("merchants")
            return [{"merchantNumber": "M10001", "name": "实时商家名称"}]

        def query_categories(self):
            self.calls.append("categories")
            return ["iTunes"]

        def query_countries(self):
            self.calls.append("countries")
            return ["US"]

        def submit_quotes(self, payload):
            self.calls.append("submit")
            self.submitted_payload = payload
            return {"code": "00000", "message": "成功"}

    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "sync.sqlite3"
        with closing(get_connection(db_path)) as conn, conn:
            create_tables(conn)
            init_sync_tables(conn)
            conn.execute(
                "INSERT INTO cardsabi_merchants VALUES (?, ?, ?)",
                ("M10001", "过期商家名称", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "INSERT INTO cardsabi_categories VALUES (?, ?)",
                ("已删除品牌", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "INSERT INTO cardsabi_countries VALUES (?, ?)",
                ("已删除国家", "2026-01-01 00:00:00"),
            )
            conn.execute(
                "UPDATE cardsabi_brand_mappings SET category_name = '已删除品牌', card_speed = 'Fast' "
                "WHERE parser_brand = 'Apple'"
            )
            conn.execute(
                "UPDATE cardsabi_country_mappings SET cardsabi_country = '已删除国家' "
                "WHERE parser_country = 'US'"
            )

        client = FreshCatalogClient()
        original_get_connection = main_module.get_connection
        original_client = main_module.CardsabiClient
        main_module.get_connection = lambda: get_connection(db_path)
        main_module.CardsabiClient = lambda: client
        try:
            result = main_module.send_quotes_json(
                QuoteSyncPayload(
                    merchant_number="M10001",
                    operator="测试客服",
                    source_text="Apple US 50=5.4",
                    rows=[QuoteRowPayload(**row())],
                )
            )
        finally:
            main_module.get_connection = original_get_connection
            main_module.CardsabiClient = original_client

        assert result["ok"] is True
        assert client.calls == ["merchants", "categories", "countries", "submit"]
        merchant_payload = client.submitted_payload["merchantQuoteList"][0]
        quote_payload = merchant_payload["quoteList"][0]
        assert merchant_payload["merchantName"] == "实时商家名称"
        assert quote_payload["categoryName"] == "iTunes"
        assert quote_payload["country"] == "US"


def test_send_stops_when_live_catalog_refresh_fails() -> None:
    class UnavailableCatalogClient:
        submitted = False

        def query_merchants(self):
            raise CardsabiClientError("实时商家目录不可用")

        def submit_quotes(self, payload):
            self.submitted = True
            return {"code": "00000", "message": "不应发送"}

    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "sync.sqlite3"
        with closing(get_connection(db_path)) as conn, conn:
            create_tables(conn)
            init_sync_tables(conn)

        client = UnavailableCatalogClient()
        original_get_connection = main_module.get_connection
        original_client = main_module.CardsabiClient
        main_module.get_connection = lambda: get_connection(db_path)
        main_module.CardsabiClient = lambda: client
        try:
            try:
                main_module.send_quotes_json(
                    QuoteSyncPayload(
                        merchant_number="M10001",
                        source_text="Apple US 50=5.4",
                        rows=[QuoteRowPayload(**row())],
                    )
                )
            except HTTPException as exc:
                assert exc.status_code == 502
                assert "实时目录" in str(exc.detail)
            else:
                raise AssertionError("实时目录刷新失败时必须停止发送")
        finally:
            main_module.get_connection = original_get_connection
            main_module.CardsabiClient = original_client

        assert client.submitted is False


def main() -> None:
    test_single_brand_and_card_types()
    test_multiple_brands_rejected()
    test_physical_subtypes_use_lower_rate_and_remark()
    test_unlimited_open_and_multiple_ranges()
    test_invalid_multiple_blocks_whole_batch()
    test_paused_rows_block_whole_batch()
    test_missing_brand_blocks_whole_batch()
    test_price_precision_and_remark_limit()
    test_history_retention()
    test_failed_api_call_is_persisted()
    test_send_refreshes_live_catalogs_before_submit()
    test_send_stops_when_live_catalog_refresh_fails()
    print("Cardsabi 同步回归通过：单品牌、卡类型、范围、合并、精度、备注和7天记录")


if __name__ == "__main__":
    main()
