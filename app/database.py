from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .money import decimal_text, to_decimal
from .standards import (
    BRAND_SEEDS,
    MARKET_SEEDS,
    market_label,
    market_value,
    normalize_card_subtype_for_brand,
    split_market_value,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "cardsabi.sqlite3"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def add_hours_iso(hours: float) -> str:
    return (datetime.now() + timedelta(hours=hours)).replace(microsecond=0).isoformat(sep=" ")


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed: bool = True, db_path: Path | str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        create_tables(conn)
        if seed:
            seed_sample_data(conn)


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS supplier_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_group_id INTEGER,
            supplier_group TEXT NOT NULL,
            quote_batch_id TEXT,
            source_text TEXT NOT NULL,
            source_line TEXT,
            line_no INTEGER,
            parse_note TEXT,
            brand TEXT,
            country TEXT,
            currency TEXT,
            frontend_type TEXT,
            subtype TEXT,
            raw_card_subtype TEXT,
            normalized_card_subtype TEXT,
            processing_method TEXT,
            feedback_note TEXT,
            multiplier REAL,
            denom_min REAL,
            denom_max REAL,
            supplier_rate REAL,
            supplier_rate_text TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            requirements TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            received_at TEXT NOT NULL,
            expires_at TEXT,
            confirmed_at TEXT,
            deleted_at TEXT,
            paused_at TEXT,
            paused_by_operator TEXT,
            pause_reason TEXT,
            resumed_at TEXT,
            resumed_by_operator TEXT,
            superseded_by_batch_id TEXT,
            superseded_at TEXT,
            superseded_reason TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_supplier_quotes_lookup
            ON supplier_quotes (brand, country, currency, frontend_type, subtype, status);

        CREATE INDEX IF NOT EXISTS idx_supplier_quotes_rate
            ON supplier_quotes (supplier_rate, received_at);

        CREATE TABLE IF NOT EXISTS card_brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brand_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            alias TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES card_brands(id)
        );

        CREATE INDEX IF NOT EXISTS idx_brand_aliases_brand_id
            ON brand_aliases (brand_id);

        CREATE TABLE IF NOT EXISTS card_markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(country, currency)
        );

        CREATE TABLE IF NOT EXISTS app_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL,
            brand TEXT NOT NULL,
            market_id INTEGER,
            market_label TEXT,
            country_name_cn TEXT,
            country_name_en TEXT,
            currency TEXT NOT NULL,
            app_card_type TEXT NOT NULL,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL DEFAULT 'unlimited',
            multiplier REAL,
            current_app_price REAL,
            discount REAL,
            speed_type TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            source_note TEXT,
            confirmed_at TEXT,
            confirmed_by_operator TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_app_categories_lookup
            ON app_categories (status, brand, market_id, app_card_type, normalized_subtype);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_categories_unique_subtype
            ON app_categories (category_name, normalized_subtype);

        CREATE TABLE IF NOT EXISTS supplier_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'normal',
            status_changed_at TEXT NOT NULL,
            refresh_required_after_quote_id INTEGER,
            paused_at TEXT,
            paused_by_operator TEXT,
            pause_reason TEXT,
            restored_at TEXT,
            restored_by_operator TEXT,
            confirmed_at TEXT,
            confirmed_by_operator TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_supplier_groups_status
            ON supplier_groups (status, name);

        CREATE TABLE IF NOT EXISTS quote_batches (
            quote_batch_id TEXT PRIMARY KEY,
            supplier_group_id INTEGER,
            supplier_group TEXT NOT NULL,
            operator TEXT,
            quote_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            revoke_reason TEXT,
            FOREIGN KEY (supplier_group_id) REFERENCES supplier_groups(id)
        );

        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_batch_id TEXT,
            group_id INTEGER,
            group_name TEXT,
            old_status TEXT,
            new_status TEXT,
            action TEXT NOT NULL,
            operator TEXT,
            reason TEXT,
            details TEXT,
            affected_quote_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES supplier_groups(id)
        );

        CREATE INDEX IF NOT EXISTS idx_operation_logs_group
            ON operation_logs (group_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_operation_logs_batch
            ON operation_logs (quote_batch_id, created_at);

        CREATE TABLE IF NOT EXISTS quote_status_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_group TEXT NOT NULL,
            brand TEXT NOT NULL,
            action TEXT NOT NULL,
            affected_count INTEGER NOT NULL DEFAULT 0,
            operator TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_quote_status_logs_lookup
            ON quote_status_logs (supplier_group, brand, created_at);

        CREATE TABLE IF NOT EXISTS quote_bulk_action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            mode TEXT NOT NULL,
            filters_json TEXT,
            quote_ids_json TEXT,
            affected_quote_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            operator TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_quote_bulk_action_logs_created
            ON quote_bulk_action_logs (created_at, action);

        CREATE TABLE IF NOT EXISTS app_price_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_category_id INTEGER,
            category_name TEXT,
            market_id INTEGER,
            market_label TEXT,
            range_type TEXT,
            brand TEXT NOT NULL,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            frontend_type TEXT NOT NULL,
            normalized_card_subtype TEXT,
            multiplier REAL,
            denom_min REAL,
            denom_max REAL,
            suggested_backend_rate REAL,
            recorded_backend_rate REAL,
            change_amount REAL,
            highest_quote_id INTEGER,
            highest_supplier_group TEXT,
            highest_supplier_rate REAL,
            second_quote_id INTEGER,
            second_supplier_group TEXT,
            second_supplier_rate REAL,
            third_quote_id INTEGER,
            third_supplier_group TEXT,
            third_supplier_rate REAL,
            affected_quote_batch_id TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            last_confirmed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (app_category_id) REFERENCES app_categories(id)
        );

        CREATE INDEX IF NOT EXISTS idx_app_price_records_status
            ON app_price_records (status, brand, country, currency, frontend_type);

        CREATE TABLE IF NOT EXISTS app_price_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_key TEXT NOT NULL,
            batch_id TEXT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            market_label TEXT,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            frontend_type TEXT NOT NULL,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL DEFAULT 'unlimited',
            range_label TEXT,
            multiplier REAL,
            admin_price REAL,
            admin_price_is_confirmed INTEGER NOT NULL DEFAULT 0,
            highest_rate REAL,
            second_rate REAL,
            third_rate REAL,
            suggested_price REAL,
            change_amount REAL,
            highest_quote_id INTEGER,
            second_quote_id INTEGER,
            third_quote_id INTEGER,
            highest_source_group TEXT,
            second_source_group TEXT,
            third_source_group TEXT,
            reason TEXT,
            reason_detail TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by_operator TEXT,
            resolution_note TEXT,
            superseded_by_suggestion_id INTEGER,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_app_price_suggestions_status
            ON app_price_suggestions (status, brand, market_id, updated_at);

        CREATE INDEX IF NOT EXISTS idx_app_price_suggestions_key
            ON app_price_suggestions (suggestion_key, status, updated_at);

        CREATE TABLE IF NOT EXISTS app_category_update_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_category_id INTEGER,
            category_name TEXT NOT NULL,
            old_price REAL,
            new_price REAL,
            suggested_price REAL,
            action TEXT NOT NULL,
            operator TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (app_category_id) REFERENCES app_categories(id)
        );

        CREATE TABLE IF NOT EXISTS confirmed_app_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            market_label TEXT,
            frontend_type TEXT,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL DEFAULT 'unlimited',
            multiplier REAL,
            confirmed_price REAL,
            confirmed_source_group TEXT,
            confirmed_quote_id INTEGER,
            confirmed_by_operator TEXT,
            confirmed_at TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual_confirm',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_confirmed_app_prices_key
            ON confirmed_app_prices (
                brand, market_id, frontend_type, normalized_subtype,
                denom_min, denom_max, range_type, multiplier
            );

        CREATE TABLE IF NOT EXISTS confirmed_price_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL,
            multiplier REAL,
            old_price REAL,
            new_price REAL,
            suggested_price REAL,
            action TEXT NOT NULL,
            operator TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_confirmed_price_logs_lookup
            ON confirmed_price_logs (brand, market_id, normalized_subtype, created_at);

        CREATE TABLE IF NOT EXISTS shipment_match_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT,
            brand TEXT,
            country TEXT,
            currency TEXT,
            frontend_type TEXT,
            subtype TEXT,
            amount REAL,
            multiplier REAL,
            selected_quote_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (selected_quote_id) REFERENCES supplier_quotes(id)
        );
        """
    )
    ensure_supplier_quote_columns(conn)
    ensure_supplier_group_columns(conn)
    ensure_operation_log_columns(conn)
    ensure_app_category_columns(conn)
    ensure_app_price_columns(conn)
    ensure_app_price_suggestion_columns(conn)
    seed_standard_catalogs(conn)


def ensure_supplier_quote_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(supplier_quotes)").fetchall()}
    migrations = {
        "source_line": "ALTER TABLE supplier_quotes ADD COLUMN source_line TEXT",
        "line_no": "ALTER TABLE supplier_quotes ADD COLUMN line_no INTEGER",
        "parse_note": "ALTER TABLE supplier_quotes ADD COLUMN parse_note TEXT",
        "feedback_note": "ALTER TABLE supplier_quotes ADD COLUMN feedback_note TEXT",
        "supplier_group_id": "ALTER TABLE supplier_quotes ADD COLUMN supplier_group_id INTEGER",
        "quote_batch_id": "ALTER TABLE supplier_quotes ADD COLUMN quote_batch_id TEXT",
        "raw_card_subtype": "ALTER TABLE supplier_quotes ADD COLUMN raw_card_subtype TEXT",
        "normalized_card_subtype": "ALTER TABLE supplier_quotes ADD COLUMN normalized_card_subtype TEXT",
        "confirmed_at": "ALTER TABLE supplier_quotes ADD COLUMN confirmed_at TEXT",
        "deleted_at": "ALTER TABLE supplier_quotes ADD COLUMN deleted_at TEXT",
        "paused_at": "ALTER TABLE supplier_quotes ADD COLUMN paused_at TEXT",
        "paused_by_operator": "ALTER TABLE supplier_quotes ADD COLUMN paused_by_operator TEXT",
        "pause_reason": "ALTER TABLE supplier_quotes ADD COLUMN pause_reason TEXT",
        "resumed_at": "ALTER TABLE supplier_quotes ADD COLUMN resumed_at TEXT",
        "resumed_by_operator": "ALTER TABLE supplier_quotes ADD COLUMN resumed_by_operator TEXT",
        "superseded_by_batch_id": "ALTER TABLE supplier_quotes ADD COLUMN superseded_by_batch_id TEXT",
        "superseded_at": "ALTER TABLE supplier_quotes ADD COLUMN superseded_at TEXT",
        "superseded_reason": "ALTER TABLE supplier_quotes ADD COLUMN superseded_reason TEXT",
        "supplier_rate_text": "ALTER TABLE supplier_quotes ADD COLUMN supplier_rate_text TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_supplier_quotes_batch ON supplier_quotes (quote_batch_id, status)"
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_supplier_quotes_normalized_lookup
        ON supplier_quotes (
            brand, country, currency, frontend_type,
            normalized_card_subtype, processing_method, multiplier, status
        )
        """
    )
    conn.execute("UPDATE supplier_quotes SET source_line = source_text WHERE source_line IS NULL")
    conn.execute(
        """
        UPDATE supplier_quotes
        SET supplier_rate_text = CAST(supplier_rate AS TEXT)
        WHERE supplier_rate IS NOT NULL AND COALESCE(supplier_rate_text, '') = ''
        """
    )
    conn.execute("UPDATE supplier_quotes SET subtype = '卡图' WHERE subtype IN ('图', '图卡')")
    conn.execute("UPDATE supplier_quotes SET subtype = '代码/卡密' WHERE subtype IN ('密', '密卡', '卡密', '代码', '纯代码')")
    conn.execute("UPDATE supplier_quotes SET subtype = '电子卡' WHERE subtype = '电子图'")
    conn.execute("UPDATE supplier_quotes SET raw_card_subtype = '电子卡' WHERE raw_card_subtype = '电子图'")
    conn.execute(
        """
        UPDATE supplier_quotes
        SET frontend_type = 'code', normalized_card_subtype = '电子卡'
        WHERE subtype = '电子卡' OR raw_card_subtype = '电子卡'
        """
    )
    conn.execute("UPDATE supplier_quotes SET multiplier = 5 WHERE subtype = '散卡' AND multiplier IS NULL")
    conn.execute("UPDATE supplier_quotes SET multiplier = 50 WHERE subtype = '整卡' AND multiplier IS NULL")
    conn.execute("UPDATE supplier_quotes SET subtype = '卡图' WHERE subtype IN ('散卡', '整卡')")
    conn.execute("UPDATE supplier_quotes SET raw_card_subtype = subtype WHERE COALESCE(raw_card_subtype, '') = ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quote_bulk_action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            mode TEXT NOT NULL,
            filters_json TEXT,
            quote_ids_json TEXT,
            affected_quote_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            operator TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_quote_bulk_action_logs_created
        ON quote_bulk_action_logs (created_at, action)
        """
    )
    rows = conn.execute(
        """
        SELECT id, brand, frontend_type, raw_card_subtype, subtype, normalized_card_subtype
        FROM supplier_quotes
        """
    ).fetchall()
    for row in rows:
        raw_subtype = row["raw_card_subtype"] or row["subtype"] or ""
        current = row["normalized_card_subtype"] or ""
        needs_backfill = current in {"", "待确认"}
        needs_non_apple_vertical_fix = row["brand"] != "Apple" and current == "竖卡"
        if needs_backfill or needs_non_apple_vertical_fix:
            normalized = normalize_card_subtype_for_brand(
                row["brand"],
                raw_subtype or current,
                row["frontend_type"],
            )
            conn.execute(
                "UPDATE supplier_quotes SET normalized_card_subtype = ? WHERE id = ?",
                (normalized, row["id"]),
            )
    backfill_supplier_groups(conn)


def ensure_app_price_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(app_price_records)").fetchall()}
    migrations = {
        "app_category_id": "ALTER TABLE app_price_records ADD COLUMN app_category_id INTEGER",
        "category_name": "ALTER TABLE app_price_records ADD COLUMN category_name TEXT",
        "market_id": "ALTER TABLE app_price_records ADD COLUMN market_id INTEGER",
        "market_label": "ALTER TABLE app_price_records ADD COLUMN market_label TEXT",
        "range_type": "ALTER TABLE app_price_records ADD COLUMN range_type TEXT",
        "highest_quote_id": "ALTER TABLE app_price_records ADD COLUMN highest_quote_id INTEGER",
        "highest_supplier_group": "ALTER TABLE app_price_records ADD COLUMN highest_supplier_group TEXT",
        "highest_supplier_rate": "ALTER TABLE app_price_records ADD COLUMN highest_supplier_rate REAL",
        "second_quote_id": "ALTER TABLE app_price_records ADD COLUMN second_quote_id INTEGER",
        "second_supplier_group": "ALTER TABLE app_price_records ADD COLUMN second_supplier_group TEXT",
        "second_supplier_rate": "ALTER TABLE app_price_records ADD COLUMN second_supplier_rate REAL",
        "third_quote_id": "ALTER TABLE app_price_records ADD COLUMN third_quote_id INTEGER",
        "third_supplier_group": "ALTER TABLE app_price_records ADD COLUMN third_supplier_group TEXT",
        "third_supplier_rate": "ALTER TABLE app_price_records ADD COLUMN third_supplier_rate REAL",
        "affected_quote_batch_id": "ALTER TABLE app_price_records ADD COLUMN affected_quote_batch_id TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)
    if "normalized_card_subtype" not in existing:
        conn.execute("ALTER TABLE app_price_records ADD COLUMN normalized_card_subtype TEXT")
    conn.execute(
        """
        UPDATE app_price_records
        SET normalized_card_subtype = CASE
            WHEN frontend_type = 'code' THEN '代码'
            WHEN frontend_type = 'physical' THEN '卡图'
            ELSE '待确认'
        END
        WHERE COALESCE(normalized_card_subtype, '') = ''
        """
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS confirmed_app_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            market_label TEXT,
            frontend_type TEXT,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL DEFAULT 'unlimited',
            multiplier REAL,
            confirmed_price REAL,
            confirmed_source_group TEXT,
            confirmed_quote_id INTEGER,
            confirmed_by_operator TEXT,
            confirmed_at TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual_confirm',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_confirmed_app_prices_key
            ON confirmed_app_prices (
                brand, market_id, frontend_type, normalized_subtype,
                denom_min, denom_max, range_type, multiplier
            );

        CREATE TABLE IF NOT EXISTS confirmed_price_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL,
            multiplier REAL,
            old_price REAL,
            new_price REAL,
            suggested_price REAL,
            action TEXT NOT NULL,
            operator TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        );

        CREATE INDEX IF NOT EXISTS idx_confirmed_price_logs_lookup
            ON confirmed_price_logs (brand, market_id, normalized_subtype, created_at);
        """
    )
    confirmed_columns = {row["name"] for row in conn.execute("PRAGMA table_info(confirmed_app_prices)").fetchall()}
    if "frontend_type" not in confirmed_columns:
        conn.execute("ALTER TABLE confirmed_app_prices ADD COLUMN frontend_type TEXT")
    if "source_type" not in confirmed_columns:
        conn.execute("ALTER TABLE confirmed_app_prices ADD COLUMN source_type TEXT NOT NULL DEFAULT 'manual_confirm'")
    conn.execute(
        """
        UPDATE confirmed_app_prices
        SET frontend_type = CASE
            WHEN normalized_subtype IN ('代码', '电子卡') THEN 'code'
            ELSE 'physical'
        END
        WHERE COALESCE(frontend_type, '') = ''
        """
    )
    conn.execute("DROP INDEX IF EXISTS idx_confirmed_app_prices_key")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_confirmed_app_prices_key
        ON confirmed_app_prices (
            brand, market_id, frontend_type, normalized_subtype,
            denom_min, denom_max, range_type, multiplier
        )
        """
    )
    conn.execute("DELETE FROM confirmed_app_prices WHERE source_type IN ('app_category', 'app_categories')")
    conn.execute(
        """
        DELETE FROM app_price_records
        WHERE app_category_id IS NOT NULL
           OR COALESCE(category_name, '') <> ''
           OR status = 'no_cover_quote'
        """
    )


def ensure_app_price_suggestion_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_price_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suggestion_key TEXT NOT NULL,
            batch_id TEXT,
            brand TEXT NOT NULL,
            market_id INTEGER,
            market_label TEXT,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            frontend_type TEXT NOT NULL,
            normalized_subtype TEXT NOT NULL,
            denom_min REAL,
            denom_max REAL,
            range_type TEXT NOT NULL DEFAULT 'unlimited',
            range_label TEXT,
            multiplier REAL,
            admin_price REAL,
            admin_price_is_confirmed INTEGER NOT NULL DEFAULT 0,
            highest_rate REAL,
            second_rate REAL,
            third_rate REAL,
            suggested_price REAL,
            change_amount REAL,
            highest_quote_id INTEGER,
            second_quote_id INTEGER,
            third_quote_id INTEGER,
            highest_source_group TEXT,
            second_source_group TEXT,
            third_source_group TEXT,
            reason TEXT,
            reason_detail TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by_operator TEXT,
            resolution_note TEXT,
            superseded_by_suggestion_id INTEGER,
            FOREIGN KEY (market_id) REFERENCES card_markets(id)
        )
        """
    )
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(app_price_suggestions)").fetchall()}
    migrations = {
        "suggestion_key": "ALTER TABLE app_price_suggestions ADD COLUMN suggestion_key TEXT",
        "batch_id": "ALTER TABLE app_price_suggestions ADD COLUMN batch_id TEXT",
        "brand": "ALTER TABLE app_price_suggestions ADD COLUMN brand TEXT",
        "market_id": "ALTER TABLE app_price_suggestions ADD COLUMN market_id INTEGER",
        "market_label": "ALTER TABLE app_price_suggestions ADD COLUMN market_label TEXT",
        "country": "ALTER TABLE app_price_suggestions ADD COLUMN country TEXT",
        "currency": "ALTER TABLE app_price_suggestions ADD COLUMN currency TEXT",
        "frontend_type": "ALTER TABLE app_price_suggestions ADD COLUMN frontend_type TEXT",
        "normalized_subtype": "ALTER TABLE app_price_suggestions ADD COLUMN normalized_subtype TEXT",
        "denom_min": "ALTER TABLE app_price_suggestions ADD COLUMN denom_min REAL",
        "denom_max": "ALTER TABLE app_price_suggestions ADD COLUMN denom_max REAL",
        "range_type": "ALTER TABLE app_price_suggestions ADD COLUMN range_type TEXT DEFAULT 'unlimited'",
        "range_label": "ALTER TABLE app_price_suggestions ADD COLUMN range_label TEXT",
        "multiplier": "ALTER TABLE app_price_suggestions ADD COLUMN multiplier REAL",
        "admin_price": "ALTER TABLE app_price_suggestions ADD COLUMN admin_price REAL",
        "admin_price_is_confirmed": "ALTER TABLE app_price_suggestions ADD COLUMN admin_price_is_confirmed INTEGER NOT NULL DEFAULT 0",
        "highest_rate": "ALTER TABLE app_price_suggestions ADD COLUMN highest_rate REAL",
        "second_rate": "ALTER TABLE app_price_suggestions ADD COLUMN second_rate REAL",
        "third_rate": "ALTER TABLE app_price_suggestions ADD COLUMN third_rate REAL",
        "suggested_price": "ALTER TABLE app_price_suggestions ADD COLUMN suggested_price REAL",
        "change_amount": "ALTER TABLE app_price_suggestions ADD COLUMN change_amount REAL",
        "highest_quote_id": "ALTER TABLE app_price_suggestions ADD COLUMN highest_quote_id INTEGER",
        "second_quote_id": "ALTER TABLE app_price_suggestions ADD COLUMN second_quote_id INTEGER",
        "third_quote_id": "ALTER TABLE app_price_suggestions ADD COLUMN third_quote_id INTEGER",
        "highest_source_group": "ALTER TABLE app_price_suggestions ADD COLUMN highest_source_group TEXT",
        "second_source_group": "ALTER TABLE app_price_suggestions ADD COLUMN second_source_group TEXT",
        "third_source_group": "ALTER TABLE app_price_suggestions ADD COLUMN third_source_group TEXT",
        "reason": "ALTER TABLE app_price_suggestions ADD COLUMN reason TEXT",
        "reason_detail": "ALTER TABLE app_price_suggestions ADD COLUMN reason_detail TEXT",
        "status": "ALTER TABLE app_price_suggestions ADD COLUMN status TEXT",
        "created_at": "ALTER TABLE app_price_suggestions ADD COLUMN created_at TEXT",
        "updated_at": "ALTER TABLE app_price_suggestions ADD COLUMN updated_at TEXT",
        "resolved_at": "ALTER TABLE app_price_suggestions ADD COLUMN resolved_at TEXT",
        "resolved_by_operator": "ALTER TABLE app_price_suggestions ADD COLUMN resolved_by_operator TEXT",
        "resolution_note": "ALTER TABLE app_price_suggestions ADD COLUMN resolution_note TEXT",
        "superseded_by_suggestion_id": "ALTER TABLE app_price_suggestions ADD COLUMN superseded_by_suggestion_id INTEGER",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_price_suggestions_status
        ON app_price_suggestions (status, brand, market_id, updated_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_price_suggestions_key
        ON app_price_suggestions (suggestion_key, status, updated_at)
        """
    )
    conn.execute(
        """
        UPDATE app_price_records
        SET normalized_card_subtype = '卡图'
        WHERE brand != 'Apple' AND normalized_card_subtype = '竖卡'
        """
    )


def ensure_app_category_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(app_categories)").fetchall()}
    migrations = {
        "market_id": "ALTER TABLE app_categories ADD COLUMN market_id INTEGER",
        "market_label": "ALTER TABLE app_categories ADD COLUMN market_label TEXT",
        "country_name_cn": "ALTER TABLE app_categories ADD COLUMN country_name_cn TEXT",
        "country_name_en": "ALTER TABLE app_categories ADD COLUMN country_name_en TEXT",
        "currency": "ALTER TABLE app_categories ADD COLUMN currency TEXT",
        "app_card_type": "ALTER TABLE app_categories ADD COLUMN app_card_type TEXT",
        "normalized_subtype": "ALTER TABLE app_categories ADD COLUMN normalized_subtype TEXT",
        "range_type": "ALTER TABLE app_categories ADD COLUMN range_type TEXT DEFAULT 'unlimited'",
        "discount": "ALTER TABLE app_categories ADD COLUMN discount REAL",
        "speed_type": "ALTER TABLE app_categories ADD COLUMN speed_type TEXT",
        "source_note": "ALTER TABLE app_categories ADD COLUMN source_note TEXT",
        "confirmed_at": "ALTER TABLE app_categories ADD COLUMN confirmed_at TEXT",
        "confirmed_by_operator": "ALTER TABLE app_categories ADD COLUMN confirmed_by_operator TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)
    ensure_app_category_unique_key(conn)


def ensure_app_category_unique_key(conn: sqlite3.Connection) -> None:
    single_name_unique = False
    for index in conn.execute("PRAGMA index_list(app_categories)").fetchall():
        if not index["unique"]:
            continue
        columns = [
            row["name"]
            for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
        ]
        if columns == ["category_name"]:
            single_name_unique = True
            break
    if single_name_unique:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_categories_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_name TEXT NOT NULL,
                brand TEXT NOT NULL,
                market_id INTEGER,
                market_label TEXT,
                country_name_cn TEXT,
                country_name_en TEXT,
                currency TEXT NOT NULL,
                app_card_type TEXT NOT NULL,
                normalized_subtype TEXT NOT NULL,
                denom_min REAL,
                denom_max REAL,
                range_type TEXT NOT NULL DEFAULT 'unlimited',
                multiplier REAL,
                current_app_price REAL,
                discount REAL,
                speed_type TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                source_note TEXT,
                confirmed_at TEXT,
                confirmed_by_operator TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (market_id) REFERENCES card_markets(id)
            );

            INSERT OR IGNORE INTO app_categories_new (
                id, category_name, brand, market_id, market_label, country_name_cn,
                country_name_en, currency, app_card_type, normalized_subtype,
                denom_min, denom_max, range_type, multiplier, current_app_price,
                discount, speed_type, status, source_note, confirmed_at,
                confirmed_by_operator, created_at, updated_at
            )
            SELECT
                id, category_name, brand, market_id, market_label, country_name_cn,
                country_name_en, COALESCE(currency, ''), COALESCE(app_card_type, 'physical'),
                COALESCE(normalized_subtype, '卡图'), denom_min, denom_max,
                COALESCE(range_type, 'unlimited'), multiplier, current_app_price,
                discount, speed_type, COALESCE(status, 'active'), source_note,
                confirmed_at, confirmed_by_operator, created_at, updated_at
            FROM app_categories;

            DROP TABLE app_categories;
            ALTER TABLE app_categories_new RENAME TO app_categories;
            """
        )
        conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_categories_lookup
        ON app_categories (status, brand, market_id, app_card_type, normalized_subtype)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_categories_unique_subtype
        ON app_categories (category_name, normalized_subtype)
        """
    )


def ensure_supplier_group_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(supplier_groups)").fetchall()}
    migrations = {
        "refresh_required_after_quote_id": "ALTER TABLE supplier_groups ADD COLUMN refresh_required_after_quote_id INTEGER",
        "paused_at": "ALTER TABLE supplier_groups ADD COLUMN paused_at TEXT",
        "paused_by_operator": "ALTER TABLE supplier_groups ADD COLUMN paused_by_operator TEXT",
        "pause_reason": "ALTER TABLE supplier_groups ADD COLUMN pause_reason TEXT",
        "restored_at": "ALTER TABLE supplier_groups ADD COLUMN restored_at TEXT",
        "restored_by_operator": "ALTER TABLE supplier_groups ADD COLUMN restored_by_operator TEXT",
        "confirmed_at": "ALTER TABLE supplier_groups ADD COLUMN confirmed_at TEXT",
        "confirmed_by_operator": "ALTER TABLE supplier_groups ADD COLUMN confirmed_by_operator TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)
    conn.execute(
        "UPDATE supplier_groups SET status = 'paused' WHERE status NOT IN ('normal', 'paused', 'needs_refresh')"
    )


def ensure_operation_log_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(operation_logs)").fetchall()}
    if "details" not in existing:
        conn.execute("ALTER TABLE operation_logs ADD COLUMN details TEXT")


def insert_supplier_quote(conn: sqlite3.Connection, quote: dict[str, Any]) -> int:
    timestamp = now_iso()
    fields = {
        "supplier_group_id": None,
        "supplier_group": "",
        "quote_batch_id": None,
        "source_text": "",
        "source_line": "",
        "line_no": None,
        "parse_note": "",
        "brand": "",
        "country": "",
        "currency": "",
        "frontend_type": "",
        "subtype": "",
        "raw_card_subtype": "",
        "normalized_card_subtype": "待确认",
        "processing_method": "fast_card",
        "feedback_note": "",
        "multiplier": None,
        "denom_min": None,
        "denom_max": None,
        "supplier_rate": None,
        "supplier_rate_text": None,
        "status": "active",
        "requirements": "",
        "confidence": 0.5,
        "received_at": timestamp,
        "expires_at": add_hours_iso(6),
        "confirmed_at": timestamp,
        "paused_at": None,
        "paused_by_operator": None,
        "pause_reason": None,
        "resumed_at": None,
        "resumed_by_operator": None,
        "superseded_by_batch_id": None,
        "superseded_at": None,
        "superseded_reason": None,
        "created_by": "",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    fields.update(quote)
    if fields["supplier_rate"] is not None:
        exact_rate = fields.get("supplier_rate_text") or decimal_text(fields["supplier_rate"])
        fields["supplier_rate_text"] = exact_rate
        fields["supplier_rate"] = exact_rate
    if not fields["source_line"]:
        fields["source_line"] = fields["source_text"]
    if not fields["raw_card_subtype"]:
        fields["raw_card_subtype"] = fields["subtype"]
    fields["normalized_card_subtype"] = normalize_card_subtype_for_brand(
        fields["brand"],
        fields["normalized_card_subtype"] or fields["raw_card_subtype"],
        fields["frontend_type"],
    )
    if fields["supplier_group"] and not fields["supplier_group_id"]:
        group = get_or_create_supplier_group(conn, str(fields["supplier_group"]))
        fields["supplier_group_id"] = group["id"]
    columns = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cursor = conn.execute(
        f"INSERT INTO supplier_quotes ({columns}) VALUES ({placeholders})",
        list(fields.values()),
    )
    return int(cursor.lastrowid)


def get_or_create_supplier_group(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("来源群/供应商不能为空")
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO supplier_groups (name, status, status_changed_at, created_at, updated_at)
        VALUES (?, 'normal', ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET updated_at = supplier_groups.updated_at
        """,
        (clean_name, timestamp, timestamp, timestamp),
    )
    return dict(conn.execute("SELECT * FROM supplier_groups WHERE name = ?", (clean_name,)).fetchone())


