from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import (  # noqa: E402
    bulk_update_quote_status,
    create_tables,
    get_or_create_supplier_group,
    list_filtered_supplier_quotes,
    pause_supplier_group_brand_quotes,
    revoke_quote_batch,
    transition_supplier_group,
)
from app.app_categories import (  # noqa: E402
    import_app_categories_csv,
    parse_app_category_names,
    save_app_categories_bulk,
    save_app_category,
)
from app import main as main_module  # noqa: E402
from app.matching import find_matches, log_match, normalize_match_form  # noqa: E402
from app.main import QuoteRowPayload, QuoteSavePayload, _validated_quotes, format_number  # noqa: E402
from app.parsing import parse_quote_text  # noqa: E402
from app.pricing import bulk_confirm_app_prices, confirm_app_price, list_app_prices, recalculate_app_prices  # noqa: E402
from app.quote_service import analyze_quote_rows, analyze_supersede_preview, save_quote_batch  # noqa: E402
from app.standards import (  # noqa: E402
    market_label,
    normalize_card_subtype,
    normalize_card_subtype_for_brand,
    normalized_subtype_options_for_brand,
)


RAZER_UNBOUNDED_SAMPLE = """==== 雷蛇 Razer ====
美 USD =5.63 ↑↑
新 SGD =4.18
澳 AUD =3.90
加 CAD =4.00
墨 MXN=0.323
欧 EUR= 5.10 [RG10+]
英 UK = 5.10 [RG10+]
【问】其他国家/代码批量（5张+）
"""

OPEN_ENDED_RANGE_SAMPLE = """====南非====
200以上图/密=0.265
"""

PRECISION_SAMPLE = """==== 雷蛇 Razer ====
印尼雷蛇=0.00033
印度尼西亚-IDR----【0.00018】
哥伦比亚=0.0011
"""

ROBLOX_MATRIX_SAMPLE = """〖 Roblox〗
USD=3.5欧盟 EUR 3.5 UK=3.8
cad 2.2  aud 1.9 泰国0.1  墨西哥 0.16
马来西亚 0.6 新西兰 1.7 巴西0.5
新加坡2.2 瑞典/挪威 0.25 其他国家问
（RA开头游戏币不要）
"""

AMAZON_DUAL_RATE_SAMPLE = """〖Amazon〗卡图  连卡大卡问
美亚  50-200=5.4卡图   代码5.2
美亚  201-500=5.3卡图  代码5.1
英亚  25-200=5.9卡图  代码4.9
德亚  25-200=5.0卡图  代码4.0
加亚  50-200=3.3卡图  代码2.5
意亚  25-200=4.6卡图  代码4.0
澳亚  25-200=3.2卡图  代码2.6
"""

PAYSAFECARD_DEFAULT_SAME_RATE_SAMPLE = """〖Paysafecard 〗(其他国家问）发前问
欧盟 EUR 50-500==6.43
瑞士 CHF 50-500==6.8
英国 GBP 50-500==7.15
希腊 GR 50-500==5.7
葡萄牙 50-500==5.7
挪威K 150-5000==0.55
瑞典/SEK 150-5000==0.56
罗马尼亚/RON 100-1000==1.1
波兰/PLN 50-500==1.35
丹麦/DKK 100-5000==0.7
匈牙利 HUF 5000-50000=0.015发前问
捷克/CZK 300-3000=0.24
澳大利亚/AUD 25-500=3.2
加拿大/CAD 25-500=3.6
"""

LONG_TAIL_MULTI_RANGE_SAMPLE = """Sephora 50-99=4.3 100-500=4.8
Footlocker 50-99=4.4 100-500=5.3
"""


def make_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    return conn


def quote(rate: float, raw_subtype: str = "横卡", amount: float = 100) -> dict:
    return {
        "source_text": f"Apple US {raw_subtype} {amount:g}={rate:g}",
        "source_line": f"Apple US {raw_subtype} {amount:g}={rate:g}",
        "line_no": 1,
        "parse_note": "",
        "brand": "Apple",
        "country": "US",
        "currency": "USD",
        "frontend_type": "code" if raw_subtype in {"代码", "代码/卡密", "电子图", "电子卡"} else "physical",
        "subtype": raw_subtype,
        "raw_card_subtype": raw_subtype,
        "normalized_card_subtype": normalize_card_subtype(raw_subtype),
        "processing_method": "fast_card",
        "multiplier": 50,
        "denom_min": amount,
        "denom_max": amount,
        "supplier_rate": rate,
        "status": "active",
        "requirements": "",
        "confidence": 0.99,
    }


def money(value: object) -> Decimal:
    return Decimal(str(value))


def match_query(amount: float = 100) -> dict:
    return {
        "brand": "Apple",
        "country": "US",
        "currency": "USD",
        "frontend_type": "physical",
        "normalized_card_subtype": "卡图",
        "amount": amount,
        "multiplier": 50,
        "processing_method": "fast_card",
    }


def app_category(
    conn: sqlite3.Connection,
    *,
    category_name: str = "APPLE|US美国|100|50倍数",
    brand: str = "Apple",
    country: str = "US",
    currency: str = "USD",
    app_card_type: str = "physical",
    normalized_subtype: str = "卡图",
    denom_min: float | None = 100,
    denom_max: float | None = 100,
    range_type: str = "fixed",
    multiplier: float | None = 50,
    current_app_price: object | None = None,
) -> dict:
    return save_app_category(
        conn,
        {
            "category_name": category_name,
            "brand": brand,
            "country": country,
            "currency": currency,
            "app_card_type": app_card_type,
            "normalized_subtype": normalized_subtype,
            "denom_min": denom_min,
            "denom_max": denom_max,
            "range_type": range_type,
            "multiplier": multiplier,
            "current_app_price": current_app_price,
            "status": "active",
        },
    )


def app_categories_from_rows(conn: sqlite3.Connection, rows: list[dict], prefix: str = "APP") -> None:
    seen = set()
    for row in rows:
        key = (
            row["brand"],
            row["country"],
            row["currency"],
            row["frontend_type"],
            row["normalized_card_subtype"],
            row.get("denom_min"),
            row.get("denom_max"),
            row.get("range_type") or ("unlimited" if row.get("denom_min") is None and row.get("denom_max") is None else "bounded"),
            row.get("multiplier"),
        )
        if key in seen:
            continue
        seen.add(key)
        brand, country, currency, frontend_type, subtype, denom_min, denom_max, range_type, multiplier = key
        app_category(
            conn,
            category_name=f"{prefix}|{brand}|{country}|{currency}|{frontend_type}|{subtype}|{denom_min}-{denom_max}|{multiplier}",
            brand=brand,
            country=country,
            currency=currency,
            app_card_type=frontend_type,
            normalized_subtype=subtype,
            denom_min=denom_min,
            denom_max=denom_max,
            range_type=range_type,
            multiplier=multiplier,
        )


def test_subtype_normalization() -> None:
    for raw in ["卡图", "横卡", "白卡", "普通物理卡", "实体图", "图片", "物理卡", "横版卡"]:
        assert normalize_card_subtype(raw) == "卡图", raw
    for raw in ["代码", "卡密", "代码/卡密", "code", "pin", "code only"]:
        assert normalize_card_subtype(raw) == "代码", raw
    for raw in ["电子图", "电子卡", "e-code", "digital", "email delivery", "email card"]:
        assert normalize_card_subtype(raw) == "电子卡", raw
    for raw in ["竖卡", "竖版卡", "vertical"]:
        assert normalize_card_subtype(raw) == "竖卡", raw
    assert normalize_card_subtype("未知") == "待确认"
    assert normalize_card_subtype("横白") == "卡图"
    assert normalize_card_subtype("整卡") == "卡图"
    assert normalize_card_subtype_for_brand("Apple", "竖卡", "physical") == "竖卡"
    assert normalize_card_subtype_for_brand("Xbox", "竖卡", "physical") == "卡图"
    assert normalize_card_subtype_for_brand("Xbox", "待确认", "physical") == "卡图"
    assert normalize_card_subtype_for_brand("Xbox", "电子卡", "code") == "电子卡"
    assert normalized_subtype_options_for_brand("Apple") == ["卡图", "竖卡", "代码", "电子卡"]
    assert normalized_subtype_options_for_brand("Xbox") == ["卡图", "代码", "电子卡"]


def test_match_page_simple_filter_rank() -> None:
    template = (ROOT / "app" / "templates" / "match.html").read_text(encoding="utf-8")
    for removed_name in ["frontend_type", "raw_card_subtype", "multiplier", "processing_method"]:
        assert f'name="{removed_name}"' not in template
    assert "当前激进价" not in template
    assert "当前建议价" not in template
    assert "当前安全价" not in template
    assert 'name="brand" required' in template
    assert 'name="market" required' in template
    assert 'name="denomination"' in template and "required" in template
    assert 'name="normalized_subtype"' in template

    conn = make_connection()
    try:
        def ranked_quote(
            rate: float,
            raw_subtype: str,
            denom_min: float,
            denom_max: float,
            multiplier: float | None,
            status: str = "active",
        ) -> dict:
            item = quote(rate, raw_subtype=raw_subtype, amount=denom_min)
            item["denom_min"] = denom_min
            item["denom_max"] = denom_max
            item["multiplier"] = multiplier
            item["status"] = status
            return item

        fixtures = [
            ("1001", ranked_quote(5.45, "卡图", 25, 190, 5)),
            ("1012", ranked_quote(5.40, "卡图", 10, 190, 5)),
            ("1005", ranked_quote(5.40, "卡图", 10, 195, None)),
            ("1004", ranked_quote(5.40, "横白", 50, 50, 50)),
            ("1008", ranked_quote(5.30, "代码/卡密", 10, 190, 5)),
            ("暂停群", ranked_quote(5.60, "卡图", 10, 190, 5, status="paused")),
            ("过期群", ranked_quote(5.70, "卡图", 10, 190, 5)),
        ]
        for group, item in fixtures:
            save_quote_batch(conn, group, [item])
        conn.execute(
            "UPDATE supplier_quotes SET expires_at = '2000-01-01 00:00:00' WHERE supplier_group = '过期群'"
        )
        conn.execute(
            "UPDATE supplier_quotes SET updated_at = '2026-06-24 12:00:02' WHERE supplier_group = '1012'"
        )
        conn.execute(
            "UPDATE supplier_quotes SET updated_at = '2026-06-24 12:00:01' WHERE supplier_group = '1005'"
        )
        conn.execute(
            "UPDATE supplier_quotes SET updated_at = '2026-06-24 12:00:00' WHERE supplier_group = '1004'"
        )

        card_query = normalize_match_form(
            {
                "brand": "Apple",
                "market": "US|USD",
                "denomination": "50",
                "normalized_subtype": "卡图",
                "order_no": "ORDER-1",
                "frontend_type": "code",
                "multiplier": "999",
                "processing_method": "slow_process",
            }
        )
        assert set(card_query) == {
            "order_no", "brand", "country", "currency", "market",
            "normalized_card_subtype", "subtype", "denomination", "amount",
        }
        card_matches = find_matches(conn, card_query)
        card_groups = [row["supplier_group"] for row in card_matches["matches"]]
        assert card_groups == ["1001", "1012", "1005", "1004"], card_groups
        assert [money(row["supplier_rate"]) for row in card_matches["matches"]] == [
            money(5.45), money(5.40), money(5.40), money(5.40)
        ]
        assert all(row["normalized_card_subtype"] == "卡图" for row in card_matches["matches"])
        assert not {"aggressive", "recommended", "safe"} & set(card_matches)
        assert all(row["supplier_group"] not in {"暂停群", "过期群", "1008"} for row in card_matches["matches"])

        all_subtypes = find_matches(
            conn,
            normalize_match_form(
                {"brand": "Apple", "market": "US|USD", "denomination": "50", "normalized_subtype": ""}
            ),
        )
        assert [row["supplier_group"] for row in all_subtypes["matches"]] == [
            "1001", "1012", "1005", "1004", "1008"
        ]
        assert {row["normalized_card_subtype"] for row in all_subtypes["matches"]} == {"卡图", "代码"}

        amount_35 = find_matches(
            conn,
            normalize_match_form(
                {"brand": "Apple", "market": "US|USD", "denomination": "35", "normalized_subtype": "卡图"}
            ),
        )
        assert amount_35["matches"]
        assert all(row["multiplier"] in (None, 5) for row in amount_35["matches"])
        assert all(row["supplier_group"] != "1004" for row in amount_35["matches"])

        missing_queries = [
            {"country": "US", "currency": "USD", "denomination": 50},
            {"brand": "Apple", "denomination": 50},
            {"brand": "Apple", "country": "US", "currency": "USD"},
        ]
        for missing in missing_queries:
            result = find_matches(conn, missing)
            assert result["matches"] == []
            assert result["errors"]
    finally:
        conn.close()


