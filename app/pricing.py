from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any

from .database import now_iso
from .money import decimal_text, to_decimal
from .standards import market_label, normalize_card_subtype_for_brand


PENDING_STATUS = "pending"
ACTIONABLE_LEGACY_STATUSES = {"first_confirm", "update_needed", "no_available_quote"}
CONFIRMABLE_STATUSES = {PENDING_STATUS}


def recalculate_app_prices(
    conn: sqlite3.Connection,
    affected_quote_ids: list[int] | None = None,
    affected_batch_id: str | None = None,
) -> None:
    if affected_quote_ids is not None:
        if not affected_quote_ids:
            return
        keys = _keys_from_quote_ids(conn, affected_quote_ids)
        _delete_records_for_keys(conn, keys)
    else:
        conn.execute("DELETE FROM app_price_records")
        keys = _all_current_keys(conn)

    for key in keys:
        record = build_dimension_suggestion(conn, key, affected_batch_id=affected_batch_id)
        if record:
            _insert_app_price_record(conn, record)
            _persist_app_price_suggestion(conn, record)


def build_dimension_suggestion(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
    affected_batch_id: str | None = None,
) -> dict[str, Any] | None:
    brand, country, currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    market_id = _market_id(conn, country, currency)
    market_display = market_label(country, currency)
    confirmed = _confirmed_price_for_key(conn, key)
    ranking = rank_supplier_quotes(conn, key)
    top = ranking[0] if ranking else None
    second = ranking[1] if len(ranking) > 1 else None
    third = ranking[2] if len(ranking) > 2 else None
    confirmed_price = to_decimal(confirmed["confirmed_price"]) if confirmed else None

    if top:
        suggested = to_decimal(top["supplier_rate"]) or Decimal("0")
        display_confirmed_price = confirmed_price if confirmed_price is not None else Decimal("0")
        change = suggested - display_confirmed_price
        if confirmed_price is None:
            legacy_status = "first_confirm"
            status = "pending"
            reason = (
                "首次确认：该报价维度此前未确认过管理后台价，当前按 0 对比；"
                f"当前最高报价为 {decimal_text(suggested)}，来源群 {top['supplier_group']}，"
                "建议客服确认是否同步到 APP 管理后台。"
            )
        elif suggested == confirmed_price:
            legacy_status = "no_change"
            status = "auto_closed_no_change"
            reason = "无变化：当前最高报价与管理后台价一致。"
        elif suggested > confirmed_price:
            legacy_status = "update_needed"
            status = "pending"
            reason = (
                f"建议上调：当前最高报价 {decimal_text(suggested)}，"
                f"高于管理后台价 {decimal_text(confirmed_price)}，建议上调。"
            )
        else:
            legacy_status = "update_needed"
            status = "pending"
            reason = (
                f"建议下调：当前最高报价 {decimal_text(suggested)}，"
                f"低于管理后台价 {decimal_text(confirmed_price)}，建议下调。"
            )
        return _record_payload(
            key,
            market_id,
            market_display,
            status,
            legacy_status,
            reason,
            suggested,
            confirmed_price,
            change,
            top,
            second,
            third,
            affected_batch_id,
        )

    if confirmed is None:
        status = "auto_closed_no_change"
        legacy_status = "no_change"
        suggested = Decimal("0")
        change = Decimal("0")
        reason = "无变化：当前没有可用供应商报价，且该维度未确认过管理后台价。"
        return _record_payload(
            key,
            market_id,
            market_display,
            status,
            legacy_status,
            reason,
            suggested,
            None,
            change,
            None,
            None,
            None,
            affected_batch_id,
        )

    confirmed_price = to_decimal(confirmed["confirmed_price"])
    if confirmed_price == Decimal("0"):
        legacy_status = "no_change"
        status = "auto_closed_no_change"
        suggested = Decimal("0")
        change = Decimal("0")
        reason = "无变化：管理后台价为 0，当前也没有可用供应商报价。"
    else:
        legacy_status = "no_available_quote"
        status = "pending"
        suggested = Decimal("0")
        change = suggested - confirmed_price if confirmed_price is not None else None
        reason = (
            f"无可用报价：此前管理后台价为 {decimal_text(confirmed_price)}，"
            "但当前该维度没有可用供应商报价，建议人工确认是否填 0 或暂停收卡。"
        )
    return _record_payload(
        key,
        market_id,
        market_display,
        status,
        legacy_status,
        reason,
        suggested,
        confirmed_price,
        change,
        None,
        None,
        None,
        affected_batch_id,
    )