def backfill_supplier_groups(conn: sqlite3.Connection) -> None:
    names = conn.execute(
        "SELECT DISTINCT supplier_group FROM supplier_quotes WHERE COALESCE(supplier_group, '') != ''"
    ).fetchall()
    for row in names:
        group = get_or_create_supplier_group(conn, row["supplier_group"])
        conn.execute(
            "UPDATE supplier_quotes SET supplier_group_id = ? WHERE supplier_group = ? AND supplier_group_id IS NULL",
            (group["id"], row["supplier_group"]),
        )


def next_quote_batch_id(conn: sqlite3.Connection) -> str:
    prefix = f"QB{datetime.now():%Y%m%d}_"
    row = conn.execute(
        "SELECT quote_batch_id FROM quote_batches WHERE quote_batch_id LIKE ? ORDER BY quote_batch_id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    sequence = 1
    if row:
        try:
            sequence = int(str(row["quote_batch_id"]).rsplit("_", 1)[1]) + 1
        except (IndexError, ValueError):
            sequence = 1
    return f"{prefix}{sequence:03d}"


def create_quote_batch(
    conn: sqlite3.Connection,
    quote_batch_id: str,
    group: dict[str, Any],
    operator: str,
    quote_count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO quote_batches (
            quote_batch_id, supplier_group_id, supplier_group, operator,
            quote_count, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'active', ?)
        """,
        (quote_batch_id, group["id"], group["name"], operator, quote_count, now_iso()),
    )


def log_operation(
    conn: sqlite3.Connection,
    action: str,
    operator: str = "",
    reason: str = "",
    details: str | None = None,
    affected_quote_count: int = 0,
    quote_batch_id: str | None = None,
    group: dict[str, Any] | sqlite3.Row | None = None,
    old_status: str | None = None,
    new_status: str | None = None,
) -> int:
    group_data = dict(group) if group is not None else {}
    cursor = conn.execute(
        """
        INSERT INTO operation_logs (
            quote_batch_id, group_id, group_name, old_status, new_status,
            action, operator, reason, details, affected_quote_count, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quote_batch_id,
            group_data.get("id"),
            group_data.get("name"),
            old_status,
            new_status,
            action,
            operator,
            reason,
            details,
            affected_quote_count,
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def revoke_quote_batch(
    conn: sqlite3.Connection,
    quote_batch_id: str,
    operator: str = "",
    reason: str = "",
) -> dict[str, Any]:
    batch = conn.execute("SELECT * FROM quote_batches WHERE quote_batch_id = ?", (quote_batch_id,)).fetchone()
    if not batch:
        raise ValueError("批次不存在")
    group = conn.execute("SELECT * FROM supplier_groups WHERE id = ?", (batch["supplier_group_id"],)).fetchone()
    quote_rows = conn.execute("SELECT id FROM supplier_quotes WHERE quote_batch_id = ?", (quote_batch_id,)).fetchall()
    quote_ids = [row["id"] for row in quote_rows]
    referenced_count = 0
    if quote_ids:
        placeholders = ", ".join("?" for _ in quote_ids)
        referenced_count = conn.execute(
            f"SELECT COUNT(*) FROM shipment_match_logs WHERE selected_quote_id IN ({placeholders})",
            quote_ids,
        ).fetchone()[0]
    timestamp = now_iso()
    cursor = conn.execute(
        "UPDATE supplier_quotes SET status = 'revoked', updated_at = ? WHERE quote_batch_id = ? AND status != 'revoked'",
        (timestamp, quote_batch_id),
    )
    affected = cursor.rowcount
    conn.execute(
        """
        UPDATE quote_batches
        SET status = 'revoked', revoked_at = ?, revoke_reason = ?
        WHERE quote_batch_id = ?
        """,
        (timestamp, reason, quote_batch_id),
    )
    log_operation(
        conn,
        action="revoke_batch",
        operator=operator,
        reason=reason,
        affected_quote_count=affected,
        quote_batch_id=quote_batch_id,
        group=group,
        old_status=batch["status"],
        new_status="revoked",
    )
    return {"affected_quote_count": affected, "referenced_count": referenced_count, "batch": dict(batch)}


def list_supplier_groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT g.*,
               COUNT(q.id) AS quote_count,
               SUM(CASE WHEN q.status = 'active' THEN 1 ELSE 0 END) AS active_quote_count
        FROM supplier_groups g
        LEFT JOIN supplier_quotes q ON q.supplier_group_id = g.id
        GROUP BY g.id
        ORDER BY g.name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def transition_supplier_group(
    conn: sqlite3.Connection,
    group_id: int,
    new_status: str,
    action: str,
    operator: str = "",
    reason: str = "",
) -> dict[str, Any]:
    group = conn.execute("SELECT * FROM supplier_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise ValueError("供应群不存在")
    old_status = group["status"]
    allowed = {
        ("normal", "paused", "pause_group"),
        ("paused", "needs_refresh", "mark_group_needs_refresh"),
        ("needs_refresh", "normal", "restore_group_normal"),
        ("paused", "normal", "confirm_reuse_old_quotes"),
        ("needs_refresh", "normal", "confirm_reuse_old_quotes"),
        ("normal", "disabled", "disable_group"),
        ("paused", "disabled", "disable_group"),
        ("needs_refresh", "disabled", "disable_group"),
    }
    if (old_status, new_status, action) not in allowed:
        raise ValueError(f"不允许从 {old_status} 变更为 {new_status}")
    if action == "restore_group_normal":
        confirmed = conn.execute(
            """
            SELECT COUNT(*)
            FROM supplier_quotes
            WHERE supplier_group_id = ?
              AND status = 'active'
              AND confirmed_at IS NOT NULL
              AND id > COALESCE(?, 0)
            """,
            (group_id, group["refresh_required_after_quote_id"]),
        ).fetchone()[0]
        if not confirmed:
            raise ValueError("该群暂无最新确认报价，不能恢复正常")
    affected = conn.execute(
        "SELECT COUNT(*) FROM supplier_quotes WHERE supplier_group_id = ? AND status NOT IN ('revoked', 'superseded')",
        (group_id,),
    ).fetchone()[0]
    affected_keys = _affected_group_quote_keys(conn, group_id)
    before_impact = _group_impact_snapshot(conn, affected_keys)
    timestamp = now_iso()
    refresh_after_id = group["refresh_required_after_quote_id"]
    if action == "mark_group_needs_refresh":
        refresh_after_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM supplier_quotes WHERE supplier_group_id = ?",
            (group_id,),
        ).fetchone()[0]
    elif action in {"restore_group_normal", "confirm_reuse_old_quotes"}:
        refresh_after_id = None
    paused_at = group["paused_at"]
    paused_by_operator = group["paused_by_operator"]
    pause_reason = group["pause_reason"]
    restored_at = group["restored_at"]
    restored_by_operator = group["restored_by_operator"]
    confirmed_at = group["confirmed_at"]
    confirmed_by_operator = group["confirmed_by_operator"]
    if action == "pause_group":
        paused_at = timestamp
        paused_by_operator = operator
        pause_reason = reason
    elif action == "mark_group_needs_refresh":
        restored_at = timestamp
        restored_by_operator = operator
    elif action in {"restore_group_normal", "confirm_reuse_old_quotes"}:
        restored_at = restored_at or timestamp
        restored_by_operator = restored_by_operator or operator
        confirmed_at = timestamp
        confirmed_by_operator = operator
    conn.execute(
        """
        UPDATE supplier_groups
        SET status = ?,
            status_changed_at = ?,
            refresh_required_after_quote_id = ?,
            paused_at = ?,
            paused_by_operator = ?,
            pause_reason = ?,
            restored_at = ?,
            restored_by_operator = ?,
            confirmed_at = ?,
            confirmed_by_operator = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            new_status,
            timestamp,
            refresh_after_id,
            paused_at,
            paused_by_operator,
            pause_reason,
            restored_at,
            restored_by_operator,
            confirmed_at,
            confirmed_by_operator,
            timestamp,
            group_id,
        ),
    )
    updated = dict(conn.execute("SELECT * FROM supplier_groups WHERE id = ?", (group_id,)).fetchone())
    after_impact = _group_impact_snapshot(conn, affected_keys)
    impact_list = _build_group_impact_list(affected_keys, before_impact, after_impact)
    log_id = log_operation(
        conn,
        action=action,
        operator=operator,
        reason=reason,
        details=json.dumps({"impact_list": impact_list}, ensure_ascii=False),
        affected_quote_count=affected,
        group=updated,
        old_status=old_status,
        new_status=new_status,
    )
    updated["operation_log_id"] = log_id
    updated["impact_list"] = impact_list
    updated["old_status"] = old_status
    return updated


def reactivate_group_after_new_quotes(
    conn: sqlite3.Connection,
    group: dict[str, Any] | sqlite3.Row,
    operator: str = "",
    affected_quote_count: int = 0,
) -> dict[str, Any] | None:
    group_data = dict(group)
    if group_data.get("status") != "needs_refresh":
        return None
    group_id = int(group_data["id"])
    affected_keys = _affected_group_quote_keys(conn, group_id)
    before_impact = _group_impact_snapshot(conn, affected_keys)
    timestamp = now_iso()
    conn.execute(
        """
        UPDATE supplier_groups
        SET status = 'normal',
            status_changed_at = ?,
            refresh_required_after_quote_id = NULL,
            confirmed_at = ?,
            confirmed_by_operator = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (timestamp, timestamp, operator.strip(), timestamp, group_id),
    )
    updated = dict(conn.execute("SELECT * FROM supplier_groups WHERE id = ?", (group_id,)).fetchone())
    after_impact = _group_impact_snapshot(conn, affected_keys)
    impact_list = _build_group_impact_list(affected_keys, before_impact, after_impact)
    log_id = log_operation(
        conn,
        action="restore_group_normal_after_new_quotes",
        operator=operator,
        reason="录入并确认新报价后自动恢复正常",
        details=json.dumps({"impact_list": impact_list}, ensure_ascii=False),
        affected_quote_count=affected_quote_count,
        group=updated,
        old_status="needs_refresh",
        new_status="normal",
    )
    updated["operation_log_id"] = log_id
    updated["impact_list"] = impact_list
    updated["old_status"] = "needs_refresh"
    return updated


def _affected_group_quote_keys(conn: sqlite3.Connection, group_id: int) -> list[tuple[Any, ...]]:
    rows = conn.execute(
        """
        SELECT *
        FROM supplier_quotes
        WHERE supplier_group_id = ?
          AND status = 'active'
          AND supplier_rate IS NOT NULL
          AND COALESCE(brand, '') != ''
          AND COALESCE(country, '') != ''
          AND COALESCE(currency, '') != ''
          AND COALESCE(frontend_type, '') != ''
          AND COALESCE(normalized_card_subtype, '') != ''
          AND deleted_at IS NULL
          AND (expires_at IS NULL OR expires_at >= ?)
        ORDER BY id DESC
        """,
        (group_id, now_iso()),
    ).fetchall()
    keys: list[tuple[Any, ...]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = _app_quote_key(row)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _app_quote_key(row: sqlite3.Row | dict[str, Any]) -> tuple[Any, ...]:
    return (
        _row_get(row, "brand"),
        _row_get(row, "country"),
        _row_get(row, "currency"),
        _row_get(row, "frontend_type"),
        normalize_card_subtype_for_brand(
            _row_get(row, "brand"),
            _row_get(row, "normalized_card_subtype")
            or _row_get(row, "raw_card_subtype")
            or _row_get(row, "subtype"),
            _row_get(row, "frontend_type"),
        ),
        _number_or_none(_row_get(row, "multiplier")),
        _number_or_none(_row_get(row, "denom_min")),
        _number_or_none(_row_get(row, "denom_max")),
    )


def _group_impact_snapshot(
    conn: sqlite3.Connection,
    keys: list[tuple[Any, ...]],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    snapshot: dict[tuple[Any, ...], dict[str, Any]] = {}
    for key in keys:
        full_candidates, partial_candidates = _available_quote_candidates_for_dimension(conn, key)
        snapshot[key] = {
            "top": full_candidates[0] if full_candidates else None,
            "full_candidates": full_candidates,
            "partial_candidates": partial_candidates,
            "app_record": _latest_app_price_record(conn, key),
        }
    return snapshot


def _top_available_quote_for_key(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
) -> dict[str, Any] | None:
    full_candidates, _ = _available_quote_candidates_for_dimension(conn, key)
    return full_candidates[0] if full_candidates else None


def _available_quote_candidates_for_dimension(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    brand, country, currency, expected_frontend_type, expected_subtype, expected_multiplier, expected_min, expected_max = key
    rows = conn.execute(
        """
        SELECT q.*, COALESCE(g.status, 'normal') AS supplier_group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE q.brand = ?
          AND q.country = ?
          AND q.currency = ?
          AND q.status = 'active'
          AND q.supplier_rate IS NOT NULL
          AND CAST(q.supplier_rate AS REAL) > 0
          AND q.deleted_at IS NULL
          AND (q.expires_at IS NULL OR q.expires_at >= ?)
          AND COALESCE(g.status, 'normal') = 'normal'
        ORDER BY q.id DESC
        """,
        (brand, country, currency, now_iso()),
    ).fetchall()

    full_by_group: dict[Any, dict[str, Any]] = {}
    partial_by_group: dict[Any, dict[str, Any]] = {}
    for row in rows:
        group_key = row["supplier_group_id"] or row["supplier_group"]
        normalized_subtype = normalize_card_subtype_for_brand(
            row["brand"],
            row["normalized_card_subtype"] or row["raw_card_subtype"] or row["subtype"],
            row["frontend_type"],
        )
        type_full = row["frontend_type"] == expected_frontend_type and normalized_subtype == expected_subtype
        range_relation = _range_coverage_relation(expected_min, expected_max, row["denom_min"], row["denom_max"])
        multiplier_relation = _multiplier_coverage_relation(expected_multiplier, row["multiplier"])
        candidate = _quote_candidate_payload(row)
        candidate["range_relation"] = range_relation
        candidate["multiplier_relation"] = multiplier_relation
        candidate["type_relation"] = "full" if type_full else "partial"
        candidate["partial_reason"] = _partial_candidate_reason(type_full, range_relation, multiplier_relation)
        if type_full and range_relation == "full" and multiplier_relation == "full":
            if group_key not in full_by_group:
                full_by_group[group_key] = candidate
        elif range_relation in {"full", "partial"} and multiplier_relation in {"full", "partial"}:
            if group_key not in partial_by_group:
                partial_by_group[group_key] = candidate

    full_candidates = _sort_quote_candidates(list(full_by_group.values()))
    partial_candidates = _sort_quote_candidates(
        [candidate for key_value, candidate in partial_by_group.items() if key_value not in full_by_group]
    )
    return full_candidates, partial_candidates


def _quote_candidate_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "quote_id": row["id"],
        "supplier_group": row["supplier_group"],
        "supplier_group_id": row["supplier_group_id"],
        "supplier_rate": row["supplier_rate_text"] or decimal_text(row["supplier_rate"]),
        "received_at": row["received_at"],
        "updated_at": row["updated_at"],
        "country": row["country"],
        "currency": row["currency"],
        "frontend_type": row["frontend_type"],
        "normalized_card_subtype": normalize_card_subtype_for_brand(
            row["brand"],
            row["normalized_card_subtype"] or row["raw_card_subtype"] or row["subtype"],
            row["frontend_type"],
        ),
        "denom_min": row["denom_min"],
        "denom_max": row["denom_max"],
        "multiplier": row["multiplier"],
    }


def _sort_quote_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            to_decimal(item.get("supplier_rate")) or 0,
            item.get("updated_at") or "",
            item.get("quote_id") or 0,
        ),
        reverse=True,
    )


def _range_coverage_relation(
    app_min: Any,
    app_max: Any,
    supplier_min: Any,
    supplier_max: Any,
) -> str:
    app_min_value = _number_or_none(app_min)
    app_max_value = _number_or_none(app_max)
    supplier_min_value = _number_or_none(supplier_min)
    supplier_max_value = _number_or_none(supplier_max)

    if app_min_value is None and app_max_value is None:
        return "full" if supplier_min_value is None and supplier_max_value is None else "partial"

    if supplier_min_value is None and supplier_max_value is None:
        return "full"

    supplier_low = float("-inf") if supplier_min_value is None else supplier_min_value
    app_low = float("-inf") if app_min_value is None else app_min_value

    if app_max_value is None:
        if supplier_max_value is None and supplier_low <= app_low:
            return "full"
        if supplier_max_value is None or supplier_max_value >= app_low:
            return "partial"
        return "none"

    if supplier_low <= app_low and (supplier_max_value is None or supplier_max_value >= app_max_value):
        return "full"
    if supplier_max_value is None:
        return "partial"
    if supplier_low <= app_max_value and supplier_max_value >= app_low:
        return "partial"
    return "none"


def _multiplier_coverage_relation(app_multiplier: Any, supplier_multiplier: Any) -> str:
    app_value = to_decimal(app_multiplier)
    supplier_value = to_decimal(supplier_multiplier)
    if app_value in (None, Decimal("0")):
        return "full" if supplier_value in (None, Decimal("0")) else "partial"
    if supplier_value in (None, Decimal("0")):
        return "full"
    if supplier_value == app_value:
        return "full"
    if supplier_value < app_value and app_value % supplier_value == 0:
        return "full"
    return "partial"


def _partial_candidate_reason(type_full: bool, range_relation: str, multiplier_relation: str) -> str:
    reasons = []
    if not type_full:
        reasons.append("类型/细分不完全一致")
    if range_relation == "partial":
        reasons.append("范围仅部分覆盖")
    elif range_relation == "none":
        reasons.append("范围不覆盖")
    if multiplier_relation == "partial":
        reasons.append("倍数需人工确认")
    return "；".join(reasons) or "需人工确认"


def _latest_app_price_record(
    conn: sqlite3.Connection,
    key: tuple[Any, ...],
) -> dict[str, Any] | None:
    clauses, params = _app_key_clauses(key)
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
    return dict(row) if row else None


def _app_key_clauses(key: tuple[Any, ...]) -> tuple[list[str], list[Any]]:
    columns = [
        "brand",
        "country",
        "currency",
        "frontend_type",
        "normalized_card_subtype",
        "multiplier",
        "denom_min",
        "denom_max",
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


def _build_group_impact_list(
    keys: list[tuple[Any, ...]],
    before: dict[tuple[Any, ...], dict[str, Any]],
    after: dict[tuple[Any, ...], dict[str, Any]],
) -> list[dict[str, Any]]:
    impact_items = []
    for key in keys:
        brand, country, currency, frontend_type, normalized_subtype, multiplier, denom_min, denom_max = key
        before_top = before.get(key, {}).get("top")
        after_top = after.get(key, {}).get("top")
        partial_candidates = after.get(key, {}).get("partial_candidates") or []
        app_record = before.get(key, {}).get("app_record") or after.get(key, {}).get("app_record")
        current_backend = None
        if app_record:
            current_backend = app_record.get("recorded_backend_rate")
            if current_backend is None:
                current_backend = app_record.get("suggested_backend_rate")
        action, action_label, reason = _classify_group_impact(current_backend, before_top, after_top, partial_candidates)
        partial_candidate_lines = [_format_impact_candidate(candidate) for candidate in partial_candidates[:3]]
        detail_parts = [
            f"当前维度：{brand} / {market_label(country, currency)} / {normalized_subtype} / {_format_range_label(denom_min, denom_max)} / {_format_multiplier_label(multiplier)}",
            f"管理后台价：{decimal_text(current_backend) if current_backend is not None else '-'}",
            f"暂停前最高报价：{before_top['supplier_rate']} / {before_top['supplier_group']}" if before_top else "暂停前最高报价：-",
            f"暂停后完全覆盖最高报价：{after_top['supplier_rate']} / {after_top['supplier_group']}" if after_top else "暂停后完全覆盖最高报价：-",
        ]
        if partial_candidate_lines:
            detail_parts.append("部分覆盖候选：\n" + "\n".join(partial_candidate_lines))
        else:
            detail_parts.append("部分覆盖候选：-")
        impact_items.append(
            {
                "brand": brand,
                "country": country,
                "currency": currency,
                "frontend_type": frontend_type,
                "normalized_card_subtype": normalized_subtype,
                "multiplier": multiplier,
                "denom_min": denom_min,
                "denom_max": denom_max,
                "current_backend_rate": decimal_text(current_backend) if current_backend is not None else None,
                "before_top_rate": before_top["supplier_rate"] if before_top else None,
                "before_top_group": before_top["supplier_group"] if before_top else None,
                "after_top_rate": after_top["supplier_rate"] if after_top else None,
                "after_top_group": after_top["supplier_group"] if after_top else None,
                "suggested_backend_rate": after_top["supplier_rate"] if after_top else None,
                "partial_candidates": partial_candidates[:3],
                "partial_candidates_text": "\n".join(partial_candidate_lines),
                "action": action,
                "action_label": action_label,
                "reason": reason,
                "reason_detail": "\n".join(detail_parts),
            }
        )
    return impact_items


def _classify_group_impact(
    current_backend: Any,
    before_top: dict[str, Any] | None,
    after_top: dict[str, Any] | None,
    partial_candidates: list[dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    if not after_top:
        if partial_candidates:
            return (
                "manual_review",
                "需人工判断",
                "暂停后未找到完全覆盖当前维度的报价，但存在其他群可接部分范围/倍数/类型；请人工确认是否缩小 APP 后台范围、调整倍数，或保留人工审核。",
            )
        return (
            "no_available_quote",
            "暂无可用报价",
            "暂停后没有找到其他正常、未过期、未覆盖、可接该维度的供应商报价，建议 APP 后台该维度填 0 或暂停收卡。",
        )
    after_rate = to_decimal(after_top["supplier_rate"]) or 0
    current_rate = to_decimal(current_backend)
    if current_rate is not None:
        if after_rate < current_rate:
            return (
                "lower_price",
                "建议下调",
                f"暂停/恢复后最高有效报价低于当前后台确认价，建议改为 {decimal_text(after_rate)}。",
            )
        if after_rate > current_rate:
            return (
                "raise_price",
                "建议上调",
                f"暂停/恢复后仍有更高可用报价，可建议上调为 {decimal_text(after_rate)}。",
            )
        return ("no_change", "无需变化", "暂停/恢复后最高有效报价与当前后台确认价一致。")
    if before_top:
        before_rate = to_decimal(before_top["supplier_rate"]) or 0
        if after_rate < before_rate:
            return (
                "lower_price",
                "建议下调",
                f"暂停后最高有效报价从 {decimal_text(before_rate)} 变为 {decimal_text(after_rate)}。",
            )
        if after_rate > before_rate:
            return (
                "raise_price",
                "建议上调",
                f"恢复后最高有效报价从 {decimal_text(before_rate)} 变为 {decimal_text(after_rate)}。",
            )
    return ("no_change", "无需变化", "当前没有后台确认价，先保留人工确认。")


def _format_impact_candidate(candidate: dict[str, Any]) -> str:
    suffix = f"（{candidate.get('partial_reason')}）" if candidate.get("partial_reason") else ""
    return (
        f"{candidate.get('supplier_group') or '-'} / "
        f"{market_label(candidate.get('country'), candidate.get('currency'))} / "
        f"{candidate.get('normalized_card_subtype') or '-'} / "
        f"{_format_range_label(candidate.get('denom_min'), candidate.get('denom_max'))} / "
        f"{_format_multiplier_label(candidate.get('multiplier'))} / "
        f"{candidate.get('supplier_rate')}{suffix}"
    )


def _format_range_label(denom_min: Any, denom_max: Any) -> str:
    min_value = _number_or_none(denom_min)
    max_value = _number_or_none(denom_max)
    if min_value is None and max_value is None:
        return "范围不限"
    if max_value is None:
        return f"{decimal_text(min_value)}以上"
    if min_value == max_value:
        return f"{decimal_text(min_value)}固定面值"
    return f"{decimal_text(min_value)}-{decimal_text(max_value)}"


def _format_multiplier_label(multiplier: Any) -> str:
    value = _number_or_none(multiplier)
    return "-" if value is None else f"{decimal_text(value)}倍"


def _row_get(row: sqlite3.Row | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if key in row.keys() else None


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def clear_test_data(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM shipment_match_logs")
    conn.execute("DELETE FROM app_price_records")
    conn.execute("DELETE FROM app_price_suggestions")
    conn.execute("DELETE FROM quote_status_logs")
    conn.execute("DELETE FROM quote_bulk_action_logs")
    conn.execute("DELETE FROM operation_logs")
    conn.execute("DELETE FROM supplier_quotes")
    conn.execute("DELETE FROM quote_batches")
    conn.execute("DELETE FROM supplier_groups")


def list_filtered_supplier_quotes(
    conn: sqlite3.Connection,
    filters: dict[str, Any],
    *,
    limit: int | None = 300,
) -> list[sqlite3.Row]:
    clauses, params = supplier_quote_filter_clauses(filters)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = "" if limit is None else f"LIMIT {int(limit)}"
    return conn.execute(
        f"""
        SELECT q.*, COALESCE(g.status, 'normal') AS supplier_group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        {where}
        ORDER BY q.created_at DESC, q.id DESC
        {limit_sql}
        """,
        params,
    ).fetchall()


def count_filtered_supplier_quotes(conn: sqlite3.Connection, filters: dict[str, Any]) -> int:
    clauses, params = supplier_quote_filter_clauses(filters)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM supplier_quotes q
            LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
            {where}
            """,
            params,
        ).fetchone()[0]
    )


def supplier_quote_filter_clauses(
    filters: dict[str, Any],
    *,
    table_alias: str = "q",
) -> tuple[list[str], list[Any]]:
    alias = f"{table_alias}." if table_alias else ""
    filters = _clean_filters(filters)
    clauses: list[str] = []
    params: list[Any] = []
    include_history = str(filters.get("include_history") or "").strip().lower() in {"1", "true", "yes", "on"}

    exact_columns = {
        "brand": "brand",
        "country": "country",
        "currency": "currency",
        "frontend_type": "frontend_type",
        "normalized_card_subtype": "normalized_card_subtype",
        "processing_method": "processing_method",
        "quote_batch_id": "quote_batch_id",
    }
    for key, column in exact_columns.items():
        if filters.get(key):
            clauses.append(f"{alias}{column} = ?")
            params.append(filters[key])
    if include_history and filters.get("status"):
        clauses.append(f"{alias}status = ?")
        params.append(filters["status"])

    supplier_group = filters.get("source_group") or filters.get("supplier_group")
    if supplier_group:
        clauses.append(f"{alias}supplier_group LIKE ?")
        params.append(f"%{supplier_group}%")

    if not include_history:
        clauses.append(f"{alias}status = 'active'")
        clauses.append(f"{alias}deleted_at IS NULL")
        clauses.append(f"({alias}expires_at IS NULL OR {alias}expires_at > ?)")
        params.append(now_iso())

    for key, column in (("denom_min", "denom_min"), ("denom_max", "denom_max"), ("multiplier", "multiplier")):
        value = _filter_number_or_none(filters.get(key))
        if value is not None:
            clauses.append(f"{alias}{column} = ?")
            params.append(value)

    expired = str(filters.get("expired") or "").strip().lower()
    if expired in {"yes", "true", "1", "expired"}:
        clauses.append(f"{alias}expires_at IS NOT NULL AND {alias}expires_at <= ?")
        params.append(now_iso())
    elif expired in {"no", "false", "0", "valid"}:
        clauses.append(f"({alias}expires_at IS NULL OR {alias}expires_at > ?)")
        params.append(now_iso())

    return clauses, params


def bulk_update_quote_status(
    conn: sqlite3.Connection,
    *,
    action: str,
    mode: str,
    quote_ids: list[int] | None = None,
    filters: dict[str, Any] | None = None,
    operator: str = "",
    reason: str = "",
    force_confirm: bool = False,
) -> dict[str, Any]:
    if action not in {"pause", "resume"}:
        raise ValueError("未知批量操作")
    if mode not in {"selected", "filtered"}:
        raise ValueError("未知选择模式")

    clean_filters = _clean_filters(filters or {})
    clean_quote_ids = [int(item) for item in (quote_ids or []) if int(item) > 0]
    if mode == "selected" and not clean_quote_ids:
        raise ValueError("请先选择要操作的报价")
    if mode == "filtered" and not clean_filters and not force_confirm:
        raise ValueError("当前没有筛选条件，批量操作风险很高，请先筛选或二次确认全部报价")

    rows, missing_count = _bulk_candidate_rows(conn, mode, clean_quote_ids, clean_filters)
    timestamp = now_iso()
    updated_ids: list[int] = []
    skipped_reasons: dict[str, int] = {}

    for row in rows:
        skip_reason = _bulk_skip_reason(row, action, timestamp)
        if skip_reason:
            skipped_reasons[skip_reason] = skipped_reasons.get(skip_reason, 0) + 1
            continue
        if action == "pause":
            conn.execute(
                """
                UPDATE supplier_quotes
                SET status = 'paused',
                    paused_at = ?,
                    paused_by_operator = ?,
                    pause_reason = ?,
                    resumed_at = NULL,
                    resumed_by_operator = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, operator.strip() or "local_admin", reason.strip(), timestamp, row["id"]),
            )
        else:
            conn.execute(
                """
                UPDATE supplier_quotes
                SET status = 'active',
                    paused_at = NULL,
                    paused_by_operator = NULL,
                    pause_reason = NULL,
                    resumed_at = ?,
                    resumed_by_operator = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, operator.strip() or "local_admin", timestamp, row["id"]),
            )
        updated_ids.append(int(row["id"]))

    if missing_count:
        skipped_reasons["数据不存在"] = skipped_reasons.get("数据不存在", 0) + missing_count

    affected_keys = {_bulk_quote_key(dict(row)) for row in rows if int(row["id"]) in set(updated_ids)}
    skipped_count = sum(skipped_reasons.values())
    log_cursor = conn.execute(
        """
        INSERT INTO quote_bulk_action_logs (
            action, mode, filters_json, quote_ids_json, affected_quote_count,
            skipped_count, operator, reason, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            mode,
            json.dumps(clean_filters, ensure_ascii=False),
            json.dumps(clean_quote_ids, ensure_ascii=False),
            len(updated_ids),
            skipped_count,
            operator.strip() or "local_admin",
            reason.strip(),
            timestamp,
        ),
    )
    action_text = "暂停" if action == "pause" else "恢复正常"
    return {
        "log_id": int(log_cursor.lastrowid),
        "action": action,
        "mode": mode,
        "affected_quote_ids": updated_ids,
        "affected_quote_count": len(updated_ids),
        "skipped_count": skipped_count,
        "skipped_reasons": skipped_reasons,
        "affected_keys_count": len(affected_keys),
        "message": f"已{action_text} {len(updated_ids)} 条报价，跳过 {skipped_count} 条。",
    }


def _clean_filters(filters: dict[str, Any]) -> dict[str, str]:
    cleaned = {
        str(key): str(value).strip()
        for key, value in (filters or {}).items()
        if value is not None and str(value).strip() != ""
    }
    market = cleaned.pop("market", "") or cleaned.pop("market_id", "")
    market_country, market_currency = split_market_value(market)
    if market_country and market_currency:
        cleaned["country"] = market_country
        cleaned["currency"] = market_currency
    if cleaned.get("currency"):
        cleaned["currency"] = cleaned["currency"].upper()
    if cleaned.get("normalized_subtype") and not cleaned.get("normalized_card_subtype"):
        cleaned["normalized_card_subtype"] = cleaned["normalized_subtype"]
    if cleaned.get("source_group") and not cleaned.get("supplier_group"):
        cleaned["supplier_group"] = cleaned["source_group"]
    return cleaned


def _filter_number_or_none(value: Any) -> float | None:
    try:
        return _number_or_none(value)
    except (TypeError, ValueError):
        return None


def _bulk_candidate_rows(
    conn: sqlite3.Connection,
    mode: str,
    quote_ids: list[int],
    filters: dict[str, Any],
) -> tuple[list[sqlite3.Row], int]:
    if mode == "selected":
        placeholders = ", ".join("?" for _ in quote_ids)
        rows = conn.execute(
            f"SELECT * FROM supplier_quotes WHERE id IN ({placeholders})",
            quote_ids,
        ).fetchall()
        found_ids = {int(row["id"]) for row in rows}
        return rows, len(set(quote_ids) - found_ids)
    return list_filtered_supplier_quotes(conn, filters, limit=None), 0


def _bulk_skip_reason(row: sqlite3.Row, action: str, timestamp: str) -> str:
    if row["deleted_at"]:
        return "已删除"
    if row["expires_at"] and row["expires_at"] <= timestamp:
        return "已过期"
    status = row["status"]
    if action == "pause":
        if status == "paused":
            return "已经是暂停状态"
        if status not in {"active", "ask_first", "warning"}:
            return "状态不允许操作"
    elif status != "paused":
        return "状态不允许操作"
    return ""


def _bulk_quote_key(quote: dict[str, Any]) -> tuple[Any, ...]:
    denom_min = _number_or_none(quote.get("denom_min"))
    denom_max = _number_or_none(quote.get("denom_max"))
    if denom_min is None and denom_max is None:
        range_type = "unlimited"
    elif denom_max is None:
        range_type = "open"
    elif denom_min == denom_max:
        range_type = "fixed"
    else:
        range_type = "bounded"
    return (
        quote.get("brand"),
        quote.get("country"),
        quote.get("currency"),
        normalize_card_subtype_for_brand(
            quote.get("brand"),
            quote.get("normalized_card_subtype") or quote.get("raw_card_subtype") or quote.get("subtype"),
            quote.get("frontend_type"),
        ),
        denom_min,
        denom_max,
        range_type,
        _number_or_none(quote.get("multiplier")),
    )


def list_brand_top_quotes(
    conn: sqlite3.Connection,
    brand: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    timestamp = now_iso()
    rows = conn.execute(
        """
        SELECT q.*, COALESCE(g.status, 'normal') AS supplier_group_status
        FROM supplier_quotes q
        LEFT JOIN supplier_groups g ON g.id = q.supplier_group_id
        WHERE q.brand = ?
          AND q.status = 'active'
          AND q.supplier_rate IS NOT NULL
          AND q.deleted_at IS NULL
          AND (q.expires_at IS NULL OR q.expires_at >= ?)
          AND COALESCE(g.status, 'normal') = 'normal'
        ORDER BY q.received_at DESC, q.id DESC
        """,
        (brand.strip(), timestamp),
    ).fetchall()

    latest_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        normalized_subtype = normalize_card_subtype_for_brand(
            item.get("brand"),
            item.get("normalized_card_subtype") or item.get("raw_card_subtype") or item.get("subtype"),
            item.get("frontend_type"),
        )
        key = (
            item.get("supplier_group"),
            item.get("brand"),
            item.get("country"),
            item.get("currency"),
            item.get("frontend_type"),
            normalized_subtype,
            item.get("denom_min"),
            item.get("denom_max"),
            item.get("multiplier"),
            item.get("processing_method"),
        )
        if key in latest_by_key:
            continue
        latest_by_key[key] = {
            "id": item["id"],
            "supplier_group": item.get("supplier_group") or "",
            "brand": item.get("brand") or "",
            "country": item.get("country") or "",
            "currency": item.get("currency") or "",
            "frontend_type": item.get("frontend_type") or "",
            "normalized_card_subtype": normalized_subtype,
            "multiplier": item.get("multiplier"),
            "denom_min": item.get("denom_min"),
            "denom_max": item.get("denom_max"),
            "supplier_rate": item.get("supplier_rate_text") or decimal_text(item.get("supplier_rate")),
            "processing_method": item.get("processing_method") or "",
            "feedback_note": item.get("feedback_note") or "",
            "requirements": item.get("requirements") or "",
            "received_at": item.get("received_at") or "",
        }

    method_priority = {"fast_card": 0, "fast_process": 1, "slow_process": 2}

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        try:
            received_timestamp = datetime.fromisoformat(item["received_at"]).timestamp()
        except (TypeError, ValueError):
            received_timestamp = 0.0
        return (
            -(to_decimal(item["supplier_rate"]) or 0),
            method_priority.get(item["processing_method"], 9),
            -received_timestamp,
            -int(item["id"]),
        )

    ranked = sorted(latest_by_key.values(), key=sort_key)[: max(0, limit)]
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def pause_supplier_group_brand_quotes(
    conn: sqlite3.Connection,
    supplier_group: str,
    brand: str,
    operator: str = "",
    note: str = "",
) -> dict[str, Any]:
    clean_group = supplier_group.strip()
    clean_brand = brand.strip()
    timestamp = now_iso()
    before_top3 = list_brand_top_quotes(conn, clean_brand)
    cursor = conn.execute(
        """
        UPDATE supplier_quotes
        SET status = 'paused', updated_at = ?
        WHERE supplier_group = ?
          AND brand = ?
          AND status IN ('active', 'ask_first', 'warning')
        """,
        (timestamp, clean_group, clean_brand),
    )
    affected_count = max(cursor.rowcount, 0)
    after_top3 = list_brand_top_quotes(conn, clean_brand)
    before_top1 = before_top3[0] if before_top3 else None
    after_top1 = after_top3[0] if after_top3 else None
    top_changed = bool(before_top1) and (
        not after_top1 or before_top1["supplier_group"] != after_top1["supplier_group"]
    )
    price_change_amount = None
    price_decreased = False
    price_drop_amount = None
    if before_top1 and after_top1:
        price_change = (to_decimal(after_top1["supplier_rate"]) or 0) - (
            to_decimal(before_top1["supplier_rate"]) or 0
        )
        price_change_amount = decimal_text(price_change)
        price_decreased = price_change < 0
        price_drop_amount = decimal_text(-price_change) if price_decreased else None
    log_detail = {
        "operator_note": note.strip(),
        "before_top3": before_top3,
        "after_top3": after_top3,
        "before_top1_supplier_group": before_top1["supplier_group"] if before_top1 else None,
        "before_top1_rate": before_top1["supplier_rate"] if before_top1 else None,
        "after_top1_supplier_group": after_top1["supplier_group"] if after_top1 else None,
        "after_top1_rate": after_top1["supplier_rate"] if after_top1 else None,
        "top_changed": top_changed,
        "price_change_amount": price_change_amount,
        "price_decreased": price_decreased,
        "price_drop_amount": price_drop_amount,
    }
    log_cursor = conn.execute(
        """
        INSERT INTO quote_status_logs (
            supplier_group, brand, action, affected_count, operator, note, created_at
        )
        VALUES (?, ?, 'pause_brand', ?, ?, ?, ?)
        """,
        (
            clean_group,
            clean_brand,
            affected_count,
            operator.strip(),
            json.dumps(log_detail, ensure_ascii=False),
            timestamp,
        ),
    )
    return {
        "log_id": int(log_cursor.lastrowid),
        "supplier_group": clean_group,
        "brand": clean_brand,
        "affected_count": affected_count,
        **log_detail,
    }


def seed_standard_catalogs(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    for brand, aliases in BRAND_SEEDS.items():
        conn.execute(
            """
            INSERT INTO card_brands (name, is_active, created_at, updated_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                is_active = 1,
                updated_at = excluded.updated_at
            """,
            (brand, timestamp, timestamp),
        )
        brand_id = conn.execute("SELECT id FROM card_brands WHERE name = ?", (brand,)).fetchone()["id"]
        for alias in aliases:
            conn.execute(
                """
                INSERT INTO brand_aliases (brand_id, alias, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET brand_id = excluded.brand_id
                """,
                (brand_id, alias, timestamp),
            )

    for index, item in enumerate(MARKET_SEEDS, start=1):
        conn.execute(
            """
            INSERT INTO card_markets (
                country, currency, display_name, is_active, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(country, currency) DO UPDATE SET
                display_name = excluded.display_name,
                is_active = 1,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            """,
            (
                item["country"],
                item["currency"],
                market_label(item["country"], item["currency"]),
                index,
                timestamp,
                timestamp,
            ),
        )


def list_active_brands(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, name
        FROM card_brands
        WHERE is_active = 1
        ORDER BY name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_active_markets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, country, currency, display_name
        FROM card_markets
        WHERE is_active = 1
        ORDER BY sort_order, country
        """
    ).fetchall()
    return [{**dict(row), "value": market_value(row["country"], row["currency"])} for row in rows]


def seed_sample_data(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM supplier_quotes").fetchone()[0]
    if existing:
        return

    received = now_iso()
    expires = add_hours_iso(6)
    samples = [
        {
            "supplier_group": "A群-快卡",
            "source_text": "Apple US 横卡 50-500 5.20 快卡",
            "brand": "Apple",
            "country": "US",
            "currency": "USD",
            "frontend_type": "physical",
            "subtype": "横卡",
            "processing_method": "fast_card",
            "multiplier": 50,
            "denom_min": 50,
            "denom_max": 500,
            "supplier_rate": 5.20,
            "status": "active",
            "requirements": "",
            "confidence": 0.98,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "B群-综合",
            "source_text": "Apple US 竖卡 50-500 5.10 快刷",
            "brand": "Apple",
            "country": "US",
            "currency": "USD",
            "frontend_type": "physical",
            "subtype": "竖卡",
            "processing_method": "fast_process",
            "multiplier": 50,
            "denom_min": 50,
            "denom_max": 500,
            "supplier_rate": 5.10,
            "status": "active",
            "requirements": "",
            "confidence": 0.96,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "C群-白卡",
            "source_text": "苹果 美区 白卡 50-500 5.00 快卡",
            "brand": "Apple",
            "country": "US",
            "currency": "USD",
            "frontend_type": "physical",
            "subtype": "白卡",
            "processing_method": "fast_card",
            "multiplier": 50,
            "denom_min": 50,
            "denom_max": 500,
            "supplier_rate": 5.00,
            "status": "active",
            "requirements": "",
            "confidence": 0.95,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "D群-代码",
            "source_text": "Apple US 纯代码 50-500 5.40 快卡",
            "brand": "Apple",
            "country": "US",
            "currency": "USD",
            "frontend_type": "code",
            "subtype": "代码/卡密",
            "processing_method": "fast_card",
            "multiplier": 50,
            "denom_min": 50,
            "denom_max": 500,
            "supplier_rate": 5.40,
            "status": "active",
            "requirements": "",
            "confidence": 0.97,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "E群-电子卡",
            "source_text": "Apple US 电子卡 50-500 5.65 快刷",
            "brand": "Apple",
            "country": "US",
            "currency": "USD",
            "frontend_type": "code",
            "subtype": "电子卡",
            "processing_method": "fast_process",
            "multiplier": 50,
            "denom_min": 50,
            "denom_max": 500,
            "supplier_rate": 5.65,
            "status": "active",
            "requirements": "",
            "confidence": 0.96,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "Steam群",
            "source_text": "Steam EUR 代码 10-200 0.88 慢刷",
            "brand": "Steam",
            "country": "EU",
            "currency": "EUR",
            "frontend_type": "code",
            "subtype": "代码/卡密",
            "processing_method": "slow_process",
            "multiplier": None,
            "denom_min": 10,
            "denom_max": 200,
            "supplier_rate": 0.88,
            "status": "active",
            "requirements": "慢反馈",
            "confidence": 0.94,
            "received_at": received,
            "expires_at": expires,
        },
        {
            "supplier_group": "Amazon UK 群",
            "source_text": "Amazon UK 实体卡 25-300 0.91 快卡 发前问",
            "brand": "Amazon",
            "country": "UK",
            "currency": "GBP",
            "frontend_type": "physical",
            "subtype": "普通物理卡",
            "processing_method": "fast_card",
            "multiplier": None,
            "denom_min": 25,
            "denom_max": 300,
            "supplier_rate": 0.91,
            "status": "ask_first",
            "requirements": "发前问",
            "confidence": 0.9,
            "received_at": received,
            "expires_at": expires,
        },
    ]

    for sample in samples:
        insert_supplier_quote(conn, sample)
