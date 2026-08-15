from __future__ import annotations

import csv
import io
import re
import sqlite3
from decimal import Decimal
from typing import Any

from .database import now_iso
from .money import decimal_text, to_decimal
from .standards import (
    MARKET_DISPLAY_NAMES,
    market_label,
    market_value,
    normalize_brand,
    normalize_card_subtype,
    normalize_market,
    split_market_value,
    standard_brand_names,
)


APP_CATEGORY_FIELDS = [
    "category_name",
    "brand",
    "market",
    "normalized_subtype",
    "denom_min",
    "denom_max",
    "multiplier",
    "current_app_price",
    "status",
    "note",
]

APP_CATEGORY_DB_FIELDS = [
    "category_name",
    "brand",
    "market_id",
    "market_label",
    "country_name_cn",
    "country_name_en",
    "currency",
    "app_card_type",
    "normalized_subtype",
    "denom_min",
    "denom_max",
    "range_type",
    "multiplier",
    "current_app_price",
    "discount",
    "speed_type",
    "status",
    "source_note",
]

CARD_SUBTYPE_OPTIONS = ["卡图", "代码", "电子卡", "竖卡", "待确认"]
STATUS_OPTIONS = ["active", "pending", "disabled"]

CATEGORY_BRAND_ALIASES = {
    "apple": "Apple",
    "itunes": "Apple",
    "itune": "Apple",
    "苹果": "Apple",
    "amazon": "Amazon",
    "amazoncom": "Amazon",
    "亚马逊": "Amazon",
    "美亚": "Amazon",
    "英亚": "Amazon",
    "德亚": "Amazon",
    "加亚": "Amazon",
    "澳亚": "Amazon",
    "意亚": "Amazon",
    "googleplay": "Google Play",
    "google play": "Google Play",
    "谷歌": "Google Play",
    "谷歌play": "Google Play",
    "xbox": "Xbox",
    "psn": "PSN",
    "playstation": "PSN",
    "razer": "Razer",
    "雷蛇": "Razer",
    "steam": "Steam",
    "蒸汽": "Steam",
    "roblox": "Roblox",
    "paysafecard": "Paysafecard",
    "paysafe": "Paysafecard",
    "psc": "Paysafecard",
    "sephora": "Sephora",
    "footlocker": "Footlocker",
    "foot locker": "Footlocker",
    "macy": "Macy",
    "macys": "Macy",
    "macy/9": "Macy",
    "macy/6": "Macy",
    "macy/8": "Macy",
    "visa": "Visa",
    "amex": "Amex",
    "americanexpress": "Amex",
    "vanilla": "Vanilla",
    "香草": "Vanilla",
    "eneba": "Eneba",
    "transcash": "Transcash",
}