def rank_supplier_quotes(conn: sqlite3.Connection, key: tuple[Any, ...]) -> list[dict[str, Any]]:
    brand, country, currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    clauses = [
        "q.brand = ?",
        "q.country = ?",
        "q.currency = ?",
        "q.frontend_type = ?",
        "q.normalized_card_subtype = ?",
        "q.status = 'active'",
        "q.deleted_at IS NULL",
        "q.supplier_rate IS NOT NULL",
        "CAST(q.supplier_rate AS REAL) > 0",
        "(q.expires_at IS NULL OR q.expires_at > ?)",
        "COALESCE(g.status, 'normal') = 'normal'",
    ]
    params: list[Any] = [brand, country, currency, frontend_type, normalized_subtype, now_iso()]
    _append_nullable_clause(clauses, params, "q.denom_min", denom_min)
    _append_nullable_clause(clauses, params, "q.denom_max", denom_max)
    _append_nullable_clause(clauses, params, "q.multiplier", multiplier)
    rows = conn.execute(
        f"""
        SELECT q.*, COALESCE(g.status, 'normal') AS supplier_group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE {' AND '.join(clauses)}
        ORDER BY q.updated_at DESC, q.id DESC
        """,
        params,
    ).fetchall()

    latest_by_group: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        group_key = str(item.get("supplier_group_id") or item.get("supplier_group") or item["id"])
        if group_key in latest_by_group:
            continue
        latest_by_group[group_key] = _quote_rank_item(item)

    ranked = sorted(latest_by_group.values(), key=lambda item: item["supplier_group"] or "")
    ranked = sorted(ranked, key=lambda item: item["updated_at"] or "", reverse=True)
    ranked = sorted(ranked, key=lambda item: to_decimal(item["supplier_rate"]) or Decimal("0"), reverse=True)
    for rank, item in enumerate(ranked[:3], start=1):
        item["rank"] = rank
    return ranked[:3]


def list_app_prices(
    conn: sqlite3.Connection,
    tab: str = "needs",
    affected_batch_id: str | None = None,
) -> list[sqlite3.Row]:
    where = "WHERE 1 = 1"
    params: list[Any] = []
    if tab == "no_change":
        where += " AND status = 'auto_closed_no_change'"
    elif tab != "all":
        where += " AND status = 'pending'"
    return conn.execute(
        f"""
        SELECT
            id,
            NULL AS app_category_id,
            NULL AS category_name,
            suggestion_key,
            batch_id AS affected_quote_batch_id,
            brand,
            market_id,
            market_label,
            country,
            currency,
            frontend_type,
            normalized_subtype AS normalized_card_subtype,
            denom_min,
            denom_max,
            range_type,
            range_label,
            multiplier,
            suggested_price AS suggested_backend_rate,
            admin_price AS recorded_backend_rate,
            admin_price_is_confirmed,
            change_amount,
            highest_quote_id,
            highest_source_group AS highest_supplier_group,
            highest_rate AS highest_supplier_rate,
            second_quote_id,
            second_source_group AS second_supplier_group,
            second_rate AS second_supplier_rate,
            third_quote_id,
            third_source_group AS third_supplier_group,
            third_rate AS third_supplier_rate,
            status,
            reason,
            reason_detail,
            resolved_at,
            resolved_by_operator,
            resolution_note,
            superseded_by_suggestion_id,
            created_at,
            updated_at
        FROM app_price_suggestions
        {where}
        ORDER BY
          CASE status
            WHEN 'pending' THEN 1
            WHEN 'auto_closed_no_change' THEN 2
            WHEN 'synced_to_admin' THEN 3
            WHEN 'filled_zero' THEN 4
            WHEN 'ignored' THEN 5
            WHEN 'superseded' THEN 6
            ELSE 9
          END,
          updated_at DESC,
          brand,
          country,
          normalized_subtype
        """,
        params,
    ).fetchall()