def test_brand_aware_subtype_migration() -> None:
    conn = make_connection()
    try:
        xbox_quote = quote(5.0, raw_subtype="竖卡")
        xbox_quote["brand"] = "Xbox"
        xbox_batch = save_quote_batch(conn, "旧数据Xbox群", [xbox_quote])
        xbox_id = xbox_batch["inserted_ids"][0]
        conn.execute(
            "UPDATE supplier_quotes SET raw_card_subtype = '竖卡', subtype = '竖卡', normalized_card_subtype = '竖卡' WHERE id = ?",
            (xbox_id,),
        )

        apple_quote = quote(5.1, raw_subtype="竖卡")
        apple_batch = save_quote_batch(conn, "旧数据Apple群", [apple_quote])
        apple_id = apple_batch["inserted_ids"][0]
        conn.execute(
            "UPDATE supplier_quotes SET normalized_card_subtype = '竖卡' WHERE id = ?",
            (apple_id,),
        )

        pending_quote = quote(4.9, raw_subtype="普通物理卡")
        pending_quote["brand"] = "Xbox"
        pending_batch = save_quote_batch(conn, "旧数据待确认群", [pending_quote])
        pending_id = pending_batch["inserted_ids"][0]
        conn.execute(
            "UPDATE supplier_quotes SET normalized_card_subtype = '待确认' WHERE id = ?",
            (pending_id,),
        )

        create_tables(conn)
        migrated = {
            row["id"]: row["normalized_card_subtype"]
            for row in conn.execute(
                "SELECT id, normalized_card_subtype FROM supplier_quotes WHERE id IN (?, ?, ?)",
                (xbox_id, apple_id, pending_id),
            ).fetchall()
        }
        assert migrated[xbox_id] == "卡图"
        assert migrated[apple_id] == "竖卡"
        assert migrated[pending_id] == "卡图"
    finally:
        conn.close()


def test_rank_group_status_batch_and_logs() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "A群", [quote(5.10)], operator="客服甲")
        b = save_quote_batch(conn, "B群", [quote(4.80)], operator="客服甲")
        c = save_quote_batch(conn, "C群", [quote(4.70)], operator="客服甲")
        assert a["quote_batch_id"].startswith("QB")

        matches = find_matches(conn, match_query())
        assert [item["supplier_group"] for item in matches["matches"]] == ["A群", "B群", "C群"]
        assert [money(item["supplier_rate"]) for item in matches["matches"]] == [money(5.10), money(4.80), money(4.70)]
        assert not {"aggressive", "recommended", "safe"} & set(matches)

        group_a = get_or_create_supplier_group(conn, "A群")
        transition_supplier_group(conn, group_a["id"], "paused", "pause_group", "客服甲", "群休息")
        paused_matches = find_matches(conn, match_query())
        assert [item["supplier_group"] for item in paused_matches["matches"]] == ["B群", "C群"]
        assert money(paused_matches["matches"][0]["supplier_rate"]) == money(4.80)

        transition_supplier_group(
            conn,
            group_a["id"],
            "needs_refresh",
            "mark_group_needs_refresh",
            "客服甲",
            "群已恢复",
        )
        needs_refresh_matches = find_matches(conn, match_query())
        assert all(item["supplier_group"] != "A群" for item in needs_refresh_matches["matches"])
        try:
            transition_supplier_group(
                conn,
                group_a["id"],
                "normal",
                "restore_group_normal",
                "客服甲",
                "未刷新就恢复",
            )
        except ValueError as exc:
            assert "暂无最新确认报价" in str(exc)
        else:
            raise AssertionError("needs_refresh 群没有新报价时不应恢复 normal")

        save_quote_batch(conn, "A群", [quote(5.00)], operator="客服甲")
        assert conn.execute(
            "SELECT status FROM supplier_groups WHERE id = ?",
            (group_a["id"],),
        ).fetchone()["status"] == "normal"
        restored = find_matches(conn, match_query())
        assert restored["matches"][0]["supplier_group"] == "A群"
        assert money(restored["matches"][0]["supplier_rate"]) == money(5.00)

        selected_b = conn.execute(
            "SELECT id FROM supplier_quotes WHERE quote_batch_id = ? ORDER BY id DESC LIMIT 1",
            (b["quote_batch_id"],),
        ).fetchone()["id"]
        log_match(conn, match_query(), selected_b)
        revoked = revoke_quote_batch(conn, b["quote_batch_id"], "客服甲", "测试撤回")
        assert revoked["affected_quote_count"] == 1
        assert revoked["referenced_count"] == 1
        after_revoke = find_matches(conn, match_query())
        assert all(item["supplier_group"] != "B群" for item in after_revoke["matches"])
        assert conn.execute(
            "SELECT status FROM supplier_quotes WHERE quote_batch_id = ?",
            (b["quote_batch_id"],),
        ).fetchone()["status"] == "revoked"

        actions = {row["action"] for row in conn.execute("SELECT action FROM operation_logs").fetchall()}
        assert {"pause_group", "mark_group_needs_refresh", "restore_group_normal_after_new_quotes", "revoke_batch"} <= actions

        app_category(conn, category_name="APPLE|US美国|100|50倍数")
        recalculate_app_prices(conn)
        suggested = conn.execute(
            """
            SELECT suggested_backend_rate FROM app_price_records
            WHERE brand = 'Apple' AND normalized_card_subtype = '卡图'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()["suggested_backend_rate"]
        assert suggested == 5.00
    finally:
        conn.close()


def test_pause_group_recalculate_suggestions() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [quote(5.45, raw_subtype="卡图", amount=50)], operator="客服甲")
        save_quote_batch(conn, "1002", [quote(5.40, raw_subtype="卡图", amount=50)], operator="客服甲")
        save_confirmed_price(conn, "5.45", denom_min=50, denom_max=50, range_type="fixed", multiplier=50)
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1001")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        recalculate_app_prices(conn)

        group_row = conn.execute(
            "SELECT status, paused_at, paused_by_operator, pause_reason FROM supplier_groups WHERE name = '1001'"
        ).fetchone()
        assert group_row["status"] == "paused"
        assert group_row["paused_at"]
        assert group_row["paused_by_operator"] == "客服甲"
        assert group_row["pause_reason"] == "群休息"
        matches = find_matches(conn, match_query(amount=50))
        assert matches["matches"][0]["supplier_group"] == "1002"
        assert money(matches["matches"][0]["supplier_rate"]) == money(5.40)
        assert all(item["supplier_group"] != "1001" for item in matches["matches"])

        impact = result["impact_list"][0]
        assert impact["action"] == "lower_price"
        assert money(impact["current_backend_rate"]) == money(5.45)
        assert money(impact["before_top_rate"]) == money(5.45)
        assert impact["before_top_group"] == "1001"
        assert money(impact["after_top_rate"]) == money(5.40)
        assert impact["after_top_group"] == "1002"
        assert money(impact["suggested_backend_rate"]) == money(5.40)

        app_record = conn.execute(
            """
            SELECT recorded_backend_rate, suggested_backend_rate, status
            FROM app_price_records
            WHERE brand = 'Apple' AND country = 'US' AND currency = 'USD'
              AND normalized_card_subtype = '卡图'
              AND denom_min = 50 AND denom_max = 50
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert money(app_record["recorded_backend_rate"]) == money(5.45)
        assert money(app_record["suggested_backend_rate"]) == money(5.40)
        assert app_record["status"] == "update_needed"
    finally:
        conn.close()


def test_pause_group_no_available_quote() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [quote(5.45, raw_subtype="卡图", amount=50)], operator="客服甲")
        save_confirmed_price(conn, "5.45", denom_min=50, denom_max=50, range_type="fixed", multiplier=50)
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1001")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        recalculate_app_prices(conn)

        assert find_matches(conn, match_query(amount=50))["matches"] == []
        impact = result["impact_list"][0]
        assert impact["action"] == "no_available_quote"
        assert "没有找到其他正常" in impact["reason"]
        app_record = conn.execute(
            """
            SELECT suggested_backend_rate, status
            FROM app_price_records
            WHERE brand = 'Apple' AND country = 'US' AND currency = 'USD'
              AND normalized_card_subtype = '卡图'
              AND denom_min = 50 AND denom_max = 50
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert money(app_record["suggested_backend_rate"]) == money(0)
        assert app_record["status"] == "no_available_quote"
    finally:
        conn.close()


def test_pause_impact_uses_shipment_matching_logic() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 1.07, brand="Razer", country="Brazil", currency="BRL", denom_min=None, denom_max=None, multiplier=None)],
        )
        save_quote_batch(
            conn,
            "1001",
            [supplier_dimension_quote("1001", 1.07, brand="Razer", country="Brazil", currency="BRL", denom_min=50, denom_max=500, multiplier=None)],
        )
        save_confirmed_price(
            conn,
            "1.07",
            brand="Razer",
            country="Brazil",
            currency="BRL",
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
            multiplier=None,
        )
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "manual_review"
        assert impact["after_top_rate"] is None
        assert "暂无可用报价" not in impact["reason"]
        assert "1001" in impact["partial_candidates_text"]
        assert "50-500" in impact["partial_candidates_text"]
    finally:
        conn.close()


def test_pause_impact_full_cover_suggests_price() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 3.12, country="Canada", currency="CAD", denom_min=50, denom_max=250, multiplier=50)],
        )
        save_quote_batch(
            conn,
            "1008",
            [supplier_dimension_quote("1008", 3.10, country="Canada", currency="CAD", denom_min=50, denom_max=500, multiplier=50)],
        )
        save_confirmed_price(conn, "3.12", country="Canada", currency="CAD", denom_min=50, denom_max=250, multiplier=50)
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "lower_price"
        assert impact["after_top_group"] == "1008"
        assert money(impact["after_top_rate"]) == money("3.10")
        assert money(impact["suggested_backend_rate"]) == money("3.10")
    finally:
        conn.close()


def test_pause_impact_no_candidate_really_no_quote() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 1.07, brand="Razer", country="Brazil", currency="BRL", denom_min=None, denom_max=None, multiplier=None)],
        )
        save_confirmed_price(
            conn,
            "1.07",
            brand="Razer",
            country="Brazil",
            currency="BRL",
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
            multiplier=None,
        )
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "no_available_quote"
        assert "没有找到其他正常" in impact["reason"]
        assert not impact["partial_candidates_text"]
    finally:
        conn.close()


def test_partial_range_does_not_become_no_quote() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 1.07, brand="Razer", country="Brazil", currency="BRL", denom_min=1, denom_max=500, multiplier=None)],
        )
        save_quote_batch(
            conn,
            "1001",
            [supplier_dimension_quote("1001", 1.05, brand="Razer", country="Brazil", currency="BRL", denom_min=10, denom_max=500, multiplier=None)],
        )
        save_confirmed_price(
            conn,
            "1.07",
            brand="Razer",
            country="Brazil",
            currency="BRL",
            denom_min=1,
            denom_max=500,
            range_type="bounded",
            multiplier=None,
        )
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "manual_review"
        assert "部分覆盖候选" in impact["reason_detail"]
        assert "1001" in impact["partial_candidates_text"]
    finally:
        conn.close()


def test_partial_multiplier_does_not_become_no_quote() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 1.07, brand="Razer", country="Brazil", currency="BRL", denom_min=1, denom_max=500, multiplier=None)],
        )
        save_quote_batch(
            conn,
            "1001",
            [supplier_dimension_quote("1001", 1.05, brand="Razer", country="Brazil", currency="BRL", denom_min=1, denom_max=500, multiplier=5)],
        )
        save_confirmed_price(
            conn,
            "1.07",
            brand="Razer",
            country="Brazil",
            currency="BRL",
            denom_min=1,
            denom_max=500,
            range_type="bounded",
            multiplier=None,
        )
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "manual_review"
        assert "倍数需人工确认" in impact["partial_candidates_text"]
    finally:
        conn.close()


def test_same_price_after_pause_no_change() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1013",
            [supplier_dimension_quote("1013", 0.323, brand="Razer", country="Brazil", currency="BRL", denom_min=None, denom_max=None, multiplier=None)],
        )
        save_quote_batch(
            conn,
            "1001",
            [supplier_dimension_quote("1001", 0.323, brand="Razer", country="Brazil", currency="BRL", denom_min=None, denom_max=None, multiplier=None)],
        )
        save_confirmed_price(
            conn,
            "0.323",
            brand="Razer",
            country="Brazil",
            currency="BRL",
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
            multiplier=None,
        )
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "no_change"
        assert money(impact["after_top_rate"]) == money("0.323")
    finally:
        conn.close()


def test_paused_superseded_expired_quotes_excluded_from_pause_impact() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1013", [supplier_dimension_quote("1013", 5.50, denom_min=50, denom_max=250, multiplier=50)])
        save_quote_batch(conn, "normal", [supplier_dimension_quote("normal", 5.40, denom_min=50, denom_max=250, multiplier=50)])
        paused = save_quote_batch(conn, "paused", [supplier_dimension_quote("paused", 5.90, denom_min=50, denom_max=250, multiplier=50)])
        superseded = save_quote_batch(conn, "superseded", [supplier_dimension_quote("superseded", 5.80, denom_min=50, denom_max=250, multiplier=50)])
        expired = save_quote_batch(conn, "expired", [supplier_dimension_quote("expired", 5.70, denom_min=50, denom_max=250, multiplier=50)])
        conn.execute("UPDATE supplier_quotes SET status = 'paused' WHERE id = ?", (paused["inserted_ids"][0],))
        conn.execute("UPDATE supplier_quotes SET status = 'superseded' WHERE id = ?", (superseded["inserted_ids"][0],))
        conn.execute("UPDATE supplier_quotes SET expires_at = '2000-01-01 00:00:00' WHERE id = ?", (expired["inserted_ids"][0],))
        save_confirmed_price(conn, "5.50", denom_min=50, denom_max=250, multiplier=50)
        recalculate_app_prices(conn)

        group = get_or_create_supplier_group(conn, "1013")
        result = transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        impact = result["impact_list"][0]
        assert impact["action"] == "lower_price"
        assert impact["after_top_group"] == "normal"
        assert money(impact["after_top_rate"]) == money("5.40")
        assert "paused" not in (impact["partial_candidates_text"] or "")
        assert "superseded" not in (impact["partial_candidates_text"] or "")
        assert "expired" not in (impact["partial_candidates_text"] or "")
    finally:
        conn.close()


def test_restore_group_needs_refresh() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [quote(5.45, raw_subtype="卡图", amount=50)], operator="客服甲")
        group = get_or_create_supplier_group(conn, "1001")
        transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        result = transition_supplier_group(
            conn,
            group["id"],
            "needs_refresh",
            "mark_group_needs_refresh",
            "客服甲",
            "群已恢复",
        )

        assert result["status"] == "needs_refresh"
        assert conn.execute("SELECT status FROM supplier_groups WHERE name = '1001'").fetchone()["status"] == "needs_refresh"
        assert find_matches(conn, match_query(amount=50))["matches"] == []
        template = (ROOT / "app" / "templates" / "library.html").read_text(encoding="utf-8")
        assert "该群已解除暂停，但旧报价暂不参与匹配。请录入该群最新报价并确认后启用。" in template
        assert "解除暂停，等待新报价" in template
    finally:
        conn.close()


def test_confirm_reuse_old_quotes() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [quote(5.45, raw_subtype="卡图", amount=50)], operator="客服甲")
        group = get_or_create_supplier_group(conn, "1001")
        transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        transition_supplier_group(conn, group["id"], "needs_refresh", "mark_group_needs_refresh", "客服甲", "群已恢复")
        result = transition_supplier_group(
            conn,
            group["id"],
            "normal",
            "confirm_reuse_old_quotes",
            "客服乙",
            "人工确认沿用旧报价",
        )
        recalculate_app_prices(conn)

        assert result["status"] == "normal"
        matches = find_matches(conn, match_query(amount=50))
        assert matches["matches"][0]["supplier_group"] == "1001"
        assert result["impact_list"]
        log = conn.execute("SELECT * FROM operation_logs ORDER BY id DESC LIMIT 1").fetchone()
        assert log["action"] == "confirm_reuse_old_quotes"
        assert log["operator"] == "客服乙"
        assert log["old_status"] == "needs_refresh"
        assert log["new_status"] == "normal"
        assert json.loads(log["details"])["impact_list"]
        group_row = conn.execute("SELECT confirmed_by_operator FROM supplier_groups WHERE name = '1001'").fetchone()
        assert group_row["confirmed_by_operator"] == "客服乙"
    finally:
        conn.close()


def test_save_new_quote_reactivates_needs_refresh_group() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [quote(5.45, raw_subtype="卡图", amount=50)], operator="客服甲")
        group = get_or_create_supplier_group(conn, "1001")
        transition_supplier_group(conn, group["id"], "paused", "pause_group", "客服甲", "群休息")
        transition_supplier_group(conn, group["id"], "needs_refresh", "mark_group_needs_refresh", "客服甲", "群已恢复")
        app_category(
            conn,
            category_name="APPLE|US美国|50|50倍数",
            denom_min=50,
            denom_max=50,
            range_type="fixed",
            current_app_price=5.45,
        )

        result = save_quote_batch(conn, "1001", [quote(5.60, raw_subtype="卡图", amount=50)], operator="客服乙")
        recalculate_app_prices(conn)

        assert result["group_reactivated"] is True
        assert conn.execute("SELECT status FROM supplier_groups WHERE name = '1001'").fetchone()["status"] == "normal"
        matches = find_matches(conn, match_query(amount=50))
        assert matches["matches"][0]["supplier_group"] == "1001"
        assert money(matches["matches"][0]["supplier_rate"]) == money(5.60)
        app_record = conn.execute(
            """
            SELECT suggested_backend_rate
            FROM app_price_records
            WHERE brand = 'Apple' AND country = 'US' AND currency = 'USD'
              AND normalized_card_subtype = '卡图'
              AND denom_min = 50 AND denom_max = 50
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert money(app_record["suggested_backend_rate"]) == money(5.60)
        actions = [row["action"] for row in conn.execute("SELECT action FROM operation_logs ORDER BY id").fetchall()]
        assert "restore_group_normal_after_new_quotes" in actions
    finally:
        conn.close()


def test_safe_confirmation_and_market_decline() -> None:
    conn = make_connection()
    try:
        safe = quote(5.10, amount=200)
        unsafe = quote(5.00, amount=201)
        unsafe["normalized_card_subtype"] = "待确认"
        unsafe["confidence"] = 0.5
        preview = analyze_quote_rows(conn, "确认测试群", [safe, unsafe])
        assert preview["confirmable_count"] == 1
        assert preview["manual_count"] == 1
        result = save_quote_batch(conn, "确认测试群", [safe, unsafe], safe_only=True)
        assert result["saved_count"] == 1
        assert result["manual_count"] == 1

        for name, old_rate, new_rate in [("降价A群", 5.30, 5.10), ("降价B群", 5.00, 4.80), ("降价C群", 4.90, 4.70)]:
            save_quote_batch(conn, name, [quote(old_rate, amount=300)])
            save_quote_batch(conn, name, [quote(new_rate, amount=300)])
        risk_matches = find_matches(conn, match_query(amount=300))
        assert [money(row["supplier_rate"]) for row in risk_matches["matches"]] == [
            money(5.10), money(4.80), money(4.70)
        ]
        assert not {"market_risk", "aggressive", "recommended", "safe"} & set(risk_matches)
    finally:
        conn.close()


def test_razer_unbounded_save_pricing_matching_and_market_labels() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("Razer测试群", RAZER_UNBOUNDED_SAMPLE)
        payload_rows = [QuoteRowPayload(**row) for row in rows]
        validation_errors, validated_rows = _validated_quotes(conn, "Razer测试群", payload_rows)
        assert validation_errors == []
        assert len(validated_rows) == 14

        partial_row = dict(rows[0])
        partial_row["denom_min"] = 10
        partial_row["denom_max"] = None
        partial_errors, _ = _validated_quotes(conn, "Razer测试群", [QuoteRowPayload(**partial_row)])
        assert any("面额范围不完整" in error for error in partial_errors)
        partial_preview = analyze_quote_rows(conn, "Razer测试群", [partial_row])
        assert partial_preview["manual_count"] == 1

        preview = analyze_quote_rows(conn, "Razer测试群", rows)
        assert preview["confirmable_count"] == 14
        assert preview["manual_count"] == 0

        saved = save_quote_batch(conn, "Razer测试群", rows, operator="回归测试")
        assert saved["saved_count"] == 14
        stored = conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE denom_min IS NULL AND denom_max IS NULL"
        ).fetchone()[0]
        assert stored == 14

        app_category(
            conn,
            category_name="RAZER|US美国|范围不限|卡图",
            brand="Razer",
            country="US",
            currency="USD",
            app_card_type="physical",
            normalized_subtype="卡图",
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
            multiplier=None,
        )
        app_category(
            conn,
            category_name="RAZER|US美国|范围不限|代码",
            brand="Razer",
            country="US",
            currency="USD",
            app_card_type="code",
            normalized_subtype="代码",
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
            multiplier=None,
        )
        recalculate_app_prices(conn)
        app_rows = conn.execute(
            """
            SELECT frontend_type, normalized_card_subtype, suggested_backend_rate
            FROM app_price_records
            WHERE brand = 'Razer' AND country = 'US' AND currency = 'USD'
            ORDER BY frontend_type
            """
        ).fetchall()
        assert len(app_rows) == 2
        assert {(row["frontend_type"], row["normalized_card_subtype"]) for row in app_rows} == {
            ("physical", "卡图"),
            ("code", "代码"),
        }
        assert all(row["suggested_backend_rate"] == 5.63 for row in app_rows)

        for amount in (10, 50, 100, 500):
            physical = find_matches(
                conn,
                {
                    "brand": "Razer",
                    "country": "US",
                    "currency": "USD",
                    "frontend_type": "physical",
                    "normalized_card_subtype": "卡图",
                    "amount": amount,
                    "multiplier": None,
                    "processing_method": "fast_card",
                },
            )
            code = find_matches(
                conn,
                {
                    "brand": "Razer",
                    "country": "US",
                    "currency": "USD",
                    "frontend_type": "code",
                    "normalized_card_subtype": "代码",
                    "amount": amount,
                    "multiplier": None,
                    "processing_method": "fast_card",
                },
            )
            assert money(physical["matches"][0]["supplier_rate"]) == money(5.63)
            assert money(code["matches"][0]["supplier_rate"]) == money(5.63)

        assert market_label("US", "USD") == "美国 / US / USD"
        assert market_label("Sweden", "SEK") == "瑞典 / Sweden / SEK"
    finally:
        conn.close()


