from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any

from .database import now_iso
from .money import decimal_text, to_decimal
from .parsing import (
    method_label,
    standardize_brand,
    standardize_country_currency,
)
from .standards import market_label, market_value, normalize_card_subtype_for_brand, split_market_value


METHOD_FEEDBACK = {
    "fast_card": "快卡，约1-2分钟",
    "fast_process": "快刷，约5-20分钟",
    "slow_process": "慢刷，慢反馈",
}

GROUP_STATUS_LABELS = {
    "normal": "正常",
    "paused": "暂停",
    "needs_refresh": "待刷新",
    "disabled": "停用",
}

def normalize_match_form(form: dict[str, Any]) -> dict[str, Any]:
    brand = standardize_brand(form.get("brand", ""))
    country, currency = split_market_value(form.get("market", ""))
    if not country or not currency:
        country, currency = standardize_country_currency(form.get("country", ""), form.get("currency", ""))
    subtype_value = str(form.get("normalized_subtype") or form.get("normalized_card_subtype") or "").strip()
    normalized_subtype = ""
    if subtype_value not in {"", "不限", "any"}:
        normalized_subtype = normalize_card_subtype_for_brand(brand, subtype_value)
    denomination = _to_float(form.get("denomination") if form.get("denomination") not in (None, "") else form.get("amount"))

    return {
        "order_no": (form.get("order_no") or "").strip(),
        "brand": brand,
        "country": country,
        "currency": currency,
        "market": market_value(country, currency),
        "normalized_card_subtype": normalized_subtype,
        "subtype": normalized_subtype,
        "denomination": denomination,
        "amount": denomination,
    }


