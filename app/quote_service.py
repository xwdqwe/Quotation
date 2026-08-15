from __future__ import annotations

import re
import sqlite3
from decimal import Decimal
from typing import Any

from .database import (
    create_quote_batch,
    get_or_create_supplier_group,
    insert_supplier_quote,
    log_operation,
    next_quote_batch_id,
    now_iso,
    reactivate_group_after_new_quotes,
)
from .standards import is_open_ended_range, market_label, normalize_card_subtype_for_brand
from .money import to_decimal


AMBIGUOUS_MARKERS = ("未识别", "待确认", "冲突", "无法", "歧义", "异常")


def quote_match_key(quote: dict[str, Any]) -> tuple[Any, ...]:
    return (
        quote.get("brand") or "",
        quote.get("country") or "",
        quote.get("currency") or "",
        quote.get("frontend_type") or "",
        normalize_card_subtype_for_brand(
            quote.get("brand"),
            quote.get("normalized_card_subtype") or quote.get("raw_card_subtype") or quote.get("subtype"),
            quote.get("frontend_type"),
        ),
        quote.get("raw_card_subtype") or quote.get("subtype") or "",
        _number_or_none(quote.get("denom_min")),
        _number_or_none(quote.get("denom_max")),
        _number_or_none(quote.get("multiplier")),
        quote.get("processing_method") or "",
    )


def analyze_quote_rows(
    conn: sqlite3.Connection,
    supplier_group: str,
    quotes: list[dict[str, Any]],
) -> dict[str, Any]:
    conflicts = _conflicting_keys(quotes)
    analyses = []
    counts = {
        "confirmable_count": 0,
        "manual_count": 0,
        "new_count": 0,
        "update_count": 0,
        "price_up_count": 0,
        "price_down_count": 0,
    }
    for index, quote in enumerate(quotes):
        normalized = normalize_card_subtype_for_brand(
            quote.get("brand"),
            quote.get("normalized_card_subtype") or quote.get("raw_card_subtype") or quote.get("subtype"),
            quote.get("frontend_type"),
        )
        quote["normalized_card_subtype"] = normalized
        raw = quote.get("raw_card_subtype") or quote.get("subtype") or ""
        quote["raw_card_subtype"] = raw
        reasons = _basic_review_reasons(quote)
        key = quote_match_key(quote)
        if key in conflicts:
            reasons.append("同一个匹配 key 存在冲突报价")
        previous = _latest_group_quote(conn, supplier_group, key)
        change = None
        change_type = "new"
        if previous:
            change_type = "update"
            if previous["supplier_rate"] is not None and quote.get("supplier_rate") is not None:
                change = (to_decimal(quote["supplier_rate"]) or Decimal("0")) - (
                    to_decimal(previous["supplier_rate_text"] or previous["supplier_rate"]) or Decimal("0")
                )
                if change > 0:
                    counts["price_up_count"] += 1
                elif change < 0:
                    counts["price_down_count"] += 1
                previous_rate = to_decimal(previous["supplier_rate_text"] or previous["supplier_rate"]) or Decimal("0")
                if previous_rate and abs(change) / abs(previous_rate) > Decimal("0.10"):
                    reasons.append("异常涨跌超过10%，需要人工确认")
        if change_type == "new":
            counts["new_count"] += 1
        else:
            counts["update_count"] += 1
        safe = not reasons
        counts["confirmable_count" if safe else "manual_count"] += 1
        analyses.append(
            {
                "index": index,
                "safe": safe,
                "reasons": reasons,
                "change_type": change_type,
                "change_amount": change,
                "previous_quote_id": previous["id"] if previous else None,
            }
        )
    return {
        **counts,
        "rows": analyses,
        "estimated_batch_id": next_quote_batch_id(conn),
    }


def analyze_supersede_preview(
    conn: sqlite3.Connection,
    supplier_group: str,
    quotes: list[dict[str, Any]],
    *,
    safe_only: bool = False,
) -> dict[str, Any]:
    analysis = analyze_quote_rows(conn, supplier_group, quotes)
    selected = _selected_quotes_from_analysis(quotes, analysis, safe_only=safe_only)
    scopes: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for quote, _row_analysis in selected:
        if not _quote_participates_in_supersede(quote):
            continue
        key = supersede_scope_key(supplier_group, quote)
        scopes.setdefault(
            key,
            {
                "source_group": key[0],
                "brand": key[1],
                "country": key[2],
                "currency": key[3],
                "market_label": market_label(key[2], key[3]),
                "new_count": 0,
                "supersede_count": 0,
                "warning": False,
                "warning_text": "",
            },
        )["new_count"] += 1

    total_supersede = 0
    for key, item in scopes.items():
        old_count = _count_superseded_scope(conn, key)
        item["supersede_count"] = old_count
        item["warning"] = old_count >= item["new_count"] * 5 and old_count >= 10
        if item["warning"]:
            item["warning_text"] = (
                f"本次仅保存 {item['new_count']} 条新报价，但将覆盖旧报价 {old_count} 条，请确认是否为完整更新。"
            )
        total_supersede += old_count

    return {
        "new_quote_count": len(selected),
        "supersede_quote_count": total_supersede,
        "groups": list(scopes.values()),
        "warnings": [item["warning_text"] for item in scopes.values() if item["warning_text"]],
        "estimated_batch_id": next_quote_batch_id(conn),
        **{key: value for key, value in analysis.items() if key not in {"rows", "estimated_batch_id"}},
    }