def test_open_range_json_validation_and_save() -> None:
    conn = make_connection()

    @contextmanager
    def fake_get_connection():
        yield conn

    original_get_connection = main_module.get_connection
    main_module.get_connection = fake_get_connection
    try:
        base = {
            "line_no": 1,
            "source_line": "波兰：卡密同价：1.3",
            "source_text": "波兰：卡密同价：1.3",
            "brand": "Apple",
            "country": "Poland",
            "currency": "PLN",
            "frontend_type": "physical",
            "subtype": "卡图",
            "raw_card_subtype": "卡图",
            "normalized_card_subtype": "卡图",
            "processing_method": "fast_card",
            "multiplier": 10,
            "supplier_rate": Decimal("1.3"),
            "status": "active",
            "confidence": 0.99,
        }

        open_row = QuoteRowPayload(
            **base,
            denom_min=100,
            denom_max=None,
            range_type="open",
        )
        errors, validated = _validated_quotes(conn, "开放范围测试群", [open_row])
        assert errors == []
        assert len(validated) == 1
        result = main_module.save_quotes_json(
            QuoteSavePayload(supplier_group="开放范围测试群", rows=[open_row])
        )
        assert result["saved_count"] == 1
        stored = conn.execute(
            "SELECT denom_min, denom_max FROM supplier_quotes WHERE supplier_group = ?",
            ("开放范围测试群",),
        ).fetchone()
        assert (stored["denom_min"], stored["denom_max"]) == (100.0, None)

        poland_rows = parse_quote_text(
            "波兰开放范围群",
            "波兰：卡密同价：1.3\n倍数：10倍数 100+",
            default_brand="Apple",
        )
        assert len(poland_rows) == 2
        assert all(row["range_type"] == "open" for row in poland_rows)
        assert all((row["denom_min"], row["denom_max"], row["multiplier"]) == (100.0, None, 10.0) for row in poland_rows)
        poland_result = main_module.save_quotes_json(
            QuoteSavePayload(
                supplier_group="波兰开放范围群",
                rows=[QuoteRowPayload(**row) for row in poland_rows],
            )
        )
        assert poland_result["saved_count"] == 2
        stored_poland = conn.execute(
            """
            SELECT frontend_type, denom_min, denom_max, multiplier, supplier_rate_text
            FROM supplier_quotes
            WHERE supplier_group = ?
            ORDER BY frontend_type
            """,
            ("波兰开放范围群",),
        ).fetchall()
        assert len(stored_poland) == 2
        assert {row["frontend_type"] for row in stored_poland} == {"physical", "code"}
        assert all((row["denom_min"], row["denom_max"], row["multiplier"]) == (100.0, None, 10.0) for row in stored_poland)
        assert all(row["supplier_rate_text"] == "1.3" for row in stored_poland)

        invalid_bounded = QuoteRowPayload(
            **base,
            denom_min=100,
            denom_max=None,
            range_type="bounded",
        )
        invalid_errors, _ = _validated_quotes(conn, "错误范围测试群", [invalid_bounded])
        assert any("面额范围不完整" in error for error in invalid_errors)

        unlimited = QuoteRowPayload(
            **base,
            denom_min=None,
            denom_max=None,
            range_type="unlimited",
        )
        unlimited_errors, _ = _validated_quotes(conn, "不限范围测试群", [unlimited])
        assert unlimited_errors == []

        fixed = QuoteRowPayload(
            **base,
            denom_min=250,
            denom_max=250,
            range_type="fixed",
        )
        fixed_errors, _ = _validated_quotes(conn, "固定面值测试群", [fixed])
        assert fixed_errors == []
    finally:
        main_module.get_connection = original_get_connection
        conn.close()