def confirm_app_price(conn: sqlite3.Connection, record_id: int, operator: str = "", action: str = "confirm_update") -> None:
    record = conn.execute("SELECT * FROM app_price_suggestions WHERE id = ?", (record_id,)).fetchone()
    if not record:
        return
    timestamp = now_iso()
    key = _record_key(record)
    old_price = to_decimal(record["admin_price"])
    suggested = to_decimal(record["suggested_price"])
    if action == "confirm_zero":
        new_price = Decimal("0")
    else:
        new_price = suggested if suggested is not None else Decimal("0")
    _upsert_confirmed_price(conn, key, record, new_price, operator, timestamp)
    _log_confirmed_price(conn, key, old_price, new_price, suggested, action, operator, record["reason"], timestamp)
    status = "filled_zero" if action == "confirm_zero" else "synced_to_admin"
    note = "已在管理后台填0" if action == "confirm_zero" else "已同步到管理后台"
    conn.execute(
        """
        UPDATE app_price_suggestions
        SET admin_price = ?,
            admin_price_is_confirmed = 1,
            change_amount = 0,
            status = ?,
            resolved_at = ?,
            resolved_by_operator = ?,
            resolution_note = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            decimal_text(new_price),
            status,
            timestamp,
            operator,
            note,
            timestamp,
            record_id,
        ),
    )


def defer_app_price(conn: sqlite3.Connection, record_id: int, operator: str = "", reason: str = "暂不处理") -> None:
    record = conn.execute("SELECT * FROM app_price_suggestions WHERE id = ?", (record_id,)).fetchone()
    if not record:
        return
    timestamp = now_iso()
    key = _record_key(record)
    _log_confirmed_price(
        conn,
        key,
        to_decimal(record["admin_price"]),
        to_decimal(record["admin_price"]),
        to_decimal(record["suggested_price"]),
        "defer",
        operator,
        reason,
        timestamp,
    )
    conn.execute(
        """
        UPDATE app_price_suggestions
        SET status = 'ignored',
            resolved_at = ?,
            resolved_by_operator = ?,
            resolution_note = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (timestamp, operator, f"客服标记暂不处理：{reason}", timestamp, record_id),
    )


def bulk_confirm_app_prices(
    conn: sqlite3.Connection,
    tab: str = "needs",
    operator: str = "",
    affected_batch_id: str | None = None,
) -> int:
    if tab not in {"needs", "all"}:
        return 0
    where = "WHERE status = 'pending'"
    params: list[Any] = []
    rows = conn.execute(
        f"""
        SELECT id, status
        FROM app_price_suggestions
        {where}
        """,
        params,
    ).fetchall()
    for row in rows:
        confirm_app_price(conn, row["id"], operator=operator, action="confirm_update")
    return len(rows)



def infer_range_type(denom_min: Any, denom_max: Any) -> str:
    if denom_min is None and denom_max is None:
        return "unlimited"
    if denom_min is not None and denom_max is None:
        return "open"
    if denom_min == denom_max:
        return "fixed"
    return "bounded"