def save_quote_batch(
    conn: sqlite3.Connection,
    supplier_group: str,
    quotes: list[dict[str, Any]],
    operator: str = "",
    safe_only: bool = False,
) -> dict[str, Any]:
    analysis = analyze_quote_rows(conn, supplier_group, quotes)
    selected = _selected_quotes_from_analysis(quotes, analysis, safe_only=safe_only)
    if not selected:
        raise ValueError("没有可确认的报价")

    group = get_or_create_supplier_group(conn, supplier_group)
    old_group_status = group["status"]
    batch_id = next_quote_batch_id(conn)
    timestamp = now_iso()
    create_quote_batch(conn, batch_id, group, operator, len(selected))
    superseded_ids = _supersede_old_quotes_by_scope(conn, group, selected, batch_id, timestamp)
    inserted_ids = []
    for quote, row_analysis in selected:
        quote = dict(quote)
        quote["supplier_group"] = group["name"]
        quote["supplier_group_id"] = group["id"]
        quote["quote_batch_id"] = batch_id
        quote["raw_card_subtype"] = quote.get("raw_card_subtype") or quote.get("subtype") or ""
        quote["normalized_card_subtype"] = normalize_card_subtype_for_brand(
            quote.get("brand"),
            quote.get("normalized_card_subtype") or quote["raw_card_subtype"],
            quote.get("frontend_type"),
        )
        quote["subtype"] = quote["raw_card_subtype"]
        if quote.get("status") == "active":
            quote["confirmed_at"] = timestamp
        quote.pop("range_type", None)
        inserted_ids.append(insert_supplier_quote(conn, quote))

    log_operation(
        conn,
        action="confirm_quotes",
        operator=operator,
        reason="一键确认可确认项" if safe_only else "人工确认保存报价",
        affected_quote_count=len(inserted_ids) + len(superseded_ids),
        quote_batch_id=batch_id,
        group=group,
        old_status=group["status"],
        new_status=group["status"],
    )
    reactivated_group = reactivate_group_after_new_quotes(
        conn,
        group,
        operator=operator,
        affected_quote_count=len(inserted_ids),
    )
    return {
        "quote_batch_id": batch_id,
        "saved_count": len(inserted_ids),
        "manual_count": analysis["manual_count"] if safe_only else 0,
        "new_count": sum(1 for _, item in selected if item["change_type"] == "new"),
        "update_count": sum(1 for _, item in selected if item["change_type"] == "update"),
        "price_up_count": sum(1 for _, item in selected if (item["change_amount"] or 0) > 0),
        "price_down_count": sum(1 for _, item in selected if (item["change_amount"] or 0) < 0),
        "inserted_ids": inserted_ids,
        "superseded_ids": superseded_ids,
        "affected_quote_ids": [*inserted_ids, *superseded_ids],
        "group_reactivated": bool(reactivated_group),
        "old_group_status": old_group_status,
        "group_status": (reactivated_group or group)["status"],
        "group_impact_list": (reactivated_group or {}).get("impact_list", []),
    }


def supersede_scope_key(supplier_group: str, quote: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        supplier_group.strip(),
        str(quote.get("brand") or "").strip(),
        str(quote.get("country") or "").strip(),
        str(quote.get("currency") or "").strip().upper(),
    )


def _selected_quotes_from_analysis(
    quotes: list[dict[str, Any]],
    analysis: dict[str, Any],
    *,
    safe_only: bool,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected = []
    for quote, row_analysis in zip(quotes, analysis["rows"]):
        if safe_only and not row_analysis["safe"]:
            continue
        selected.append((quote, row_analysis))
    return selected


def _quote_participates_in_supersede(quote: dict[str, Any]) -> bool:
    return bool(
        quote.get("brand")
        and quote.get("country")
        and quote.get("currency")
        and quote.get("supplier_rate") is not None
        and (quote.get("status") or "active") in {"active", "ask_first", "warning"}
    )


def _count_superseded_scope(conn: sqlite3.Connection, key: tuple[str, str, str, str]) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM supplier_quotes
            WHERE supplier_group = ?
              AND brand = ?
              AND country = ?
              AND currency = ?
              AND status IN ('active', 'ask_first', 'warning')
              AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (*key, now_iso()),
        ).fetchone()[0]
    )