def test_open_ended_range_save_pricing_and_matching() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("南非开放区间群", OPEN_ENDED_RANGE_SAMPLE, default_brand="Apple")
        payload_rows = [QuoteRowPayload(**row) for row in rows]
        validation_errors, validated_rows = _validated_quotes(conn, "南非开放区间群", payload_rows)
        assert validation_errors == []
        assert len(validated_rows) == 2
        preview = analyze_quote_rows(conn, "南非开放区间群", rows)
        assert preview["confirmable_count"] == 2

        saved = save_quote_batch(conn, "南非开放区间群", rows, operator="回归测试")
        assert saved["saved_count"] == 2
        for app_card_type, subtype in [("physical", "卡图"), ("code", "代码")]:
            app_category(
                conn,
                category_name=f"APPLE|ZA南非|200以上|{subtype}",
                country="South Africa",
                currency="ZAR",
                app_card_type=app_card_type,
                normalized_subtype=subtype,
                denom_min=200,
                denom_max=None,
                range_type="open",
                multiplier=None,
            )
        recalculate_app_prices(conn)
        app_count = conn.execute(
            """
            SELECT COUNT(*) FROM app_price_records
            WHERE brand = 'Apple' AND country = 'South Africa' AND currency = 'ZAR'
              AND denom_min = 200 AND denom_max IS NULL
            """
        ).fetchone()[0]
        assert app_count == 2

        base_query = {
            "brand": "Apple",
            "country": "South Africa",
            "currency": "ZAR",
            "frontend_type": "physical",
            "normalized_card_subtype": "卡图",
            "multiplier": None,
            "processing_method": "fast_card",
        }
        matches_300 = find_matches(conn, {**base_query, "amount": 300})
        matches_199 = find_matches(conn, {**base_query, "amount": 199})
        assert money(matches_300["matches"][0]["supplier_rate"]) == money(0.265)
        assert matches_199["matches"] == []
    finally:
        conn.close()


def test_manual_pause_supplier_group_brand() -> None:
    conn = make_connection()
    try:
        group_a_rows = []
        for amount, rate, status in [
            (100, 5.20, "active"),
            (200, 4.90, "ask_first"),
            (300, 4.80, "warning"),
        ]:
            item = quote(rate, amount=amount)
            item["brand"] = "Roblox"
            item["status"] = status
            group_a_rows.append(item)
        group_b = quote(5.10, amount=100)
        group_b["brand"] = "Roblox"
        group_c = quote(5.00, raw_subtype="代码/卡密", amount=100)
        group_c["brand"] = "Roblox"
        same_group_other_brand = quote(5.20, amount=100)

        save_quote_batch(conn, "1008", group_a_rows, operator="客服甲")
        save_quote_batch(conn, "1002", [group_b], operator="客服甲")
        save_quote_batch(conn, "1006", [group_c], operator="客服甲")
        save_quote_batch(conn, "1008", [same_group_other_brand], operator="客服甲")
        app_category(
            conn,
            category_name="ROBLOX|US美国|100|50倍数",
            brand="Roblox",
            country="US",
            currency="USD",
            app_card_type="physical",
            normalized_subtype="卡图",
            denom_min=100,
            denom_max=100,
            range_type="fixed",
            multiplier=50,
            current_app_price=5.20,
        )
        save_confirmed_price(
            conn,
            "5.20",
            brand="Roblox",
            country="US",
            currency="USD",
            normalized_subtype="鍗″浘",
            denom_min=100,
            denom_max=100,
            range_type="fixed",
            multiplier=50,
        )
        recalculate_app_prices(conn)

        before_status = conn.execute(
            "SELECT status FROM supplier_quotes WHERE supplier_group = '1008' AND brand = 'Roblox' ORDER BY id LIMIT 1"
        ).fetchone()["status"]
        assert parse_quote_text("1008", "=====Roblox=====\n暂停") == []
        after_status = conn.execute(
            "SELECT status FROM supplier_quotes WHERE supplier_group = '1008' AND brand = 'Roblox' ORDER BY id LIMIT 1"
        ).fetchone()["status"]
        assert before_status == after_status

        pause_result = pause_supplier_group_brand_quotes(
            conn,
            supplier_group="1008",
            brand="Roblox",
            operator="客服甲",
            note="群通知暂停",
        )
        assert pause_result["affected_count"] == 3
        assert [item["supplier_group"] for item in pause_result["before_top3"]] == ["1008", "1002", "1006"]
        assert [money(item["supplier_rate"]) for item in pause_result["before_top3"]] == [money(5.20), money(5.10), money(5.00)]
        assert [item["supplier_group"] for item in pause_result["after_top3"]] == ["1002", "1006"]
        assert pause_result["top_changed"] is True
        assert pause_result["before_top1_supplier_group"] == "1008"
        assert pause_result["after_top1_supplier_group"] == "1002"
        assert money(pause_result["price_change_amount"]) == money(-0.10)
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1008' AND brand = 'Roblox' AND status = 'paused'"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1002' AND brand = 'Roblox' AND status = 'active'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1008' AND brand = 'Apple' AND status = 'active'"
        ).fetchone()[0] == 1

        log = conn.execute("SELECT * FROM quote_status_logs ORDER BY id DESC LIMIT 1").fetchone()
        assert log["supplier_group"] == "1008"
        assert log["brand"] == "Roblox"
        assert log["action"] == "pause_brand"
        assert log["affected_count"] == 3
        assert log["operator"] == "客服甲"
        log_detail = json.loads(log["note"])
        assert log_detail["operator_note"] == "群通知暂停"
        assert log_detail["before_top3"][0]["supplier_group"] == "1008"
        assert log_detail["after_top3"][0]["supplier_group"] == "1002"
        assert money(log_detail["price_change_amount"]) == money(-0.10)

        original_get_connection = main_module.get_connection
        original_render = main_module.render
        main_module.get_connection = lambda: conn
        main_module.render = lambda request, template, context: context
        try:
            page_context = main_module.quote_page(
                request=None,
                pause_done=1,
                pause_log_id=pause_result["log_id"],
            )
        finally:
            main_module.get_connection = original_get_connection
            main_module.render = original_render
        assert page_context["pause_result"]["before_top3"][0]["supplier_group"] == "1008"
        assert page_context["pause_result"]["after_top3"][0]["supplier_group"] == "1002"
        assert page_context["pause_result"]["top_changed"] is True

        recalculate_app_prices(conn)
        query = {
            "brand": "Roblox",
            "country": "US",
            "currency": "USD",
            "frontend_type": "physical",
            "normalized_card_subtype": "卡图",
            "amount": 100,
            "multiplier": 50,
            "processing_method": "fast_card",
        }
        one_active = find_matches(conn, query)
        assert one_active["matches"][0]["supplier_group"] == "1002"
        assert all(item["supplier_group"] != "1008" for item in one_active["matches"])
        app_status = conn.execute(
            """
            SELECT status FROM app_price_records
            WHERE brand = 'Roblox' AND country = 'US' AND denom_min = 100
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()["status"]
        assert app_status != "no_cover_quote"

        pause_supplier_group_brand_quotes(conn, "1002", "Roblox", "客服甲", "第二群暂停")
        final_pause = pause_supplier_group_brand_quotes(conn, "1006", "Roblox", "客服甲", "第三群暂停")
        assert final_pause["after_top3"] == []
        recalculate_app_prices(conn)
        no_active = find_matches(conn, query)
        assert no_active["matches"] == []
        app_status = conn.execute(
            """
            SELECT status FROM app_price_records
            WHERE brand = 'Roblox' AND country = 'US' AND denom_min = 100
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()["status"]
        assert app_status == "no_available_quote"
    finally:
        conn.close()


def test_bulk_pause_selected_quotes() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        b = save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        c = save_quote_batch(conn, "1003", [supplier_dimension_quote("1003", 5.30)])
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="selected",
            quote_ids=[a["inserted_ids"][0], c["inserted_ids"][0]],
            operator="客服A",
            reason="群通知暂停",
        )
        recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"])
        assert result["affected_quote_count"] == 2
        assert conn.execute("SELECT status FROM supplier_quotes WHERE id = ?", (a["inserted_ids"][0],)).fetchone()["status"] == "paused"
        assert conn.execute("SELECT status FROM supplier_quotes WHERE id = ?", (c["inserted_ids"][0],)).fetchone()["status"] == "paused"
        assert conn.execute("SELECT status FROM supplier_quotes WHERE id = ?", (b["inserted_ids"][0],)).fetchone()["status"] == "active"
        record = latest_app_record(conn)
        assert record["highest_supplier_group"] == "1002"
        assert money(record["highest_supplier_rate"]) == money("5.40")
        matches = find_matches(
            conn,
            {
                "brand": "Apple",
                "country": "US",
                "currency": "USD",
                "amount": 50,
            },
        )
        assert [item["supplier_group"] for item in matches["matches"]] == ["1002"]
    finally:
        conn.close()


def test_bulk_pause_filtered_by_group() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1007",
            [
                supplier_dimension_quote("1007", 5.0 + index / 100, denom_min=10 + index, denom_max=10 + index)
                for index in range(10)
            ],
        )
        save_quote_batch(
            conn,
            "1008",
            [
                supplier_dimension_quote("1008", 4.0 + index / 100, denom_min=100 + index, denom_max=100 + index)
                for index in range(5)
            ],
        )
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="filtered",
            filters={"supplier_group": "1007"},
            operator="客服A",
            reason="供应商暂不收",
        )
        assert result["affected_quote_count"] == 10
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1007' AND status = 'paused'").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1008' AND status = 'active'").fetchone()[0] == 5
    finally:
        conn.close()


def test_bulk_pause_filtered_by_group_brand_market() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1007",
            [
                supplier_dimension_quote("1007", 5.0 + index / 100, denom_min=10 + index, denom_max=10 + index)
                for index in range(5)
            ],
        )
        save_quote_batch(
            conn,
            "1007",
            [
                supplier_dimension_quote("1007", 6.0 + index / 100, country="UK", currency="GBP", denom_min=20 + index, denom_max=20 + index)
                for index in range(5)
            ],
        )
        save_quote_batch(
            conn,
            "1007",
            [
                supplier_dimension_quote("1007", 3.0 + index / 100, brand="Roblox", denom_min=30 + index, denom_max=30 + index)
                for index in range(5)
            ],
        )
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="filtered",
            filters={"supplier_group": "1007", "brand": "Apple", "country": "US", "currency": "USD"},
            operator="客服A",
            reason="价格异常",
        )
        assert result["affected_quote_count"] == 5
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1007' AND brand = 'Apple' AND country = 'US' AND status = 'paused'").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1007' AND brand = 'Apple' AND country = 'UK' AND status = 'active'").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = '1007' AND brand = 'Roblox' AND country = 'US' AND status = 'active'").fetchone()[0] == 5
    finally:
        conn.close()


def test_pause_recalculates_suggestions() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        save_quote_batch(conn, "1003", [supplier_dimension_quote("1003", 5.30)])
        recalculate_app_prices(conn)
        assert money(latest_app_record(conn)["highest_supplier_rate"]) == money("5.50")
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="selected",
            quote_ids=a["inserted_ids"],
            operator="客服A",
            reason="群通知暂停",
        )
        recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"])
        record = latest_app_record(conn)
        assert money(record["highest_supplier_rate"]) == money("5.40")
        assert money(record["second_supplier_rate"]) == money("5.30")
        assert record["highest_supplier_group"] == "1002"
    finally:
        conn.close()


def test_resume_recalculates_suggestions() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        bulk_update_quote_status(conn, action="pause", mode="selected", quote_ids=a["inserted_ids"], operator="客服A", reason="群通知暂停")
        recalculate_app_prices(conn, affected_quote_ids=a["inserted_ids"])
        assert money(latest_app_record(conn)["highest_supplier_rate"]) == money("5.40")
        result = bulk_update_quote_status(conn, action="resume", mode="selected", quote_ids=a["inserted_ids"], operator="客服A", reason="恢复正常")
        recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"])
        record = latest_app_record(conn)
        assert money(record["highest_supplier_rate"]) == money("5.50")
        assert record["highest_supplier_group"] == "1001"
        restored = conn.execute("SELECT status, resumed_by_operator FROM supplier_quotes WHERE id = ?", (a["inserted_ids"][0],)).fetchone()
        assert restored["status"] == "active"
        assert restored["resumed_by_operator"] == "客服A"
    finally:
        conn.close()