def _all_current_keys(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    keys = []
    rows = conn.execute(
        """
        SELECT q.*
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE q.status = 'active'
          AND q.deleted_at IS NULL
          AND q.supplier_rate IS NOT NULL
          AND CAST(q.supplier_rate AS REAL) > 0
          AND (q.expires_at IS NULL OR q.expires_at > ?)
          AND COALESCE(g.status, 'normal') = 'normal'
        """,
        (now_iso(),),
    ).fetchall()
    keys.extend(_key_from_quote(row) for row in rows)
    confirmed_rows = conn.execute(
        """
        SELECT cp.*, m.country, m.currency
        FROM confirmed_app_prices cp
        LEFT JOIN card_markets m ON m.id = cp.market_id
        """
    ).fetchall()
    for row in confirmed_rows:
        if row["country"] and row["currency"]:
            keys.append(
                (
                    row["brand"],
                    row["country"],
                    row["currency"],
                    row["frontend_type"] or ("code" if row["normalized_subtype"] in {"代码", "电子卡"} else "physical"),
                    row["normalized_subtype"],
                    row["denom_min"],
                    row["denom_max"],
                    row["range_type"],
                    row["multiplier"],
                )
            )
    return list(dict.fromkeys(keys))


def _keys_from_quote_ids(conn: sqlite3.Connection, quote_ids: list[int]) -> list[tuple[Any, ...]]:
    if not quote_ids:
        return []
    placeholders = ", ".join("?" for _ in quote_ids)
    rows = conn.execute(
        f"SELECT * FROM supplier_quotes WHERE id IN ({placeholders})",
        quote_ids,
    ).fetchall()
    return list(dict.fromkeys(_key_from_quote(row) for row in rows))


def _key_from_quote(row: sqlite3.Row | dict[str, Any]) -> tuple[Any, ...]:
    quote = dict(row)
    subtype = normalize_card_subtype_for_brand(
        quote.get("brand"),
        quote.get("normalized_card_subtype") or quote.get("raw_card_subtype") or quote.get("subtype"),
        quote.get("frontend_type"),
    )
    return (
        quote.get("brand"),
        quote.get("country"),
        quote.get("currency"),
        quote.get("frontend_type") or ("code" if subtype in {"代码", "电子卡"} else "physical"),
        subtype,
        _number_or_none(quote.get("denom_min")),
        _number_or_none(quote.get("denom_max")),
        infer_range_type(_number_or_none(quote.get("denom_min")), _number_or_none(quote.get("denom_max"))),
        _number_or_none(quote.get("multiplier")),
    )


def _record_key(record: sqlite3.Row | dict[str, Any]) -> tuple[Any, ...]:
    row = dict(record)
    return (
        row.get("brand"),
        row.get("country"),
        row.get("currency"),
        row.get("frontend_type") or ("code" if (row.get("normalized_subtype") or row.get("normalized_card_subtype")) in {"代码", "电子卡"} else "physical"),
        row.get("normalized_subtype") or row.get("normalized_card_subtype"),
        row.get("denom_min"),
        row.get("denom_max"),
        row.get("range_type") or infer_range_type(row.get("denom_min"), row.get("denom_max")),
        row.get("multiplier"),
    )


def _record_payload(
    key: tuple[Any, ...],
    market_id: int | None,
    market_display: str,
    status: str,
    legacy_status: str,
    reason: str,
    suggested: Decimal,
    confirmed: Decimal | None,
    change: Decimal | None,
    top: dict[str, Any] | None,
    second: dict[str, Any] | None,
    third: dict[str, Any] | None,
    affected_batch_id: str | None,
) -> dict[str, Any]:
    brand, country, currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    suggestion_key = _suggestion_key(key, market_id)
    reason_detail = _reason_detail(
        suggestion_key=suggestion_key,
        batch_id=affected_batch_id,
        market_display=market_display,
        reason=reason,
        admin_price=confirmed,
        suggested=suggested,
        change=change,
        top=top,
        second=second,
        third=third,
    )
    return {
        "suggestion_key": suggestion_key,
        "market_id": market_id,
        "market_label": market_display,
        "range_type": range_type,
        "range_label": _range_label(denom_min, denom_max),
        "brand": brand,
        "country": country,
        "currency": currency,
        "frontend_type": frontend_type,
        "normalized_card_subtype": normalized_subtype,
        "normalized_subtype": normalized_subtype,
        "multiplier": multiplier,
        "denom_min": denom_min,
        "denom_max": denom_max,
        "suggested_backend_rate": decimal_text(suggested),
        "recorded_backend_rate": decimal_text(confirmed) if confirmed is not None else None,
        "admin_price": decimal_text(confirmed) if confirmed is not None else None,
        "admin_price_is_confirmed": 1 if confirmed is not None else 0,
        "change_amount": decimal_text(change) if change is not None else None,
        "highest_quote_id": top["id"] if top else None,
        "highest_supplier_group": top["supplier_group"] if top else None,
        "highest_supplier_rate": top["supplier_rate"] if top else None,
        "second_quote_id": second["id"] if second else None,
        "second_supplier_group": second["supplier_group"] if second else None,
        "second_supplier_rate": second["supplier_rate"] if second else None,
        "third_quote_id": third["id"] if third else None,
        "third_supplier_group": third["supplier_group"] if third else None,
        "third_supplier_rate": third["supplier_rate"] if third else None,
        "affected_quote_batch_id": affected_batch_id,
        "batch_id": affected_batch_id,
        "status": status,
        "legacy_status": legacy_status,
        "reason": reason,
        "reason_detail": reason_detail,
    }


def _insert_app_price_record(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO app_price_records (
            market_id, market_label, range_type,
            brand, country, currency, frontend_type, normalized_card_subtype,
            multiplier, denom_min, denom_max, suggested_backend_rate,
            recorded_backend_rate, change_amount, highest_quote_id,
            highest_supplier_group, highest_supplier_rate, second_quote_id,
            second_supplier_group, second_supplier_rate, third_quote_id,
            third_supplier_group, third_supplier_rate, affected_quote_batch_id,
            status, reason, last_confirmed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            payload["market_id"],
            payload["market_label"],
            payload["range_type"],
            payload["brand"],
            payload["country"],
            payload["currency"],
            payload["frontend_type"],
            payload["normalized_card_subtype"],
            payload["multiplier"],
            payload["denom_min"],
            payload["denom_max"],
            payload["suggested_backend_rate"],
            payload["recorded_backend_rate"],
            payload["change_amount"],
            payload["highest_quote_id"],
            payload["highest_supplier_group"],
            payload["highest_supplier_rate"],
            payload["second_quote_id"],
            payload["second_supplier_group"],
            payload["second_supplier_rate"],
            payload["third_quote_id"],
            payload["third_supplier_group"],
            payload["third_supplier_rate"],
            payload["affected_quote_batch_id"],
            payload["legacy_status"],
            payload["reason"],
            timestamp,
            timestamp,
        ),
    )


def _delete_records_for_keys(conn: sqlite3.Connection, keys: list[tuple[Any, ...]]) -> None:
    for key in keys:
        clauses, params = _key_clauses(key, table_alias="")
        conn.execute(f"DELETE FROM app_price_records WHERE {' AND '.join(clauses)}", params)


def _persist_app_price_suggestion(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    timestamp = now_iso()
    status = payload["status"]
    suggestion_key = payload["suggestion_key"]
    if status == "auto_closed_no_change":
        conn.execute(
            """
            UPDATE app_price_suggestions
            SET status = 'auto_closed_no_change',
                resolved_at = ?,
                resolved_by_operator = '',
                resolution_note = ?,
                reason = ?,
                reason_detail = ?,
                updated_at = ?
            WHERE suggestion_key = ? AND status = 'pending'
            """,
            (
                timestamp,
                "当前管理后台价与建议价一致，自动关闭",
                payload["reason"],
                payload["reason_detail"],
                timestamp,
                suggestion_key,
            ),
        )
        return

    cursor = conn.execute(
        """
        INSERT INTO app_price_suggestions (
            suggestion_key, batch_id, brand, market_id, market_label,
            country, currency, frontend_type, normalized_subtype,
            denom_min, denom_max, range_type, range_label, multiplier,
            admin_price, admin_price_is_confirmed, highest_rate,
            second_rate, third_rate, suggested_price, change_amount,
            highest_quote_id, second_quote_id, third_quote_id,
            highest_source_group, second_source_group, third_source_group,
            reason, reason_detail, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (
            payload["suggestion_key"],
            payload["batch_id"],
            payload["brand"],
            payload["market_id"],
            payload["market_label"],
            payload["country"],
            payload["currency"],
            payload["frontend_type"],
            payload["normalized_subtype"],
            payload["denom_min"],
            payload["denom_max"],
            payload["range_type"],
            payload["range_label"],
            payload["multiplier"],
            payload["admin_price"],
            payload["admin_price_is_confirmed"],
            payload["highest_supplier_rate"],
            payload["second_supplier_rate"],
            payload["third_supplier_rate"],
            payload["suggested_backend_rate"],
            payload["change_amount"],
            payload["highest_quote_id"],
            payload["second_quote_id"],
            payload["third_quote_id"],
            payload["highest_supplier_group"],
            payload["second_supplier_group"],
            payload["third_supplier_group"],
            payload["reason"],
            payload["reason_detail"],
            timestamp,
            timestamp,
        ),
    )
    new_id = int(cursor.lastrowid)
    conn.execute(
        """
        UPDATE app_price_suggestions
        SET status = 'superseded',
            superseded_by_suggestion_id = ?,
            resolved_at = ?,
            resolved_by_operator = '',
            resolution_note = '已被新建议覆盖',
            updated_at = ?
        WHERE suggestion_key = ?
          AND status = 'pending'
          AND id <> ?
        """,
        (new_id, timestamp, timestamp, suggestion_key, new_id),
    )


def _existing_records_for_keys(conn: sqlite3.Connection, keys: list[tuple[Any, ...]]) -> dict[tuple[Any, ...], sqlite3.Row]:
    records = {}
    for key in keys:
        clauses, params = _key_clauses(key, table_alias="")
        row = conn.execute(
            f"""
            SELECT *
            FROM app_price_records
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if row:
            records[key] = row
    return records


def _apply_previous_ranking_context(record: dict[str, Any], previous: sqlite3.Row | None) -> None:
    if not previous or record.get("status") != "no_change":
        return
    old_group = previous["highest_supplier_group"]
    new_group = record.get("highest_supplier_group")
    if not old_group or not new_group or old_group == new_group:
        return
    old_rate = to_decimal(previous["highest_supplier_rate"])
    new_rate = to_decimal(record.get("highest_supplier_rate"))
    if old_rate is None or new_rate is None:
        return
    record["status"] = "update_needed"
    record["change_amount"] = decimal_text((to_decimal(record.get("suggested_backend_rate")) or Decimal("0")) - (to_decimal(record.get("recorded_backend_rate")) or Decimal("0")))
    record["reason"] = (
        f"最高出货来源变化：此前 {old_group} {decimal_text(old_rate)}，"
        f"当前 {new_group} {decimal_text(new_rate)}；管理后台价与本次建议价一致，"
        "请确认出货群切换是否已知。"
    )


def _confirmed_price_for_key(conn: sqlite3.Connection, key: tuple[Any, ...]) -> sqlite3.Row | None:
    market_id = _market_id(conn, key[1], key[2])
    clauses, params = _confirmed_key_clauses(key, market_id)
    return conn.execute(
        f"""
        SELECT *
        FROM confirmed_app_prices
        WHERE {' AND '.join(clauses)}
        ORDER BY id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()


def _upsert_confirmed_price(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
    record: sqlite3.Row | dict[str, Any],
    new_price: Decimal,
    operator: str,
    timestamp: str,
) -> None:
    market_id = _market_id(conn, key[1], key[2])
    existing = _confirmed_price_for_key(conn, key)
    if existing:
        conn.execute(
            """
            UPDATE confirmed_app_prices
            SET confirmed_price = ?,
                frontend_type = ?,
                confirmed_source_group = ?,
                confirmed_quote_id = ?,
                confirmed_by_operator = ?,
                confirmed_at = ?,
                source_type = 'manual_confirm',
                updated_at = ?
            WHERE id = ?
            """,
            (
                decimal_text(new_price),
                key[3],
                _record_value(record, "highest_supplier_group", "highest_source_group"),
                _record_value(record, "highest_quote_id"),
                operator,
                timestamp,
                timestamp,
                existing["id"],
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO confirmed_app_prices (
            brand, market_id, market_label, frontend_type, normalized_subtype,
            denom_min, denom_max, range_type, multiplier, confirmed_price,
            confirmed_source_group, confirmed_quote_id, confirmed_by_operator,
            confirmed_at, source_type, note, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual_confirm', '', ?, ?)
        """,
        (
            key[0],
            market_id,
            market_label(key[1], key[2]),
            key[3],
            key[4],
            key[5],
            key[6],
            key[7],
            key[8],
            decimal_text(new_price),
            _record_value(record, "highest_supplier_group", "highest_source_group"),
            _record_value(record, "highest_quote_id"),
            operator,
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def _log_confirmed_price(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
    old_price: Decimal | None,
    new_price: Decimal | None,
    suggested_price: Decimal | None,
    action: str,
    operator: str,
    reason: str,
    timestamp: str,
) -> None:
    conn.execute(
        """
        INSERT INTO confirmed_price_logs (
            brand, market_id, normalized_subtype, denom_min, denom_max,
            range_type, multiplier, old_price, new_price, suggested_price,
            action, operator, reason, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key[0],
            _market_id(conn, key[1], key[2]),
            key[4],
            key[5],
            key[6],
            key[7],
            key[8],
            decimal_text(old_price) if old_price is not None else None,
            decimal_text(new_price) if new_price is not None else None,
            decimal_text(suggested_price) if suggested_price is not None else None,
            action,
            operator,
            reason,
            timestamp,
        ),
    )


def _key_clauses(key: tuple[Any, ...], table_alias: str = "q.") -> tuple[list[str], list[Any]]:
    brand, country, currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    prefix = table_alias
    clauses = [
        f"{prefix}brand = ?",
        f"{prefix}country = ?",
        f"{prefix}currency = ?",
        f"{prefix}frontend_type = ?",
        f"{prefix}normalized_card_subtype = ?",
    ]
    params: list[Any] = [brand, country, currency, frontend_type, normalized_subtype]
    _append_nullable_clause(clauses, params, f"{prefix}denom_min", denom_min)
    _append_nullable_clause(clauses, params, f"{prefix}denom_max", denom_max)
    clauses.append(f"{prefix}range_type = ?")
    params.append(range_type)
    _append_nullable_clause(clauses, params, f"{prefix}multiplier", multiplier)
    return clauses, params


def _confirmed_key_clauses(key: tuple[Any, ...], market_id: int | None) -> tuple[list[str], list[Any]]:
    brand, _country, _currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    clauses = ["brand = ?", "(frontend_type = ? OR frontend_type IS NULL)", "normalized_subtype = ?", "range_type = ?"]
    params: list[Any] = [brand, frontend_type, normalized_subtype, range_type]
    _append_nullable_clause(clauses, params, "market_id", market_id)
    _append_nullable_clause(clauses, params, "denom_min", denom_min)
    _append_nullable_clause(clauses, params, "denom_max", denom_max)
    _append_nullable_clause(clauses, params, "multiplier", multiplier)
    return clauses, params


def _append_nullable_clause(clauses: list[str], params: list[Any], column: str, value: Any) -> None:
    if value is None:
        clauses.append(f"{column} IS NULL")
    else:
        clauses.append(f"{column} = ?")
        params.append(value)


def _quote_rank_item(item: dict[str, Any]) -> dict[str, Any]:
    rate = item.get("supplier_rate_text") or decimal_text(item.get("supplier_rate"))
    return {
        "id": item["id"],
        "supplier_group": item.get("supplier_group") or "",
        "supplier_rate": rate,
        "processing_method": item.get("processing_method") or "",
        "feedback_note": item.get("feedback_note") or "",
        "requirements": item.get("requirements") or "",
        "updated_at": item.get("updated_at") or "",
        "received_at": item.get("received_at") or "",
    }


def _record_value(record: sqlite3.Row | dict[str, Any], *names: str) -> Any:
    data = dict(record)
    for name in names:
        if name in data:
            return data[name]
    return None


def _suggestion_key(key: tuple[Any, ...], market_id: int | None) -> str:
    brand, _country, _currency, frontend_type, normalized_subtype, denom_min, denom_max, range_type, multiplier = key
    parts = [
        brand,
        market_id if market_id is not None else "",
        frontend_type,
        normalized_subtype,
        "" if denom_min is None else decimal_text(denom_min),
        "" if denom_max is None else decimal_text(denom_max),
        range_type or infer_range_type(denom_min, denom_max),
        "" if multiplier is None else decimal_text(multiplier),
    ]
    return "|".join(str(part) for part in parts)


def _range_label(denom_min: Any, denom_max: Any) -> str:
    if denom_min is None and denom_max is None:
        return "范围不限"
    if denom_min is not None and denom_max is None:
        return f"{decimal_text(denom_min)}以上"
    if denom_min == denom_max:
        return f"{decimal_text(denom_min)}固定面值"
    return f"{decimal_text(denom_min)}-{decimal_text(denom_max)}"


def _reason_detail(
    *,
    suggestion_key: str,
    batch_id: str | None,
    market_display: str,
    reason: str,
    admin_price: Decimal | None,
    suggested: Decimal,
    change: Decimal | None,
    top: dict[str, Any] | None,
    second: dict[str, Any] | None,
    third: dict[str, Any] | None,
) -> str:
    lines = [
        f"触发原因：{reason}",
        f"管理后台价：{decimal_text(admin_price) if admin_price is not None else '0（未确认）'}",
        f"本次建议价：{decimal_text(suggested)}",
        f"变化：{decimal_text(change) if change is not None else '-'}",
        f"地区/币种：{market_display}",
        f"批次号：{batch_id or '-'}",
        f"suggestion_key：{suggestion_key}",
    ]
    rank_rows = [
        ("当前最高报价", top),
        ("第二报价", second),
        ("第三报价", third),
    ]
    for label, item in rank_rows:
        if item:
            lines.append(
                f"{label}：{item.get('supplier_rate') or '-'} / 来源 {item.get('supplier_group') or '-'} / 报价ID {item.get('id') or '-'}"
            )
        else:
            lines.append(f"{label}：-")
    return "\n".join(lines)


def _market_id(conn: sqlite3.Connection, country: str | None, currency: str | None) -> int | None:
    if not country or not currency:
        return None
    row = conn.execute(
        "SELECT id FROM card_markets WHERE country = ? AND currency = ?",
        (country, currency),
    ).fetchone()
    return int(row["id"]) if row else None


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