def _supersede_old_quotes_by_scope(
    conn: sqlite3.Connection,
    group: dict[str, Any],
    selected: list[tuple[dict[str, Any], dict[str, Any]]],
    batch_id: str,
    timestamp: str,
) -> list[int]:
    scopes = {
        supersede_scope_key(group["name"], quote)
        for quote, _analysis in selected
        if _quote_participates_in_supersede(quote)
    }
    superseded_ids: list[int] = []
    for key in scopes:
        rows = conn.execute(
            """
            SELECT id
            FROM supplier_quotes
            WHERE supplier_group = ?
              AND brand = ?
              AND country = ?
              AND currency = ?
              AND status IN ('active', 'ask_first', 'warning')
              AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (*key, timestamp),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if not ids:
            continue
        placeholders = ", ".join("?" for _ in ids)
        conn.execute(
            f"""
            UPDATE supplier_quotes
            SET status = 'superseded',
                superseded_by_batch_id = ?,
                superseded_at = ?,
                superseded_reason = ?,
                updated_at = ?
            WHERE id IN ({placeholders})
            """,
            [batch_id, timestamp, "新报价覆盖", timestamp, *ids],
        )
        superseded_ids.extend(ids)
    return superseded_ids


def _basic_review_reasons(quote: dict[str, Any]) -> list[str]:
    reasons = []
    if not quote.get("brand"):
        reasons.append("品牌待选择")
    if not quote.get("country") or not quote.get("currency"):
        reasons.append("地区/币种待确认")
    if quote.get("frontend_type") not in {"physical", "code"}:
        reasons.append("前台类型待确认")
    if not quote.get("raw_card_subtype") or quote.get("normalized_card_subtype") == "待确认":
        reasons.append("卡细分待确认")
    if (quote.get("denom_min") is None) != (quote.get("denom_max") is None):
        source_text = " ".join(
            str(quote.get(key) or "") for key in ("source_line", "source_text", "parse_note")
        )
        if not is_open_ended_range(
            quote.get("denom_min"),
            quote.get("denom_max"),
            source_text,
            range_type=str(quote.get("range_type") or ""),
        ):
            reasons.append("面额范围不完整")
    if quote.get("status") == "active" and quote.get("supplier_rate") is None:
        reasons.append("价格解析不确定")
    if not quote.get("processing_method"):
        reasons.append("处理方式待确认")
    if quote.get("status") != "active":
        reasons.append("报价状态不是正常")
    if float(quote.get("confidence") or 0) < 0.8:
        reasons.append("解析置信度低于0.8")
    parse_note = str(quote.get("parse_note") or "")
    if any(marker in parse_note for marker in AMBIGUOUS_MARKERS):
        reasons.append("报价文字存在解析歧义")
    source_line = str(quote.get("source_line") or quote.get("source_text") or "")
    if re.search(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?", source_line):
        if quote.get("denom_min") != quote.get("denom_max"):
            reasons.append("固定面值列表被错误识别为范围")
    return list(dict.fromkeys(reasons))


def _conflicting_keys(quotes: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    rates_by_key: dict[tuple[Any, ...], set[Decimal]] = {}
    for quote in quotes:
        if quote.get("supplier_rate") is None:
            continue
        rate = to_decimal(quote["supplier_rate"])
        if rate is not None:
            rates_by_key.setdefault(quote_match_key(quote), set()).add(rate)
    return {key for key, rates in rates_by_key.items() if len(rates) > 1}


def _latest_group_quote(
    conn: sqlite3.Connection,
    supplier_group: str,
    key: tuple[Any, ...],
) -> sqlite3.Row | None:
    clauses, params = _key_clauses(key)
    return conn.execute(
        f"""
        SELECT * FROM supplier_quotes
        WHERE supplier_group = ? AND {' AND '.join(clauses)}
        ORDER BY id DESC LIMIT 1
        """,
        [supplier_group, *params],
    ).fetchone()


def _supersede_previous_active_quote(
    conn: sqlite3.Connection,
    supplier_group_id: int,
    key: tuple[Any, ...],
    timestamp: str,
) -> None:
    clauses, params = _key_clauses(key)
    conn.execute(
        f"""
        UPDATE supplier_quotes
        SET status = 'superseded', updated_at = ?
        WHERE supplier_group_id = ? AND status = 'active' AND {' AND '.join(clauses)}
        """,
        [timestamp, supplier_group_id, *params],
    )


def _key_clauses(key: tuple[Any, ...]) -> tuple[list[str], list[Any]]:
    columns = [
        "brand",
        "country",
        "currency",
        "frontend_type",
        "normalized_card_subtype",
        "raw_card_subtype",
        "denom_min",
        "denom_max",
        "multiplier",
        "processing_method",
    ]
    clauses = []
    params: list[Any] = []
    for column, value in zip(columns, key):
        if value is None:
            clauses.append(f"{column} IS NULL")
        else:
            clauses.append(f"{column} = ?")
            params.append(value)
    return clauses, params


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