def test_bulk_pause_no_filters_warning() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        try:
            bulk_update_quote_status(conn, action="pause", mode="filtered", filters={}, operator="客服A", reason="误操作保护")
        except ValueError as exc:
            assert "筛选" in str(exc) or "风险" in str(exc)
        else:
            raise AssertionError("bulk pause without filters should require force confirmation")
    finally:
        conn.close()


def test_paused_quote_excluded_from_match() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        bulk_update_quote_status(conn, action="pause", mode="selected", quote_ids=a["inserted_ids"], operator="客服A", reason="群通知暂停")
        matches = find_matches(
            conn,
            {
                "brand": "Apple",
                "country": "US",
                "currency": "USD",
                "amount": 50,
            },
        )
        assert [item["supplier_group"] for item in matches["matches"]] == ["1002"]
    finally:
        conn.close()


def test_bulk_action_log_created() -> None:
    conn = make_connection()
    try:
        a = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.50)])
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="selected",
            quote_ids=a["inserted_ids"],
            operator="客服A",
            reason="风险过高",
        )
        assert result["affected_quote_count"] == 1
        log = conn.execute("SELECT * FROM quote_bulk_action_logs ORDER BY id DESC LIMIT 1").fetchone()
        assert log["action"] == "pause"
        assert log["mode"] == "selected"
        assert log["affected_quote_count"] == 1
        assert log["operator"] == "客服A"
        assert log["reason"] == "风险过高"
        assert json.loads(log["quote_ids_json"]) == a["inserted_ids"]
    finally:
        conn.close()


def test_status_quotes_precision_and_bulk_app_confirmation() -> None:
    conn = make_connection()
    try:
        paused_rows = parse_quote_text(
            "状态测试群",
            "NZD 10-500 图/密=暂停",
            default_brand="Apple",
        )
        paused_payload = [QuoteRowPayload(**row) for row in paused_rows]
        errors, validated = _validated_quotes(conn, "状态测试群", paused_payload)
        assert errors == []
        assert len(validated) == 2
        empty_group_errors, _ = _validated_quotes(conn, "", paused_payload)
        assert "请先填写来源群/供应商，再确认保存报价。" in empty_group_errors
        save_quote_batch(conn, "状态测试群", validated)
        stored_paused = conn.execute(
            "SELECT status, supplier_rate, supplier_rate_text FROM supplier_quotes WHERE supplier_group = '状态测试群'"
        ).fetchall()
        assert len(stored_paused) == 2
        assert all(row["status"] == "paused" for row in stored_paused)
        assert all(row["supplier_rate"] is None and row["supplier_rate_text"] is None for row in stored_paused)

        scatter_rows = parse_quote_text("散卡测试群", "Apple USD散卡 10-190=5.38（5倍数）")
        scatter_payload = [QuoteRowPayload(**row) for row in scatter_rows]
        scatter_errors, scatter_validated = _validated_quotes(conn, "散卡测试群", scatter_payload)
        assert scatter_errors == []
        save_quote_batch(conn, "散卡测试群", scatter_validated)
        stored_scatter = conn.execute(
            "SELECT raw_card_subtype, normalized_card_subtype FROM supplier_quotes WHERE supplier_group = '散卡测试群'"
        ).fetchone()
        assert stored_scatter["raw_card_subtype"] == "散卡"
        assert stored_scatter["normalized_card_subtype"] == "卡图"

        active_missing = QuoteRowPayload(**{**paused_rows[0], "status": "active"})
        active_errors, _ = _validated_quotes(conn, "状态测试群", [active_missing])
        assert any("缺少供应商报价" in item for item in active_errors)
        ask_missing = QuoteRowPayload(**{**paused_rows[0], "status": "ask_first"})
        ask_errors, _ = _validated_quotes(conn, "状态测试群", [ask_missing])
        assert ask_errors == []

        precision_rows = parse_quote_text("精度测试群", PRECISION_SAMPLE)
        precision_payload = [QuoteRowPayload(**row) for row in precision_rows]
        precision_errors, precision_validated = _validated_quotes(conn, "精度测试群", precision_payload)
        assert precision_errors == []
        save_quote_batch(conn, "精度测试群", precision_validated)
        stored_rates = conn.execute(
            """
            SELECT source_line, supplier_rate, supplier_rate_text
            FROM supplier_quotes
            WHERE supplier_group = '精度测试群'
            ORDER BY id
            """
        ).fetchall()
        expected_by_source = {
            "印尼雷蛇=0.00033": "0.00033",
            "印度尼西亚-IDR----【0.00018】": "0.00018",
            "哥伦比亚=0.0011": "0.0011",
        }
        assert len(stored_rates) == 6
        for row in stored_rates:
            expected = expected_by_source[row["source_line"]]
            assert row["supplier_rate_text"] == expected
            assert format_number(row["supplier_rate_text"]) == expected
            assert format_number(row["supplier_rate"]) == expected

        for index, amount in enumerate([401, 402, 403], start=1):
            app_category(
                conn,
                category_name=f"APPLE|US美国|{amount}|批量{index}",
                denom_min=amount,
                denom_max=amount,
                range_type="fixed",
                multiplier=None,
            )
            item = quote(float(f"5.{index}"), raw_subtype="卡图", amount=amount)
            item["multiplier"] = None
            save_quote_batch(conn, f"批量确认群{index}", [item])
        app_category(
            conn,
            category_name="APPLE|US美国|499|填0",
            denom_min=499,
            denom_max=499,
            range_type="fixed",
            multiplier=None,
            current_app_price=9.9,
        )
        app_category(
            conn,
            category_name="APPLE|US美国|500|无变化",
            denom_min=500,
            denom_max=500,
            range_type="fixed",
            multiplier=None,
            current_app_price=7.0,
        )
        no_change_quote = quote(7.0, raw_subtype="卡图", amount=500)
        no_change_quote["multiplier"] = None
        save_quote_batch(conn, "批量无变化群", [no_change_quote])
        recalculate_app_prices(conn)

        confirmed_count = bulk_confirm_app_prices(conn, "needs", operator="客服甲")
        assert confirmed_count == 4
        confirmed = conn.execute(
            """
            SELECT status, suggested_backend_rate, recorded_backend_rate, last_confirmed_at
            FROM app_price_records
            WHERE app_category_id IS NOT NULL
            ORDER BY id
            """
        ).fetchall()
        assert len(confirmed) == 5
        assert all(row["status"] == "no_change" for row in confirmed)
        assert all(row["recorded_backend_rate"] == row["suggested_backend_rate"] for row in confirmed)
        assert sum(1 for row in confirmed if row["last_confirmed_at"]) == 4
        assert conn.execute("SELECT COUNT(*) FROM app_category_update_logs").fetchone()[0] == 4
    finally:
        conn.close()