CATEGORY_MARKET_ALIASES: list[tuple[str, str, str]] = [
    ("United Arab Emirates", "AED", "AED"),
    ("United Arab Emirates", "AED", "阿联酋"),
    ("Australia", "AUD", "AUD"),
    ("Australia", "AUD", "澳大利亚"),
    ("Australia", "AUD", "澳元"),
    ("Austria", "EUR", "AT"),
    ("Austria", "EUR", "奥地利"),
    ("Belgium", "EUR", "BE"),
    ("Belgium", "EUR", "比利时"),
    ("Brazil", "BRL", "BR"),
    ("Brazil", "BRL", "BRL"),
    ("Brazil", "BRL", "巴西"),
    ("Canada", "CAD", "CAD"),
    ("Canada", "CAD", "CA"),
    ("Canada", "CAD", "加拿大"),
    ("Canada", "CAD", "加元"),
    ("Chile", "CLP", "CLP"),
    ("Chile", "CLP", "智利"),
    ("Colombia", "COP", "COP"),
    ("Colombia", "COP", "哥伦比亚"),
    ("Czech Republic", "CZK", "CZ"),
    ("Czech Republic", "CZK", "CZK"),
    ("Czech Republic", "CZK", "捷克"),
    ("Denmark", "DKK", "DK"),
    ("Denmark", "DKK", "DKK"),
    ("Denmark", "DKK", "丹麦"),
    ("EU", "EUR", "EU"),
    ("EU", "EUR", "EUR"),
    ("EU", "EUR", "欧盟"),
    ("Finland", "EUR", "FI"),
    ("Finland", "EUR", "芬兰"),
    ("France", "EUR", "FR"),
    ("France", "EUR", "法国"),
    ("Germany", "EUR", "DE"),
    ("Germany", "EUR", "德国"),
    ("Greece", "EUR", "GR"),
    ("Greece", "EUR", "希腊"),
    ("Hong Kong", "HKD", "HK"),
    ("Hong Kong", "HKD", "HKD"),
    ("Hong Kong", "HKD", "香港"),
    ("India", "INR", "IN"),
    ("India", "INR", "INR"),
    ("India", "INR", "印度"),
    ("Indonesia", "IDR", "IDR"),
    ("Indonesia", "IDR", "印度尼西亚"),
    ("Ireland", "EUR", "IE"),
    ("Ireland", "EUR", "爱尔兰"),
    ("Israel", "ILS", "ILS"),
    ("Israel", "ILS", "以色列"),
    ("Italy", "EUR", "IT"),
    ("Italy", "EUR", "意大利"),
    ("Japan", "JPY", "JP"),
    ("Japan", "JPY", "JPY"),
    ("Japan", "JPY", "日本"),
    ("Malaysia", "MYR", "MYR"),
    ("Malaysia", "MYR", "马来西亚"),
    ("Mexico", "MXN", "MX"),
    ("Mexico", "MXN", "MXN"),
    ("Mexico", "MXN", "墨西哥"),
    ("Netherlands", "EUR", "NL"),
    ("Netherlands", "EUR", "荷兰"),
    ("New Zealand", "NZD", "NZD"),
    ("New Zealand", "NZD", "新西兰"),
    ("Norway", "NOK", "NOK"),
    ("Norway", "NOK", "挪威"),
    ("Poland", "PLN", "PL"),
    ("Poland", "PLN", "PLN"),
    ("Poland", "PLN", "波兰"),
    ("Portugal", "EUR", "PT"),
    ("Portugal", "EUR", "葡萄牙"),
    ("Saudi Arabia", "SAR", "SAR"),
    ("Saudi Arabia", "SAR", "沙特"),
    ("Singapore", "SGD", "SGD"),
    ("Singapore", "SGD", "新加坡"),
    ("South Africa", "ZAR", "ZAR"),
    ("South Africa", "ZAR", "南非"),
    ("South Korea", "KRW", "KR"),
    ("South Korea", "KRW", "KRW"),
    ("South Korea", "KRW", "韩国"),
    ("Spain", "EUR", "ES"),
    ("Spain", "EUR", "西班牙"),
    ("Sweden", "SEK", "SEK"),
    ("Sweden", "SEK", "瑞典"),
    ("Switzerland", "CHF", "CH"),
    ("Switzerland", "CHF", "CHF"),
    ("Switzerland", "CHF", "瑞士"),
    ("Taiwan", "TWD", "TWD"),
    ("Taiwan", "TWD", "台湾"),
    ("Thailand", "THB", "THB"),
    ("Thailand", "THB", "泰国"),
    ("Turkey", "TRY", "TRY"),
    ("Turkey", "TRY", "土耳其"),
    ("UK", "GBP", "GBP"),
    ("UK", "GBP", "UK"),
    ("UK", "GBP", "英国"),
    ("US", "USD", "US"),
    ("US", "USD", "USD"),
    ("US", "USD", "美国"),
    ("US", "USD", "美金"),
]