def find_matches(conn: sqlite3.Connection, query: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if not query.get("brand"):
        errors.append("请选择品牌")
    if not query.get("country") or not query.get("currency"):
        errors.append("请选择地区/币种")
    if query.get("denomination") is None and query.get("amount") is None:
        errors.append("请填写面额")
    if errors:
        return {"matches": [], "errors": errors}

    matches = _query_quotes(conn, query)
    for index, quote in enumerate(matches, start=1):
        quote["rank"] = index
    return {"matches": matches, "errors": []}


def log_match(conn: sqlite3.Connection, query: dict[str, Any], selected_quote_id: int | None) -> None:
    conn.execute(
        """
        INSERT INTO shipment_match_logs (
            order_no, brand, country, currency, frontend_type, subtype,
            amount, multiplier, selected_quote_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            query.get("order_no"),
            query.get("brand"),
            query.get("country"),
            query.get("currency"),
            query.get("frontend_type"),
            query.get("normalized_card_subtype"),
            query.get("amount"),
            query.get("multiplier"),
            selected_quote_id,
            now_iso(),
        ),
    )


def quote_to_view(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    raw_subtype = data.get("raw_card_subtype") or data.get("subtype") or ""
    data["raw_card_subtype"] = raw_subtype
    data["normalized_card_subtype"] = normalize_card_subtype_for_brand(
        data.get("brand"),
        data.get("normalized_card_subtype") or raw_subtype,
        data.get("frontend_type"),
    )
    data["supplier_rate"] = data.get("supplier_rate_text") or decimal_text(data.get("supplier_rate"))
    data["processing_label"] = method_label(data.get("processing_method"))
    data["feedback"] = data.get("feedback_note") or METHOD_FEEDBACK.get(data.get("processing_method"), "")
    data["group_status_label"] = GROUP_STATUS_LABELS.get(data.get("group_status"), data.get("group_status") or "")
    data["source_group"] = data.get("supplier_group") or ""
    data["original_subtype"] = raw_subtype
    data["market_label"] = market_label(data.get("country"), data.get("currency"))
    return data


def _query_quotes(conn: sqlite3.Connection, query: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = [
        "q.brand = ?",
        "q.country = ?",
        "q.currency = ?",
        "q.status = 'active'",
        "q.supplier_rate IS NOT NULL",
        "q.deleted_at IS NULL",
        "(q.expires_at IS NULL OR q.expires_at > ?)",
        "COALESCE(g.status, 'normal') = 'normal'",
    ]
    params: list[Any] = [
        query.get("brand"),
        query.get("country"),
        query.get("currency"),
        now_iso(),
    ]

    amount = query.get("denomination") if query.get("denomination") is not None else query.get("amount")
    if amount is not None:
        clauses.append(
            "((q.denom_min IS NULL AND q.denom_max IS NULL) "
            "OR (q.denom_min IS NOT NULL AND q.denom_min <= ? "
            "AND (q.denom_max IS NULL OR q.denom_max >= ?)))"
        )
        params.extend([amount, amount])

    normalized_subtype = query.get("normalized_card_subtype") or ""
    if normalized_subtype and normalized_subtype != "不限":
        clauses.append("q.normalized_card_subtype = ?")
        params.append(normalized_subtype)

    rows = conn.execute(
        f"""
        SELECT q.*, COALESCE(g.status, 'normal') AS group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE {' AND '.join(clauses)}
        ORDER BY q.supplier_rate DESC, q.updated_at DESC, q.supplier_group ASC
        """,
        params,
    ).fetchall()
    views = [quote_to_view(row) for row in rows if _matches_quote_multiplier(amount, row["multiplier"])]
    views.sort(key=lambda row: str(row.get("supplier_group") or ""))
    views.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    views.sort(key=lambda row: to_decimal(row.get("supplier_rate")) or Decimal("0"), reverse=True)
    return views


def _matches_quote_multiplier(denomination: float | None, multiplier: Any) -> bool:
    if denomination is None or multiplier in (None, "", "-"):
        return True
    amount_value = to_decimal(denomination)
    multiplier_value = to_decimal(multiplier)
    if amount_value is None or multiplier_value in (None, Decimal("0")):
        return True
    return amount_value % multiplier_value == 0


def _latest_per_group(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    latest: dict[Any, sqlite3.Row] = {}
    for row in rows:
        group_key = row["supplier_group_id"] or row["supplier_group"]
        if group_key not in latest:
            latest[group_key] = row
    return list(latest.values())


def _excluded_group_quotes(conn: sqlite3.Connection, query: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = [
        "q.brand = ?",
        "q.country = ?",
        "q.currency = ?",
        "q.frontend_type = ?",
        "q.status = 'active'",
        "q.supplier_rate IS NOT NULL",
        "COALESCE(g.status, 'normal') IN ('paused', 'needs_refresh', 'disabled')",
    ]
    params: list[Any] = [
        query.get("brand"),
        query.get("country"),
        query.get("currency"),
        query.get("frontend_type"),
    ]
    _append_subtype_filter(clauses, params, query)
    if query.get("amount") is not None:
        clauses.append(
            "((q.denom_min IS NULL AND q.denom_max IS NULL) "
            "OR (q.denom_min IS NOT NULL AND q.denom_min <= ? "
            "AND (q.denom_max IS NULL OR q.denom_max >= ?)))"
        )
        params.extend([query["amount"], query["amount"]])
    if query.get("multiplier") is not None:
        clauses.append("q.multiplier = ?")
        params.append(query["multiplier"])
    if query.get("processing_method") != "any":
        clauses.append("q.processing_method = ?")
        params.append(query["processing_method"])
    rows = conn.execute(
        f"""
        SELECT q.*, g.status AS group_status
        FROM supplier_quotes q
        JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE {' AND '.join(clauses)}
        ORDER BY q.id DESC
        """,
        params,
    ).fetchall()
    views = [quote_to_view(row) for row in _latest_per_group(rows)]
    return sorted(views, key=lambda row: -(to_decimal(row.get("supplier_rate")) or Decimal("0")))


def _paused_quote_matches(conn: sqlite3.Connection, query: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = [
        "q.brand = ?",
        "q.country = ?",
        "q.currency = ?",
        "q.frontend_type = ?",
        "q.status = 'paused'",
        "q.supplier_rate IS NOT NULL",
        "COALESCE(g.status, 'normal') = 'normal'",
    ]
    params: list[Any] = [
        query.get("brand"),
        query.get("country"),
        query.get("currency"),
        query.get("frontend_type"),
    ]
    _append_subtype_filter(clauses, params, query)
    if query.get("amount") is not None:
        clauses.append(
            "((q.denom_min IS NULL AND q.denom_max IS NULL) "
            "OR (q.denom_min IS NOT NULL AND q.denom_min <= ? "
            "AND (q.denom_max IS NULL OR q.denom_max >= ?)))"
        )
        params.extend([query["amount"], query["amount"]])
    if query.get("multiplier") is not None:
        clauses.append("q.multiplier = ?")
        params.append(query["multiplier"])
    if query.get("processing_method") != "any":
        clauses.append("q.processing_method = ?")
        params.append(query["processing_method"])

    rows = conn.execute(
        f"""
        SELECT q.*, COALESCE(g.status, 'normal') AS group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE {' AND '.join(clauses)}
        ORDER BY q.id DESC
        """,
        params,
    ).fetchall()
    views = [quote_to_view(row) for row in _latest_per_group(rows)]
    for view in views:
        view["availability_note"] = "该群报价已暂停，仅供查看，不能出货。"
    return sorted(views, key=lambda row: -(to_decimal(row.get("supplier_rate")) or Decimal("0")))


def _market_decline_risk(conn: sqlite3.Connection, ranking: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not ranking:
        return None
    comparisons = []
    for current in ranking:
        previous = _previous_quote_for_same_key(conn, current)
        if previous and previous["supplier_rate"] is not None:
            comparisons.append(
                {
                    "group": current["supplier_group"],
                    "previous": to_decimal(previous["supplier_rate_text"] or previous["supplier_rate"]),
                    "current": to_decimal(current["supplier_rate"]),
                }
            )
    if not comparisons:
        return None

    previous_highest = max(item["previous"] for item in comparisons)
    current_highest = to_decimal(ranking[0]["supplier_rate"]) or Decimal("0")
    all_declined = len(comparisons) >= 2 and all(item["current"] < item["previous"] for item in comparisons)
    decline_amount = current_highest - previous_highest
    if all_declined and decline_amount < 0:
        return {
            "is_market_decline": True,
            "previous_highest": previous_highest,
            "current_highest": current_highest,
            "decline_amount": decline_amount,
            "action": f"后台报价建议调整为当前激进价 {decimal_text(current_highest)}",
            "backup_second": ranking[1] if len(ranking) > 1 else None,
            "backup_third": ranking[2] if len(ranking) > 2 else None,
        }
    if decline_amount < 0:
        return {
            "is_market_decline": False,
            "previous_highest": previous_highest,
            "current_highest": current_highest,
            "decline_amount": decline_amount,
            "action": "原最高群降价，但仍有其他群可承接，建议切换出货群。",
            "backup_second": ranking[1] if len(ranking) > 1 else None,
            "backup_third": ranking[2] if len(ranking) > 2 else None,
        }
    return None


def _previous_quote_for_same_key(conn: sqlite3.Connection, current: dict[str, Any]) -> sqlite3.Row | None:
    clauses = [
        "id < ?",
        "supplier_group_id = ?",
        "brand = ?",
        "country = ?",
        "currency = ?",
        "frontend_type = ?",
        "normalized_card_subtype = ?",
        "raw_card_subtype = ?",
        "processing_method = ?",
    ]
    params: list[Any] = [
        current["id"],
        current["supplier_group_id"],
        current["brand"],
        current["country"],
        current["currency"],
        current["frontend_type"],
        current["normalized_card_subtype"],
        current["raw_card_subtype"],
        current["processing_method"],
    ]
    for column in ("multiplier", "denom_min", "denom_max"):
        value = current.get(column)
        if value is None:
            clauses.append(f"{column} IS NULL")
        else:
            clauses.append(f"{column} = ?")
            params.append(value)
    return conn.execute(
        f"SELECT * FROM supplier_quotes WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT 1",
        params,
    ).fetchone()


def _append_subtype_filter(clauses: list[str], params: list[Any], query: dict[str, Any]) -> None:
    raw_subtype = query.get("raw_card_subtype")
    if raw_subtype:
        clauses.append("q.raw_card_subtype = ?")
        params.append(raw_subtype)
        return
    normalized = query.get("normalized_card_subtype")
    if normalized == "卡图" and query.get("brand") != "Apple":
        clauses.append("(q.normalized_card_subtype = ? OR q.normalized_card_subtype = '竖卡')")
    else:
        clauses.append("q.normalized_card_subtype = ?")
    params.append(normalized)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