def test_apple_raw_subtype_matching_and_conservative_app_price() -> None:
    conn = make_connection()
    try:
        group_a = [quote(5.80, raw_subtype="横卡"), quote(5.50, raw_subtype="白卡")]
        group_b = [quote(5.70, raw_subtype="横卡"), quote(5.40, raw_subtype="白卡")]
        save_quote_batch(conn, "横白A群", group_a)
        save_quote_batch(conn, "横白B群", group_b)
        active_rows = conn.execute(
            """
            SELECT supplier_group, raw_card_subtype, status
            FROM supplier_quotes
            WHERE supplier_group IN ('横白A群', '横白B群') AND status = 'active'
            """
        ).fetchall()
        assert len(active_rows) == 4
        assert {row["raw_card_subtype"] for row in active_rows} == {"横卡", "白卡"}

        app_category(conn, category_name="APPLE|US美国|100|50倍数")
        recalculate_app_prices(conn)
        app_record = conn.execute(
            """
            SELECT suggested_backend_rate
            FROM app_price_records
            WHERE brand = 'Apple' AND country = 'US' AND currency = 'USD'
              AND frontend_type = 'physical' AND normalized_card_subtype = '卡图'
              AND denom_min = 100 AND denom_max = 100 AND multiplier = 50
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        assert money(app_record["suggested_backend_rate"]) == money(5.80)

        unified_matches = find_matches(conn, match_query())
        assert unified_matches["matches"]
        assert all(row["normalized_card_subtype"] == "卡图" for row in unified_matches["matches"])
        assert all(row["raw_card_subtype"] in {"横卡", "白卡"} for row in unified_matches["matches"])
        assert [money(row["supplier_rate"]) for row in unified_matches["matches"]] == sorted(
            [money(row["supplier_rate"]) for row in unified_matches["matches"]],
            reverse=True,
        )
    finally:
        conn.close()


def test_roblox_matrix_save_pricing_and_unbounded_matching() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("Roblox矩阵群", ROBLOX_MATRIX_SAMPLE)
        payload = [QuoteRowPayload(**row) for row in rows]
        errors, validated = _validated_quotes(conn, "Roblox矩阵群", payload)
        assert errors == []
        assert len(validated) == 26
        result = save_quote_batch(conn, "Roblox矩阵群", validated)
        assert result["saved_count"] == 26
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = 'Roblox矩阵群' AND denom_min IS NULL AND denom_max IS NULL"
        ).fetchone()[0] == 26

        app_categories_from_rows(conn, validated, prefix="ROBLOX")
        recalculate_app_prices(conn)
        app_rows = conn.execute(
            "SELECT COUNT(*) FROM app_price_records WHERE brand = 'Roblox' AND suggested_backend_rate IS NOT NULL"
        ).fetchone()[0]
        assert app_rows == 26

        for frontend_type, normalized_subtype in [("physical", "卡图"), ("code", "代码")]:
            matches = find_matches(
                conn,
                {
                    "brand": "Roblox",
                    "country": "US",
                    "currency": "USD",
                    "frontend_type": frontend_type,
                    "normalized_card_subtype": normalized_subtype,
                    "raw_card_subtype": "",
                    "amount": 500,
                    "multiplier": None,
                    "processing_method": "any",
                },
            )
            assert matches["matches"]
            assert money(matches["matches"][0]["supplier_rate"]) == money(3.5)
    finally:
        conn.close()


def test_amazon_distinct_physical_and_code_app_prices() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("Amazon双价格群", AMAZON_DUAL_RATE_SAMPLE)
        payload = [QuoteRowPayload(**row) for row in rows]
        errors, validated = _validated_quotes(conn, "Amazon双价格群", payload)
        assert errors == []
        assert len(validated) == 14
        result = save_quote_batch(conn, "Amazon双价格群", validated)
        assert result["saved_count"] == 14

        app_categories_from_rows(conn, validated, prefix="AMAZON")
        recalculate_app_prices(conn)
        records = conn.execute(
            """
            SELECT frontend_type, normalized_card_subtype, suggested_backend_rate
            FROM app_price_records
            WHERE brand = 'Amazon' AND country = 'US' AND currency = 'USD'
              AND denom_min = 50 AND denom_max = 200
            """
        ).fetchall()
        assert {
            (row["frontend_type"], row["normalized_card_subtype"]): money(row["suggested_backend_rate"])
            for row in records
        } == {
            ("physical", "卡图"): money("5.4"),
            ("code", "代码"): money("5.2"),
        }
    finally:
        conn.close()


def test_paysafecard_default_same_rate_app_prices() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("Paysafecard测试群", PAYSAFECARD_DEFAULT_SAME_RATE_SAMPLE)
        payload = [QuoteRowPayload(**row) for row in rows]
        errors, validated = _validated_quotes(conn, "Paysafecard测试群", payload)
        assert errors == []
        assert len(validated) == 28
        result = save_quote_batch(conn, "Paysafecard测试群", validated)
        assert result["saved_count"] == 28
        assert conn.execute(
            "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = 'Paysafecard测试群' AND normalized_card_subtype = '电子卡'"
        ).fetchone()[0] == 0

        app_categories_from_rows(conn, validated, prefix="PAYSAFECARD")
        recalculate_app_prices(conn)
        records = conn.execute(
            """
            SELECT frontend_type, normalized_card_subtype, suggested_backend_rate
            FROM app_price_records
            WHERE brand = 'Paysafecard' AND country = 'EU' AND currency = 'EUR'
              AND denom_min = 50 AND denom_max = 500
            """
        ).fetchall()
        assert {
            (row["frontend_type"], row["normalized_card_subtype"]): money(row["suggested_backend_rate"])
            for row in records
        } == {
            ("physical", "卡图"): money("6.43"),
            ("code", "代码"): money("6.43"),
        }
    finally:
        conn.close()


def test_long_tail_multi_range_save_and_app_prices() -> None:
    conn = make_connection()
    try:
        rows = parse_quote_text("长尾零售测试群", LONG_TAIL_MULTI_RANGE_SAMPLE)
        payload = [QuoteRowPayload(**row) for row in rows]
        errors, validated = _validated_quotes(conn, "长尾零售测试群", payload)
        assert errors == []
        assert len(validated) == 8
        result = save_quote_batch(conn, "长尾零售测试群", validated)
        assert result["saved_count"] == 8

        app_categories_from_rows(conn, validated, prefix="LONGTAIL")
        recalculate_app_prices(conn)
        records = conn.execute(
            """
            SELECT brand, frontend_type, normalized_card_subtype,
                   denom_min, denom_max, suggested_backend_rate
            FROM app_price_records
            WHERE brand IN ('Sephora', 'Footlocker')
            """
        ).fetchall()
        assert len(records) == 8
        assert all((row["denom_min"], row["denom_max"]) in {(50.0, 99.0), (100.0, 500.0)} for row in records)
        assert {
            (row["frontend_type"], row["normalized_card_subtype"])
            for row in records
        } == {("physical", "卡图"), ("code", "代码")}
    finally:
        conn.close()


def category_quote(
    rate: float,
    *,
    country: str,
    currency: str,
    denom_min: float | None,
    denom_max: float | None,
    multiplier: float | None,
    processing_method: str = "fast_card",
) -> dict:
    item = quote(rate, raw_subtype="卡图", amount=denom_min or 1)
    item["country"] = country
    item["currency"] = currency
    item["denom_min"] = denom_min
    item["denom_max"] = denom_max
    item["multiplier"] = multiplier
    item["processing_method"] = processing_method
    return item


def app_price_by_category(conn: sqlite3.Connection, category_name: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM app_price_records WHERE category_name = ? ORDER BY id DESC LIMIT 1",
        (category_name,),
    ).fetchone()
    assert row is not None, category_name
    return row


def supplier_dimension_quote(
    group: str,
    rate: float,
    *,
    country: str = "US",
    currency: str = "USD",
    denom_min: float | None = 10,
    denom_max: float | None = 190,
    multiplier: float | None = 5,
    brand: str = "Apple",
    normalized_subtype: str = "卡图",
) -> dict:
    raw_subtype = "代码/卡密" if normalized_subtype == "代码" else normalized_subtype
    item = quote(rate, raw_subtype=raw_subtype, amount=denom_min or 1)
    item["supplier_group"] = group
    item["brand"] = brand
    item["country"] = country
    item["currency"] = currency
    item["frontend_type"] = "code" if normalized_subtype in {"代码", "电子卡"} else "physical"
    item["raw_card_subtype"] = raw_subtype
    item["subtype"] = raw_subtype
    item["normalized_card_subtype"] = normalized_subtype
    item["denom_min"] = denom_min
    item["denom_max"] = denom_max
    item["multiplier"] = multiplier
    return item


def save_confirmed_price(
    conn: sqlite3.Connection,
    price: object,
    *,
    brand: str = "Apple",
    country: str = "US",
    currency: str = "USD",
    normalized_subtype: str = "卡图",
    denom_min: float | None = 10,
    denom_max: float | None = 190,
    range_type: str = "bounded",
    multiplier: float | None = 5,
) -> None:
    market_id = conn.execute(
        "SELECT id FROM card_markets WHERE country = ? AND currency = ?",
        (country, currency),
    ).fetchone()["id"]
    timestamp = "2026-06-25 10:00:00"
    conn.execute(
        """
        INSERT INTO confirmed_app_prices (
            brand, market_id, market_label, normalized_subtype, denom_min, denom_max,
            range_type, multiplier, confirmed_price, confirmed_by_operator,
            confirmed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '测试', ?, ?, ?)
        """,
        (
            brand,
            market_id,
            market_label(country, currency),
            normalized_subtype,
            denom_min,
            denom_max,
            range_type,
            multiplier,
            price,
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def latest_app_record(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM app_price_records ORDER BY id DESC LIMIT 1").fetchone()


def latest_app_suggestion(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM app_price_suggestions ORDER BY id DESC LIMIT 1").fetchone()


def pending_app_suggestions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM app_price_suggestions WHERE status = 'pending' ORDER BY id").fetchall()


def quote_row_payload_from_quote(item: dict) -> QuoteRowPayload:
    market = f"{item['country']}|{item['currency']}"
    range_type = "unlimited" if item.get("denom_min") is None and item.get("denom_max") is None else (
        "open" if item.get("denom_max") is None else ("fixed" if item.get("denom_min") == item.get("denom_max") else "bounded")
    )
    return QuoteRowPayload(
        line_no=item.get("line_no", 1),
        source_line=item.get("source_line") or item.get("source_text") or "",
        source_text=item.get("source_text") or item.get("source_line") or "",
        brand=item.get("brand") or "",
        market=market,
        country=item.get("country") or "",
        currency=item.get("currency") or "",
        frontend_type=item.get("frontend_type") or "",
        subtype=item.get("subtype") or item.get("raw_card_subtype") or "",
        raw_card_subtype=item.get("raw_card_subtype") or item.get("subtype") or "",
        normalized_card_subtype=item.get("normalized_card_subtype") or "",
        processing_method=item.get("processing_method") or "fast_card",
        multiplier=item.get("multiplier"),
        denom_min=item.get("denom_min"),
        denom_max=item.get("denom_max"),
        range_type=range_type,
        supplier_rate=Decimal(str(item.get("supplier_rate"))),
        status=item.get("status") or "active",
        requirements=item.get("requirements") or "",
        confidence=item.get("confidence", 0.99),
    )


FORBIDDEN_SUGGESTION_REASON_WORDS = [
    "APP 分类",
    "完整覆盖",
    "分类价格填 0",
    "管理后台分类名称",
    "系统确认价",
    "系统记录价",
]


def assert_no_category_words(reason: str | None) -> None:
    text = reason or ""
    for word in FORBIDDEN_SUGGESTION_REASON_WORDS:
        assert word not in text, text


def test_suggestion_from_supplier_quote_dimensions() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        save_quote_batch(conn, "1003", [supplier_dimension_quote("1003", 5.30)])
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "first_confirm"
        assert money(record["highest_supplier_rate"]) == money("5.45")
        assert money(record["second_supplier_rate"]) == money("5.40")
        assert money(record["third_supplier_rate"]) == money("5.30")
        assert money(record["suggested_backend_rate"]) == money("5.45")
        assert record["recorded_backend_rate"] is None
    finally:
        conn.close()


def test_update_needed_when_confirmed_price_differs() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "update_needed"
        assert money(record["change_amount"]) == money("0.05")
        assert "上调" in record["reason"]
    finally:
        conn.close()


def test_no_change_when_price_same() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.45")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "no_change"
        assert list_app_prices(conn, "needs") == []
    finally:
        conn.close()


def test_no_available_quote_only_when_previously_confirmed() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "no_available_quote"
        assert money(record["suggested_backend_rate"]) == money(0)
    finally:
        conn.close()


def test_no_available_quote_not_shown_when_never_confirmed() -> None:
    conn = make_connection()
    try:
        recalculate_app_prices(conn)
        assert conn.execute("SELECT COUNT(*) FROM app_price_records").fetchone()[0] == 0
    finally:
        conn.close()


def test_zero_confirmed_zero_suggested_is_no_change() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "0")
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "no_change"
        assert money(record["recorded_backend_rate"]) == money(0)
        assert money(record["suggested_backend_rate"]) == money(0)
        assert conn.execute(
            "SELECT COUNT(*) FROM app_price_records WHERE status IN ('first_confirm', 'update_needed', 'no_available_quote')"
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_paused_group_excluded_from_ranking() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.60)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        group = get_or_create_supplier_group(conn, "1001")
        transition_supplier_group(conn, group["id"], "paused", "pause_group", "测试", "暂停")
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert money(record["highest_supplier_rate"]) == money("5.40")
        assert record["highest_supplier_group"] == "1002"
    finally:
        conn.close()


def test_needs_refresh_group_excluded_from_ranking() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.60)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        group = get_or_create_supplier_group(conn, "1001")
        transition_supplier_group(conn, group["id"], "paused", "pause_group", "测试", "暂停")
        transition_supplier_group(conn, group["id"], "needs_refresh", "mark_group_needs_refresh", "测试", "待刷新")
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert money(record["highest_supplier_rate"]) == money("5.40")
        assert record["highest_supplier_group"] == "1002"
    finally:
        conn.close()


def test_save_quotes_only_returns_affected_suggestions() -> None:
    conn = make_connection()
    try:
        other = supplier_dimension_quote("2001", 9.99, country="Canada", currency="CAD")
        other_batch = save_quote_batch(conn, "2001", [other])
        recalculate_app_prices(conn, affected_quote_ids=other_batch["inserted_ids"], affected_batch_id=other_batch["quote_batch_id"])
        result = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=result["inserted_ids"], affected_batch_id=result["quote_batch_id"])
        affected = conn.execute(
            "SELECT * FROM app_price_records WHERE affected_quote_batch_id = ?",
            (result["quote_batch_id"],),
        ).fetchall()
        assert len(affected) == 1
        assert affected[0]["brand"] == "Apple"
        assert affected[0]["country"] == "US"
    finally:
        conn.close()


def test_app_categories_not_used_for_suggestions() -> None:
    conn = make_connection()
    try:
        app_category(conn, category_name="APPLE|US美国|10-190|5倍数", denom_min=10, denom_max=190, multiplier=5)
        recalculate_app_prices(conn)
        assert conn.execute("SELECT COUNT(*) FROM app_price_records").fetchone()[0] == 0
    finally:
        conn.close()


def test_suggestions_do_not_use_app_categories() -> None:
    conn = make_connection()
    try:
        for index in range(100):
            app_category(
                conn,
                category_name=f"APP-CATEGORY-ONLY-{index}",
                denom_min=10,
                denom_max=190,
                range_type="bounded",
                multiplier=5,
                current_app_price=5.0,
            )
        recalculate_app_prices(conn)
        assert conn.execute("SELECT COUNT(*) FROM app_categories").fetchone()[0] == 100
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM confirmed_app_prices").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_price_records").fetchone()[0] == 0
    finally:
        conn.close()


def test_save_quote_returns_only_supplier_dimension_suggestion() -> None:
    conn = make_connection()
    try:
        result = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=result["inserted_ids"], affected_batch_id=result["quote_batch_id"])
        rows = list_app_prices(conn, "needs", affected_batch_id=result["quote_batch_id"])
        assert len(rows) == 1
        record = rows[0]
        assert record["status"] == "pending"
        assert record["recorded_backend_rate"] is None
        assert money(record["highest_supplier_rate"]) == money("5.45")
        assert money(record["suggested_backend_rate"]) == money("5.45")
        assert record["category_name"] is None
        assert record["app_category_id"] is None
        assert_no_category_words(record["reason"])
    finally:
        conn.close()


def test_existing_app_categories_do_not_create_zero_suggestions() -> None:
    conn = make_connection()
    try:
        app_category(
            conn,
            category_name="APPLE|AUSTRIA|CODE|10-200|5",
            brand="Apple",
            country="Austria",
            currency="EUR",
            app_card_type="code",
            normalized_subtype="代码",
            denom_min=10,
            denom_max=200,
            range_type="bounded",
            multiplier=5,
            current_app_price=0,
        )
        recalculate_app_prices(conn)
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM confirmed_app_prices").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM app_price_records").fetchone()[0] == 0
    finally:
        conn.close()


def test_confirmed_zero_no_quote_not_in_needs_action() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "0")
        recalculate_app_prices(conn)
        assert latest_app_record(conn)["status"] == "no_change"
        assert list_app_prices(conn, "needs") == []
    finally:
        conn.close()


def test_no_available_only_when_confirmed_price_positive() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        recalculate_app_prices(conn)
        needs = list_app_prices(conn, "needs")
        assert len(needs) == 1
        assert needs[0]["status"] == "pending"
        assert money(needs[0]["suggested_backend_rate"]) == money(0)
        assert_no_category_words(needs[0]["reason"])
    finally:
        conn.close()


def test_reason_text_has_no_app_category_words() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_confirmed_price(conn, "5.40")
        recalculate_app_prices(conn)
        for row in conn.execute("SELECT reason FROM app_price_records").fetchall():
            assert_no_category_words(row["reason"])
        bulk_confirm_app_prices(conn, "needs", operator="客服甲")
        confirmed = conn.execute("SELECT source_type FROM confirmed_app_prices ORDER BY id DESC LIMIT 1").fetchone()
        assert confirmed["source_type"] == "manual_confirm"
    finally:
        conn.close()


def test_save_quotes_supersedes_old_by_group_brand_market() -> None:
    conn = make_connection()

    @contextmanager
    def fake_get_connection():
        yield conn

    original_get_connection = main_module.get_connection
    main_module.get_connection = fake_get_connection
    try:
        old_us_physical = supplier_dimension_quote("1011", 5.40, normalized_subtype="卡图", denom_min=10, denom_max=190)
        old_us_code = supplier_dimension_quote("1011", 5.10, normalized_subtype="代码", denom_min=10, denom_max=200)
        old_cad = supplier_dimension_quote("1011", 3.70, country="Canada", currency="CAD", denom_min=10, denom_max=500)
        other_group_us = supplier_dimension_quote("1012", 5.45, normalized_subtype="卡图", denom_min=10, denom_max=190)
        save_quote_batch(conn, "1011", [old_us_physical, old_us_code, old_cad])
        save_quote_batch(conn, "1012", [other_group_us])

        new_row = quote_row_payload_from_quote(
            supplier_dimension_quote("1011", 5.50, normalized_subtype="卡图", denom_min=10, denom_max=190)
        )
        preview = main_module.save_quotes_preview(QuoteSavePayload(supplier_group="1011", rows=[new_row]))
        assert preview["new_quote_count"] == 1
        assert preview["supersede_quote_count"] == 2
        assert preview["groups"][0]["source_group"] == "1011"
        assert preview["groups"][0]["brand"] == "Apple"
        assert preview["groups"][0]["country"] == "US"

        try:
            main_module.save_quotes_json(QuoteSavePayload(supplier_group="1011", rows=[new_row]))
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409
        else:
            raise AssertionError("未确认覆盖预览时不应直接保存覆盖")

        result = main_module.save_quotes_json(
            QuoteSavePayload(supplier_group="1011", rows=[new_row], confirm_supersede=True)
        )
        assert result["saved_count"] == 1
        assert len(result["superseded_ids"]) == 2

        statuses = {
            (row["supplier_group"], row["country"], row["currency"], row["normalized_card_subtype"], row["supplier_rate_text"]): row["status"]
            for row in conn.execute(
                """
                SELECT supplier_group, country, currency, normalized_card_subtype, supplier_rate_text, status
                FROM supplier_quotes
                WHERE brand = 'Apple'
                """
            ).fetchall()
        }
        assert statuses[("1011", "US", "USD", "卡图", "5.4")] == "superseded"
        assert statuses[("1011", "US", "USD", "代码", "5.1")] == "superseded"
        assert statuses[("1011", "Canada", "CAD", "卡图", "3.7")] == "active"
        assert statuses[("1012", "US", "USD", "卡图", "5.45")] == "active"
        assert statuses[("1011", "US", "USD", "卡图", "5.5")] == "active"

        matches = find_matches(conn, match_query(amount=50))
        groups = [item["supplier_group"] for item in matches["matches"]]
        assert groups[:2] == ["1011", "1012"], groups
        assert money(matches["matches"][0]["supplier_rate"]) == money("5.5")
        assert all(item["id"] not in result["superseded_ids"] for item in matches["matches"])
    finally:
        main_module.get_connection = original_get_connection
        conn.close()


def test_multi_brand_batch_supersedes_independently() -> None:
    conn = make_connection()
    try:
        old_quotes = [
            supplier_dimension_quote("1011", 5.10, brand="Apple", country="US", currency="USD"),
            supplier_dimension_quote("1011", 0.80, brand="Steam", country="Switzerland", currency="CHF"),
            supplier_dimension_quote("1011", 3.20, brand="Roblox", country="US", currency="USD"),
            supplier_dimension_quote("1011", 3.70, brand="Apple", country="Canada", currency="CAD"),
        ]
        save_quote_batch(conn, "1011", old_quotes)
        new_quotes = [
            supplier_dimension_quote("1011", 5.20, brand="Apple", country="US", currency="USD"),
            supplier_dimension_quote("1011", 0.85, brand="Steam", country="Switzerland", currency="CHF"),
            supplier_dimension_quote("1011", 3.30, brand="Roblox", country="US", currency="USD"),
        ]
        preview = analyze_supersede_preview(conn, "1011", new_quotes)
        assert preview["new_quote_count"] == 3
        assert preview["supersede_quote_count"] == 3
        assert {
            (item["brand"], item["country"], item["currency"], item["new_count"], item["supersede_count"])
            for item in preview["groups"]
        } == {
            ("Apple", "US", "USD", 1, 1),
            ("Steam", "Switzerland", "CHF", 1, 1),
            ("Roblox", "US", "USD", 1, 1),
        }
        result = save_quote_batch(conn, "1011", new_quotes)
        assert len(result["superseded_ids"]) == 3
        cad = conn.execute(
            "SELECT status FROM supplier_quotes WHERE supplier_group = '1011' AND brand = 'Apple' AND country = 'Canada'"
        ).fetchone()
        assert cad["status"] == "active"
    finally:
        conn.close()


def test_pending_market_blocks_save() -> None:
    conn = make_connection()
    try:
        row = quote_row_payload_from_quote(supplier_dimension_quote("待确认群", 5.0))
        row.market = ""
        row.country = ""
        row.currency = ""
        errors, _ = _validated_quotes(conn, "待确认群", [row])
        assert any("地区/币种未确认" in error for error in errors)
    finally:
        conn.close()


def test_pending_brand_blocks_save() -> None:
    conn = make_connection()
    try:
        row = quote_row_payload_from_quote(supplier_dimension_quote("待确认群", 5.0))
        row.brand = ""
        errors, _ = _validated_quotes(conn, "待确认群", [row])
        assert any("品牌未确认" in error for error in errors)
    finally:
        conn.close()


def test_superseded_quotes_hidden_by_default() -> None:
    conn = make_connection()
    try:
        normal_quotes = [
            supplier_dimension_quote(f"normal-{index}", 5.0 + index / 100, denom_min=10 + index, denom_max=10 + index)
            for index in range(10)
        ]
        history_quotes = [
            supplier_dimension_quote("history", 1.0, denom_min=1000 + index, denom_max=1000 + index)
            for index in range(1000)
        ]
        save_quote_batch(conn, "normal", normal_quotes)
        save_quote_batch(conn, "history", history_quotes)
        conn.execute("UPDATE supplier_quotes SET status = 'superseded' WHERE supplier_group = 'history'")

        default_rows = list_filtered_supplier_quotes(conn, {}, limit=None)
        history_rows = list_filtered_supplier_quotes(conn, {"include_history": "yes", "status": "superseded"}, limit=None)
        assert len(default_rows) == 10
        assert all(row["status"] == "active" for row in default_rows)
        assert len(history_rows) == 1000
        assert all(row["status"] == "superseded" for row in history_rows)
    finally:
        conn.close()


def test_include_history_shows_superseded_quotes() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "history", [supplier_dimension_quote("history", 5.0)])
        conn.execute("UPDATE supplier_quotes SET status = 'superseded' WHERE supplier_group = 'history'")
        assert list_filtered_supplier_quotes(conn, {}, limit=None) == []
        rows = list_filtered_supplier_quotes(conn, {"include_history": "yes", "status": "superseded"}, limit=None)
        assert len(rows) == 1
        assert rows[0]["status"] == "superseded"
    finally:
        conn.close()


def test_bulk_pause_excludes_superseded_by_default() -> None:
    conn = make_connection()
    try:
        normal_quotes = [
            supplier_dimension_quote("normal", 5.0, denom_min=10 + index, denom_max=10 + index)
            for index in range(10)
        ]
        history_quotes = [
            supplier_dimension_quote("history", 1.0, denom_min=1000 + index, denom_max=1000 + index)
            for index in range(1000)
        ]
        save_quote_batch(conn, "normal", normal_quotes)
        save_quote_batch(conn, "history", history_quotes)
        conn.execute("UPDATE supplier_quotes SET status = 'superseded' WHERE supplier_group = 'history'")
        result = bulk_update_quote_status(
            conn,
            action="pause",
            mode="filtered",
            filters={},
            operator="客服甲",
            reason="测试默认只处理当前有效报价",
            force_confirm=True,
        )
        assert result["affected_quote_count"] == 10
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = 'normal' AND status = 'paused'").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group = 'history' AND status = 'superseded'").fetchone()[0] == 1000
    finally:
        conn.close()


def test_suggestions_only_show_price_impacted_items() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.40)])
        save_confirmed_price(conn, "5.45")
        result = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"], affected_batch_id=result["quote_batch_id"])
        assert list_app_prices(conn, "needs", affected_batch_id=result["quote_batch_id"]) == []
        rows = conn.execute(
            "SELECT status FROM app_price_records WHERE affected_quote_batch_id = ?",
            (result["quote_batch_id"],),
        ).fetchall()
        assert {row["status"] for row in rows} == {"no_change"}
    finally:
        conn.close()


def test_suggestions_show_when_highest_changed() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.30)])
        save_confirmed_price(conn, "5.45")
        result = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.20)])
        recalculate_app_prices(conn, affected_quote_ids=result["affected_quote_ids"], affected_batch_id=result["quote_batch_id"])
        needs = list_app_prices(conn, "needs", affected_batch_id=result["quote_batch_id"])
        assert len(needs) == 1
        assert needs[0]["status"] == "pending"
        assert money(needs[0]["highest_supplier_rate"]) == money("5.30")
        assert money(needs[0]["suggested_backend_rate"]) == money("5.30")
    finally:
        conn.close()


def test_source_change_same_price_not_pending() -> None:
    conn = make_connection()
    try:
        first = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_confirmed_price(conn, "5.45")
        recalculate_app_prices(conn, affected_quote_ids=first["affected_quote_ids"], affected_batch_id=first["quote_batch_id"])
        conn.execute("UPDATE supplier_quotes SET updated_at = '2026-06-24 12:00:00' WHERE supplier_group = '1001'")
        second = save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=second["affected_quote_ids"], affected_batch_id=second["quote_batch_id"])
        needs = list_app_prices(conn, "needs", affected_batch_id=second["quote_batch_id"])
        assert needs == []
        assert conn.execute("SELECT COUNT(*) FROM app_price_suggestions WHERE status = 'pending'").fetchone()[0] == 0
    finally:
        conn.close()


def test_unconfirmed_admin_price_displayed_as_zero() -> None:
    template = (ROOT / "app" / "templates" / "quotes.html").read_text(encoding="utf-8")
    assert "<th>管理后台价</th>" in template
    assert "{% if record.recorded_backend_rate is none %}0" in template
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        record = latest_app_record(conn)
        assert record["status"] == "first_confirm"
        assert record["recorded_backend_rate"] is None
        assert money(record["change_amount"]) == money("5.45")
        assert "管理后台价" in record["reason"]
        suggestion = latest_app_suggestion(conn)
        assert suggestion["status"] == "pending"
        assert suggestion["admin_price"] is None
        assert suggestion["admin_price_is_confirmed"] == 0
    finally:
        conn.close()


def test_confirm_fill_zero_writes_zero() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        recalculate_app_prices(conn)
        record = latest_app_suggestion(conn)
        assert record["status"] == "pending"
        assert money(record["suggested_price"]) == money("0")
        confirm_app_price(conn, record["id"], operator="客服甲", action="confirm_zero")
        confirmed = conn.execute("SELECT confirmed_price FROM confirmed_app_prices ORDER BY id DESC LIMIT 1").fetchone()
        assert money(confirmed["confirmed_price"]) == money("0")
        stored = conn.execute("SELECT status FROM app_price_suggestions WHERE id = ?", (record["id"],)).fetchone()
        assert stored["status"] == "filled_zero"
    finally:
        conn.close()


def test_confirm_synced_writes_suggested_price() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        record = latest_app_suggestion(conn)
        confirm_app_price(conn, record["id"], operator="客服甲", action="confirm_update")
        confirmed = conn.execute("SELECT confirmed_price FROM confirmed_app_prices ORDER BY id DESC LIMIT 1").fetchone()
        assert money(confirmed["confirmed_price"]) == money("5.45")
        stored = conn.execute("SELECT status FROM app_price_suggestions WHERE id = ?", (record["id"],)).fetchone()
        assert stored["status"] == "synced_to_admin"
    finally:
        conn.close()


def test_pending_suggestion_persists_after_navigation() -> None:
    conn = make_connection()
    try:
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        first_needs = list_app_prices(conn, "needs")
        assert len(first_needs) == 1

        find_matches(conn, match_query(amount=50))
        second_needs = list_app_prices(conn, "needs")
        assert len(second_needs) == 1
        assert second_needs[0]["id"] == first_needs[0]["id"]
        assert second_needs[0]["status"] == "pending"
    finally:
        conn.close()


def test_zero_change_not_in_pending_suggestions() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.45")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        assert list_app_prices(conn, "needs") == []
        closed = list_app_prices(conn, "no_change")
        assert all(row["status"] == "auto_closed_no_change" for row in closed)
    finally:
        conn.close()


def test_new_suggestion_supersedes_old_pending() -> None:
    conn = make_connection()
    try:
        first = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=first["affected_quote_ids"], affected_batch_id=first["quote_batch_id"])
        old = pending_app_suggestions(conn)
        assert len(old) == 1

        second = save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.55)])
        recalculate_app_prices(conn, affected_quote_ids=second["affected_quote_ids"], affected_batch_id=second["quote_batch_id"])
        pending = pending_app_suggestions(conn)
        assert len(pending) == 1
        assert pending[0]["id"] != old[0]["id"]
        assert money(pending[0]["suggested_price"]) == money("5.55")
        superseded = conn.execute("SELECT * FROM app_price_suggestions WHERE id = ?", (old[0]["id"],)).fetchone()
        assert superseded["status"] == "superseded"
        assert superseded["superseded_by_suggestion_id"] == pending[0]["id"]
    finally:
        conn.close()


def test_auto_close_when_admin_price_matches_latest_suggestion() -> None:
    conn = make_connection()
    try:
        first = save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn, affected_quote_ids=first["affected_quote_ids"], affected_batch_id=first["quote_batch_id"])
        pending = pending_app_suggestions(conn)
        assert len(pending) == 1
        save_confirmed_price(conn, "5.45")
        recalculate_app_prices(conn)
        assert list_app_prices(conn, "needs") == []
        stored = conn.execute("SELECT status FROM app_price_suggestions WHERE id = ?", (pending[0]["id"],)).fetchone()
        assert stored["status"] == "auto_closed_no_change"
    finally:
        conn.close()


def test_ignore_suggestion_does_not_update_confirmed_price() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        suggestion = latest_app_suggestion(conn)
        from app.pricing import defer_app_price

        defer_app_price(conn, suggestion["id"], operator="客服甲", reason="稍后人工处理")
        stored = conn.execute("SELECT status FROM app_price_suggestions WHERE id = ?", (suggestion["id"],)).fetchone()
        confirmed = conn.execute("SELECT confirmed_price FROM confirmed_app_prices ORDER BY id DESC LIMIT 1").fetchone()
        assert stored["status"] == "ignored"
        assert money(confirmed["confirmed_price"]) == money("5.40")
    finally:
        conn.close()


def test_bulk_sync_admin_updates_all_pending_suggestions() -> None:
    conn = make_connection()
    try:
        save_quote_batch(
            conn,
            "1001",
            [
                supplier_dimension_quote("1001", 5.45, country="US", currency="USD"),
                supplier_dimension_quote("1001", 3.40, country="Canada", currency="CAD"),
                supplier_dimension_quote("1001", 5.90, country="UK", currency="GBP"),
            ],
        )
        recalculate_app_prices(conn)
        assert len(pending_app_suggestions(conn)) == 3
        confirmed_count = bulk_confirm_app_prices(conn, "needs", operator="客服甲")
        assert confirmed_count == 3
        assert pending_app_suggestions(conn) == []
        assert conn.execute("SELECT COUNT(*) FROM app_price_suggestions WHERE status = 'synced_to_admin'").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM confirmed_app_prices").fetchone()[0] == 3
    finally:
        conn.close()


def test_reason_detail_available_on_pending_suggestion() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        save_quote_batch(conn, "1002", [supplier_dimension_quote("1002", 5.35)])
        recalculate_app_prices(conn)
        suggestion = latest_app_suggestion(conn)
        detail = suggestion["reason_detail"]
        assert suggestion["status"] == "pending"
        assert "5.4" in detail
        assert "5.45" in detail
        assert "1001" in detail
        assert "1002" in detail
    finally:
        conn.close()


def test_reason_uses_admin_price_wording() -> None:
    conn = make_connection()
    try:
        save_confirmed_price(conn, "5.40")
        save_quote_batch(conn, "1001", [supplier_dimension_quote("1001", 5.45)])
        recalculate_app_prices(conn)
        for row in conn.execute("SELECT reason FROM app_price_records").fetchall():
            assert_no_category_words(row["reason"])
            assert "管理后台价" in row["reason"]
    finally:
        conn.close()



def test_app_category_ui_and_csv_import() -> None:
    template = (ROOT / "app" / "templates" / "app_categories.html").read_text(encoding="utf-8")
    assert "category_names_text" in template
    assert "parse_app_category_names_route" in template
    assert "save_parsed_app_categories_route" in template
    assert 'name="category_name_' in template
    assert 'name="current_app_price_' in template

    conn = make_connection()
    try:
        report = import_app_categories_csv(
            conn,
            """category_name,brand,country,currency,app_card_type,normalized_subtype,denom_min,denom_max,range_type,multiplier,current_app_price,discount,speed_type,status
APPLE|CA加拿大|10-300|5倍数,Apple,Canada,CAD,physical,卡图,10,300,bounded,5,3.55,0.99,Fast,active
坏行,Unknown,Canada,CAD,physical,卡图,10,300,bounded,5,3.55,0.99,Fast,active
""",
        )
        assert report["success_count"] == 2
        assert report["skip_count"] == 0
        stored = conn.execute("SELECT category_name, current_app_price FROM app_categories").fetchone()
        assert stored["category_name"] == "APPLE|CA加拿大|10-300|5倍数"
        assert money(stored["current_app_price"]) == money(3.55)
    finally:
        conn.close()

def test_app_category_ui_and_csv_import() -> None:
    template = (ROOT / "app" / "templates" / "quotes.html").read_text(encoding="utf-8")
    assert "管理后台卡分类名称" in template
    assert "data-copy-button" in template
    assert "已在管理后台填0" in template
    assert "当前没有可用于 APP 建议价的 active 快卡/快刷报价" not in template
    assert "建议暂停" not in template

    conn = make_connection()
    try:
        report = import_app_categories_csv(
            conn,
            """category_name,brand,country,currency,app_card_type,normalized_subtype,denom_min,denom_max,range_type,multiplier,current_app_price,discount,speed_type,status
APPLE|CA加拿大|10-300|5倍数,Apple,Canada,CAD,physical,卡图,10,300,bounded,5,3.55,0.99,Fast,active
坏行,Unknown,Canada,CAD,physical,卡图,10,300,bounded,5,3.55,0.99,Fast,active
""",
        )
        assert report["success_count"] == 2
        assert report["skip_count"] == 0
        stored = conn.execute("SELECT category_name, current_app_price FROM app_categories").fetchone()
        assert stored["category_name"] == "APPLE|CA加拿大|10-300|5倍数"
        assert money(stored["current_app_price"]) == money(3.55)
    finally:
        conn.close()


def test_parse_app_category_name_default_two_subtypes() -> None:
    conn = make_connection()
    try:
        rows = parse_app_category_names(conn, "Amazon|AUD澳大利亚|25-200|1倍数")["rows"]
        assert len(rows) == 2
        assert {row["brand"] for row in rows} == {"Amazon"}
        assert {(row["country"], row["currency"]) for row in rows} == {("Australia", "AUD")}
        assert {
            (row["normalized_subtype"], row["app_card_type"])
            for row in rows
        } == {("卡图", "physical"), ("代码", "code")}
        assert {row["denom_min"] for row in rows} == {25.0}
        assert {row["denom_max"] for row in rows} == {200.0}
        assert {row["multiplier"] for row in rows} == {1.0}
        assert {row["category_name"] for row in rows} == {"Amazon|AUD澳大利亚|25-200|1倍数"}
    finally:
        conn.close()


def test_parse_app_category_name_explicit_subtype() -> None:
    conn = make_connection()
    try:
        rows = parse_app_category_names(conn, "APPLE|US美国|10-190|5倍数|卡图")["rows"]
        assert len(rows) == 1
        assert rows[0]["brand"] == "Apple"
        assert rows[0]["country"] == "US"
        assert rows[0]["currency"] == "USD"
        assert rows[0]["normalized_subtype"] == "卡图"
        assert rows[0]["app_card_type"] == "physical"
    finally:
        conn.close()


def test_parse_app_category_open_range() -> None:
    conn = make_connection()
    try:
        rows = parse_app_category_names(conn, "APPLE|JP日本|10000以上|1000倍数")["rows"]
        assert len(rows) == 2
        assert {row["denom_min"] for row in rows} == {10000.0}
        assert {row["denom_max"] for row in rows} == {None}
        assert {row["range_type"] for row in rows} == {"open"}
        assert {row["multiplier"] for row in rows} == {1000.0}
    finally:
        conn.close()


def test_save_category_name_duplicate_by_subtype() -> None:
    conn = make_connection()
    try:
        rows = parse_app_category_names(conn, "Amazon|AUD澳大利亚|25-200|1倍数")["rows"]
        first = save_app_categories_bulk(conn, rows)
        second = save_app_categories_bulk(conn, rows)
        assert first["created_count"] == 2
        assert first["updated_count"] == 0
        assert second["created_count"] == 0
        assert second["updated_count"] == 2
        assert conn.execute("SELECT COUNT(*) FROM app_categories").fetchone()[0] == 2
        stored = conn.execute(
            "SELECT category_name, normalized_subtype FROM app_categories ORDER BY normalized_subtype"
        ).fetchall()
        assert {row["normalized_subtype"] for row in stored} == {"卡图", "代码"}
    finally:
        conn.close()


def test_app_category_form_hides_unused_fields() -> None:
    template = (ROOT / "app" / "templates" / "app_categories.html").read_text(encoding="utf-8")
    assert 'name="discount"' not in template
    assert 'name="speed_type"' not in template
    assert 'name="app_card_type"' not in template
    assert 'name="range_type"' not in template
    assert "批量解析 APP 分类名称" in template
    assert "确认保存分类" in template


def main() -> None:
    test_subtype_normalization()
    test_match_page_simple_filter_rank()
    test_brand_aware_subtype_migration()
    test_rank_group_status_batch_and_logs()
    test_pause_group_recalculate_suggestions()
    test_pause_group_no_available_quote()
    test_pause_impact_uses_shipment_matching_logic()
    test_pause_impact_full_cover_suggests_price()
    test_pause_impact_no_candidate_really_no_quote()
    test_partial_range_does_not_become_no_quote()
    test_partial_multiplier_does_not_become_no_quote()
    test_same_price_after_pause_no_change()
    test_paused_superseded_expired_quotes_excluded_from_pause_impact()
    test_restore_group_needs_refresh()
    test_confirm_reuse_old_quotes()
    test_save_new_quote_reactivates_needs_refresh_group()
    test_safe_confirmation_and_market_decline()
    test_razer_unbounded_save_pricing_matching_and_market_labels()
    test_open_range_json_validation_and_save()
    test_open_ended_range_save_pricing_and_matching()
    test_manual_pause_supplier_group_brand()
    test_bulk_pause_selected_quotes()
    test_bulk_pause_filtered_by_group()
    test_bulk_pause_filtered_by_group_brand_market()
    test_pause_recalculates_suggestions()
    test_resume_recalculates_suggestions()
    test_bulk_pause_no_filters_warning()
    test_paused_quote_excluded_from_match()
    test_bulk_action_log_created()
    test_roblox_matrix_save_pricing_and_unbounded_matching()
    test_amazon_distinct_physical_and_code_app_prices()
    test_paysafecard_default_same_rate_app_prices()
    test_long_tail_multi_range_save_and_app_prices()
    test_suggestion_from_supplier_quote_dimensions()
    test_update_needed_when_confirmed_price_differs()
    test_no_change_when_price_same()
    test_no_available_quote_only_when_previously_confirmed()
    test_no_available_quote_not_shown_when_never_confirmed()
    test_zero_confirmed_zero_suggested_is_no_change()
    test_paused_group_excluded_from_ranking()
    test_needs_refresh_group_excluded_from_ranking()
    test_save_quotes_only_returns_affected_suggestions()
    test_app_categories_not_used_for_suggestions()
    test_suggestions_do_not_use_app_categories()
    test_save_quote_returns_only_supplier_dimension_suggestion()
    test_existing_app_categories_do_not_create_zero_suggestions()
    test_confirmed_zero_no_quote_not_in_needs_action()
    test_no_available_only_when_confirmed_price_positive()
    test_reason_text_has_no_app_category_words()
    test_save_quotes_supersedes_old_by_group_brand_market()
    test_multi_brand_batch_supersedes_independently()
    test_pending_market_blocks_save()
    test_pending_brand_blocks_save()
    test_superseded_quotes_hidden_by_default()
    test_include_history_shows_superseded_quotes()
    test_bulk_pause_excludes_superseded_by_default()
    test_suggestions_only_show_price_impacted_items()
    test_suggestions_show_when_highest_changed()
    test_source_change_same_price_not_pending()
    test_unconfirmed_admin_price_displayed_as_zero()
    test_confirm_fill_zero_writes_zero()
    test_confirm_synced_writes_suggested_price()
    test_pending_suggestion_persists_after_navigation()
    test_zero_change_not_in_pending_suggestions()
    test_new_suggestion_supersedes_old_pending()
    test_auto_close_when_admin_price_matches_latest_suggestion()
    test_ignore_suggestion_does_not_update_confirmed_price()
    test_bulk_sync_admin_updates_all_pending_suggestions()
    test_reason_detail_available_on_pending_suggestion()
    test_reason_uses_admin_price_wording()
    test_parse_app_category_name_default_two_subtypes()
    test_parse_app_category_name_explicit_subtype()
    test_parse_app_category_open_range()
    test_save_category_name_duplicate_by_subtype()
    test_app_category_form_hides_unused_fields()
    print("quote workflow regression passed")


if __name__ == "__main__":
    main()