def list_app_categories(conn: sqlite3.Connection, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses = []
    params: list[Any] = []
    for column in ("brand", "status", "normalized_subtype"):
        if filters.get(column):
            clauses.append(f"c.{column} = ?")
            params.append(filters[column])
    if filters.get("app_card_type"):
        clauses.append("c.app_card_type = ?")
        params.append(filters["app_card_type"])
    if filters.get("market"):
        country, currency = split_market_value(filters["market"])
        if country and currency:
            clauses.append("m.country = ? AND m.currency = ?")
            params.extend([country, currency])
    if filters.get("keyword"):
        clauses.append("c.category_name LIKE ?")
        params.append(f"%{filters['keyword']}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT c.*, m.country, m.currency AS market_currency
        FROM app_categories c
        LEFT JOIN card_markets m ON m.id = c.market_id
        {where}
        ORDER BY c.status, c.brand, m.sort_order, c.category_name, c.normalized_subtype
        """,
        params,
    ).fetchall()
    return [_category_view(row) for row in rows]


def get_app_category(conn: sqlite3.Connection, category_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.*, m.country, m.currency AS market_currency
        FROM app_categories c
        LEFT JOIN card_markets m ON m.id = c.market_id
        WHERE c.id = ?
        """,
        (category_id,),
    ).fetchone()
    return _category_view(row) if row else None


def save_app_category(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    normalized, errors = normalize_app_category_payload(conn, data)
    if errors:
        raise ValueError("；".join(errors))
    timestamp = now_iso()
    category_id = _to_int(data.get("id"))
    values = [normalized[field] for field in APP_CATEGORY_DB_FIELDS]
    if category_id:
        conn.execute(
            """
            UPDATE app_categories
            SET category_name = ?,
                brand = ?,
                market_id = ?,
                market_label = ?,
                country_name_cn = ?,
                country_name_en = ?,
                currency = ?,
                app_card_type = ?,
                normalized_subtype = ?,
                denom_min = ?,
                denom_max = ?,
                range_type = ?,
                multiplier = ?,
                current_app_price = ?,
                discount = ?,
                speed_type = ?,
                status = ?,
                source_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            [*values, timestamp, category_id],
        )
        return get_app_category(conn, category_id) or {}

    conn.execute(
        """
        INSERT INTO app_categories (
            category_name, brand, market_id, market_label, country_name_cn,
            country_name_en, currency, app_card_type, normalized_subtype,
            denom_min, denom_max, range_type, multiplier, current_app_price,
            discount, speed_type, status, source_note, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(category_name, normalized_subtype) DO UPDATE SET
            brand = excluded.brand,
            market_id = excluded.market_id,
            market_label = excluded.market_label,
            country_name_cn = excluded.country_name_cn,
            country_name_en = excluded.country_name_en,
            currency = excluded.currency,
            app_card_type = excluded.app_card_type,
            denom_min = excluded.denom_min,
            denom_max = excluded.denom_max,
            range_type = excluded.range_type,
            multiplier = excluded.multiplier,
            current_app_price = excluded.current_app_price,
            discount = excluded.discount,
            speed_type = excluded.speed_type,
            status = excluded.status,
            source_note = excluded.source_note,
            updated_at = excluded.updated_at
        """,
        [*values, timestamp, timestamp],
    )
    return get_app_category_by_name_and_subtype(
        conn,
        normalized["category_name"],
        normalized["normalized_subtype"],
    ) or {}


def get_app_category_by_name_and_subtype(
    conn: sqlite3.Connection,
    category_name: str,
    normalized_subtype: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.*, m.country, m.currency AS market_currency
        FROM app_categories c
        LEFT JOIN card_markets m ON m.id = c.market_id
        WHERE c.category_name = ? AND c.normalized_subtype = ?
        """,
        (category_name, normalized_subtype),
    ).fetchone()
    return _category_view(row) if row else None


def get_app_category_by_name(conn: sqlite3.Connection, category_name: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT c.*, m.country, m.currency AS market_currency
        FROM app_categories c
        LEFT JOIN card_markets m ON m.id = c.market_id
        WHERE c.category_name = ?
        ORDER BY c.id
        LIMIT 1
        """,
        (category_name,),
    ).fetchone()
    return _category_view(row) if row else None


def set_app_category_status(conn: sqlite3.Connection, category_id: int, status: str) -> None:
    if status not in {"active", "pending", "disabled"}:
        raise ValueError("分类状态只能是 active / pending / disabled")
    conn.execute(
        "UPDATE app_categories SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), category_id),
    )


def delete_app_category(conn: sqlite3.Connection, category_id: int) -> None:
    conn.execute("DELETE FROM app_price_records WHERE app_category_id = ?", (category_id,))
    conn.execute("DELETE FROM app_categories WHERE id = ?", (category_id,))


def parse_app_category_names(conn: sqlite3.Connection, text: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parsed = parse_app_category_name(conn, line, line_no=line_no)
        if parsed:
            rows.extend(parsed)
        else:
            ignored.append({"line_no": line_no, "source_line": raw_line, "reason": "无法解析分类名称"})
    return {"rows": rows, "ignored": ignored}


def parse_app_category_name(
    conn: sqlite3.Connection,
    category_name: str,
    *,
    line_no: int | None = None,
) -> list[dict[str, Any]]:
    original = category_name.strip()
    if not original:
        return []
    parts = [part.strip() for part in original.split("|")]
    if len(parts) < 4:
        return []

    brand_raw, market_raw, range_raw, multiplier_raw = parts[:4]
    subtype_raw = " ".join(part for part in parts[4:] if part).strip()

    brand = _normalize_brand_value(brand_raw) or brand_raw.strip()
    brand_known = bool(_normalize_brand_value(brand_raw) or brand_raw.strip() in standard_brand_names())
    country, currency = _normalize_market_value(None, None, market_raw)
    market_known = bool(country and currency and _market_id(conn, country, currency))
    denom_min, denom_max, range_type, range_error = parse_category_range(range_raw)
    multiplier = parse_multiplier(multiplier_raw)
    subtypes = parse_category_subtypes(subtype_raw)
    status = "active" if brand_known and market_known and not range_error and "待确认" not in subtypes else "pending"

    rows = []
    for subtype in subtypes:
        app_card_type = app_card_type_from_subtype(subtype)
        item = {
            "line_no": line_no,
            "category_name": original,
            "brand": brand,
            "brand_known": brand_known,
            "market": market_value(country, currency),
            "market_display": market_label(country, currency) if market_known else "待选择",
            "country": country,
            "currency": currency,
            "market_known": market_known,
            "normalized_subtype": subtype,
            "app_card_type": app_card_type,
            "denom_min": denom_min,
            "denom_max": denom_max,
            "range_type": range_type,
            "multiplier": multiplier,
            "current_app_price": "",
            "status": status,
            "source_note": "；".join(part for part in [range_error] if part),
        }
        rows.append(item)
    return rows


def save_app_categories_bulk(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, Any]:
    report = {"created_count": 0, "updated_count": 0, "skip_count": 0, "errors": []}
    for index, row in enumerate(rows, start=1):
        if row.get("deleted"):
            report["skip_count"] += 1
            continue
        try:
            normalized, errors = normalize_app_category_payload(conn, row)
            if errors:
                report["skip_count"] += 1
                report["errors"].append({"line_no": row.get("line_no") or index, "reason": "；".join(errors)})
                continue
            exists = _category_exists(
                conn,
                normalized["category_name"],
                normalized["normalized_subtype"],
            )
            save_app_category(conn, row)
            if exists:
                report["updated_count"] += 1
            else:
                report["created_count"] += 1
        except ValueError as exc:
            report["skip_count"] += 1
            report["errors"].append({"line_no": row.get("line_no") or index, "reason": str(exc)})
    return report


def import_app_categories_csv(conn: sqlite3.Connection, csv_text: str) -> dict[str, Any]:
    report = {"success_count": 0, "skip_count": 0, "errors": []}
    reader = csv.DictReader(io.StringIO(csv_text.strip("\ufeff")))
    if not reader.fieldnames:
        return {"success_count": 0, "skip_count": 0, "errors": [{"line_no": 1, "reason": "CSV 缺少表头"}]}
    for line_no, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            report["skip_count"] += 1
            continue
        category_name = (row.get("category_name") or "").strip()
        useful_fields = [
            row.get("brand"),
            row.get("market"),
            row.get("country"),
            row.get("currency"),
            row.get("normalized_subtype"),
            row.get("denom_min"),
            row.get("denom_max"),
            row.get("multiplier"),
        ]
        if category_name and not any((value or "").strip() for value in useful_fields):
            parsed = parse_app_category_name(conn, category_name, line_no=line_no)
            if not parsed:
                report["skip_count"] += 1
                report["errors"].append({"line_no": line_no, "reason": "无法解析 category_name"})
                continue
            bulk_report = save_app_categories_bulk(conn, parsed)
            report["success_count"] += bulk_report["created_count"] + bulk_report["updated_count"]
            report["skip_count"] += bulk_report["skip_count"]
            report["errors"].extend(bulk_report["errors"])
            continue
        try:
            save_app_category(conn, row)
            report["success_count"] += 1
        except ValueError as exc:
            report["skip_count"] += 1
            report["errors"].append({"line_no": line_no, "reason": str(exc)})
    return report


def export_app_categories_csv(conn: sqlite3.Connection) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=APP_CATEGORY_FIELDS)
    writer.writeheader()
    for category in list_app_categories(conn, {"status": ""}):
        writer.writerow(
            {
                "category_name": category["category_name"],
                "brand": category["brand"],
                "market": category["market_display"],
                "normalized_subtype": category["normalized_subtype"],
                "denom_min": decimal_text(category["denom_min"]) if category["denom_min"] is not None else "",
                "denom_max": decimal_text(category["denom_max"]) if category["denom_max"] is not None else "",
                "multiplier": decimal_text(category["multiplier"]) if category["multiplier"] is not None else "",
                "current_app_price": (
                    decimal_text(category["current_app_price"])
                    if category["current_app_price"] is not None
                    else ""
                ),
                "status": category["status"],
                "note": category.get("source_note") or "",
            }
        )
    return output.getvalue()


def normalize_app_category_payload(
    conn: sqlite3.Connection,
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors = []
    category_name = str(data.get("category_name") or "").strip()
    if not category_name:
        errors.append("缺少管理后台分类名称")

    brand_raw = str(data.get("brand") or "").strip()
    brand = _normalize_brand_value(brand_raw) or brand_raw
    if not brand:
        errors.append("缺少品牌")
    brand_known = bool(_normalize_brand_value(brand_raw) or brand in standard_brand_names())

    country, currency = _normalize_market_value(
        data.get("country") or data.get("country_name_en"),
        data.get("currency"),
        data.get("market"),
    )
    market_id = _market_id(conn, country, currency) if country and currency else None
    market_known = bool(country and currency and market_id)

    normalized_subtype = parse_single_category_subtype(
        data.get("normalized_subtype") or data.get("subtype") or data.get("raw_card_subtype")
    )
    if normalized_subtype == "待确认":
        errors.append("统一细分无法识别")
    app_card_type = app_card_type_from_subtype(normalized_subtype)

    denom_min = _to_float(data.get("denom_min"))
    denom_max = _to_float(data.get("denom_max"))
    range_type = infer_range_type(denom_min, denom_max)
    if denom_min is None and denom_max is not None:
        errors.append("面额范围非法：只有上限时无法判断范围")

    current_app_price = _to_decimal_text(data.get("current_app_price"), allow_zero=True)
    status = normalize_category_status(data.get("status"))
    if not brand_known or not market_known:
        status = "pending"
    normalized = {
        "category_name": category_name,
        "brand": brand,
        "market_id": market_id,
        "market_label": market_label(country, currency) if market_known else "待选择",
        "country_name_cn": MARKET_DISPLAY_NAMES.get(country, country) if market_known else "",
        "country_name_en": country if market_known else "",
        "currency": currency if market_known else "",
        "app_card_type": app_card_type,
        "normalized_subtype": normalized_subtype,
        "denom_min": denom_min,
        "denom_max": denom_max,
        "range_type": range_type,
        "multiplier": _to_float(data.get("multiplier")),
        "current_app_price": current_app_price,
        "discount": None,
        "speed_type": "",
        "status": status,
        "source_note": str(data.get("source_note") or data.get("note") or "").strip(),
    }
    return normalized, errors


def app_card_type_from_subtype(normalized_subtype: str) -> str:
    if normalized_subtype in {"代码", "电子卡"}:
        return "code"
    return "physical"


def normalize_app_card_type(value: Any) -> str:
    raw = str(value or "").strip()
    lower = raw.lower()
    if raw in {"实体卡", "卡图", "图"} or lower in {"physical", "phys"}:
        return "physical"
    if raw in {"卡密", "代码", "密"} or lower in {"code", "pin"}:
        return "code"
    return lower if lower in {"physical", "code"} else ""


def normalize_category_status(value: Any) -> str:
    raw = str(value or "active").strip().lower()
    if raw in {"pending", "待确认", "待选择", "manual_review"}:
        return "pending"
    if raw in {"disabled", "停用", "禁用", "inactive"}:
        return "disabled"
    return "active"


def infer_range_type(denom_min: Any, denom_max: Any) -> str:
    if denom_min is None and denom_max is None:
        return "unlimited"
    if denom_min is not None and denom_max is None:
        return "open"
    if denom_min == denom_max:
        return "fixed"
    return "bounded"


def parse_category_range(value: Any) -> tuple[float | None, float | None, str, str]:
    raw = str(value or "").strip()
    if not raw:
        return None, None, "unlimited", ""
    compact = (
        raw.replace(" ", "")
        .replace("，", ",")
        .replace("～", "~")
        .replace("－", "-")
        .replace("—", "-")
        .replace("至", "-")
    )
    if compact.lower() in {"不限", "范围不限", "all"}:
        return None, None, "unlimited", ""
    open_match = re.fullmatch(r"(?:>=|≥)?(\d+(?:\.\d+)?)(?:\+|以上)?", compact)
    if open_match and (">=" in compact or "≥" in compact or compact.endswith("+") or compact.endswith("以上")):
        return _to_float(open_match.group(1)), None, "open", ""
    range_match = re.fullmatch(r"(\d+(?:\.\d+)?)[\-~](\d+(?:\.\d+)?)", compact)
    if range_match:
        return _to_float(range_match.group(1)), _to_float(range_match.group(2)), "bounded", ""
    fixed_match = re.fullmatch(r"\d+(?:\.\d+)?", compact)
    if fixed_match:
        value_float = _to_float(compact)
        return value_float, value_float, "fixed", ""
    return None, None, "unlimited", f"范围无法识别：{raw}"


def parse_multiplier(value: Any) -> float | None:
    raw = str(value or "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*倍(?:数)?", raw)
    return _to_float(match.group(1)) if match else None


def parse_category_subtypes(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return ["卡图", "代码"]
    subtype = parse_single_category_subtype(raw)
    return [subtype] if subtype != "待确认" else ["待确认"]


def parse_single_category_subtype(value: Any) -> str:
    raw = str(value or "").strip()
    lower = raw.lower()
    compact = re.sub(r"[\s_\-/]+", "", lower)
    if not raw:
        return "待确认"
    if raw in CARD_SUBTYPE_OPTIONS:
        return raw
    if any(token in raw for token in ["电子", "电子卡", "电子图"]) or compact in {"ecard", "ecard", "digital"}:
        return "电子卡"
    if any(token in raw for token in ["代码", "卡密", "纯代码", "密"]) or lower in {"code", "pin", "code only"}:
        return "代码"
    if any(token in raw for token in ["竖卡", "竖版卡"]) or lower == "vertical":
        return "竖卡"
    if any(token in raw for token in ["卡图", "实体卡", "物理卡", "图片", "图"]) or lower == "physical":
        return "卡图"
    normalized = normalize_card_subtype(raw)
    if normalized in {"卡图", "代码", "电子卡", "竖卡"}:
        return normalized
    return "待确认"


def _category_view(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    country = data.get("country") or data.get("country_name_en") or ""
    currency = data.get("market_currency") or data.get("currency") or ""
    data["country"] = country
    data["currency"] = currency
    data["market"] = market_value(country, currency)
    data["market_display"] = market_label(country, currency) if country and currency else "待选择"
    data["range_display"] = _range_label(data)
    return data


def _normalize_brand_value(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in standard_brand_names():
        return raw
    normalized = normalize_brand(raw)
    if normalized:
        return normalized
    key = _compact_alias(raw)
    return CATEGORY_BRAND_ALIASES.get(key, "")


def _normalize_market_value(country_value: Any, currency_value: Any = "", market_value_raw: Any = "") -> tuple[str, str]:
    if market_value_raw:
        country, currency = split_market_value(str(market_value_raw))
        if country and currency:
            return country, currency
        country, currency = normalize_market(str(market_value_raw))
        if country and currency:
            return country, currency
        country, currency = _market_from_alias_text(str(market_value_raw))
        if country and currency:
            return country, currency
    country, currency = normalize_market(str(country_value or ""), str(currency_value or ""))
    if country and currency:
        return country, currency
    return _market_from_alias_text(f"{country_value or ''} {currency_value or ''}".strip())


def _market_from_alias_text(value: str) -> tuple[str, str]:
    compact = _compact_market_text(value)
    if not compact:
        return "", ""
    aliases = sorted(CATEGORY_MARKET_ALIASES, key=lambda item: len(_compact_market_text(item[2])), reverse=True)
    for country, currency, alias in aliases:
        alias_key = _compact_market_text(alias)
        if not alias_key:
            continue
        if alias_key == compact or alias_key in compact:
            return country, currency
    return "", ""


def _market_id(conn: sqlite3.Connection, country: str, currency: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM card_markets WHERE country = ? AND currency = ?",
        (country, currency),
    ).fetchone()
    return int(row["id"]) if row else None


def _category_exists(conn: sqlite3.Connection, category_name: str, normalized_subtype: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM app_categories WHERE category_name = ? AND normalized_subtype = ?",
        (category_name, normalized_subtype),
    ).fetchone()
    return bool(row)


def _range_label(row: dict[str, Any]) -> str:
    range_type = (row.get("range_type") or infer_range_type(row.get("denom_min"), row.get("denom_max"))).lower()
    denom_min = row.get("denom_min")
    denom_max = row.get("denom_max")
    if range_type == "unlimited" or (denom_min is None and denom_max is None):
        return "范围不限"
    if range_type == "open" or (denom_min is not None and denom_max is None):
        return f"{decimal_text(denom_min)}以上"
    if range_type == "fixed" or denom_min == denom_max:
        return f"{decimal_text(denom_min)}固定"
    return f"{decimal_text(denom_min)}-{decimal_text(denom_max)}"


def _compact_alias(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value.strip().lower())


def _compact_market_text(value: str) -> str:
    return re.sub(r"[\s_\-/|]+", "", value.strip().lower())


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal_text(value: Any, allow_zero: bool = False) -> str | None:
    if value in (None, ""):
        return None
    decimal = to_decimal(value)
    if decimal is None:
        return None
    if decimal == Decimal("0") and not allow_zero:
        return None
    return decimal_text(decimal)
