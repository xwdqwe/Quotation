from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .database import now_iso


HISTORY_RETENTION_DAYS = 7

DEFAULT_CATEGORY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "Apple": ("Apple(itunes)", "iTunes", "Apple"),
    "Google Play": ("Google", "Google Play", "Google play"),
    "PSN": ("PSN", "PlayStation"),
    "Razer": ("Razer Gold", "Razer"),
}

DEFAULT_COUNTRY_CODES: dict[str, str] = {
    "US": "US",
    "UK": "UK",
    "EU": "EUR",
    "Canada": "CAD",
    "Australia": "AUD",
    "New Zealand": "NZD",
    "Switzerland": "CHF",
    "Brazil": "BR",
    "Mexico": "MX",
    "Czech Republic": "Czechia",
    "South Korea": "Korea",
}


def init_sync_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cardsabi_merchants (
            merchant_number TEXT PRIMARY KEY,
            merchant_name TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_categories (
            category_name TEXT PRIMARY KEY,
            synced_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_countries (
            country_name TEXT PRIMARY KEY,
            synced_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_brand_mappings (
            parser_brand TEXT PRIMARY KEY,
            category_name TEXT,
            card_speed TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_category_settings (
            category_name TEXT PRIMARY KEY,
            card_speed TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_country_mappings (
            parser_country TEXT PRIMARY KEY,
            cardsabi_country TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardsabi_sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant_number TEXT NOT NULL,
            merchant_name TEXT NOT NULL,
            category_name TEXT,
            source_text TEXT,
            request_json TEXT,
            response_code TEXT,
            response_message TEXT,
            status TEXT NOT NULL,
            operator TEXT,
            parsed_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cardsabi_sync_history_created
            ON cardsabi_sync_history (created_at DESC);
        """
    )
    _ensure_sync_history_columns(conn)
    ensure_mapping_rows(conn)
    ensure_category_settings(conn)


def replace_catalogs(
    conn: sqlite3.Connection,
    merchants: list[dict[str, Any]],
    categories: list[str],
    countries: list[str],
) -> None:
    timestamp = now_iso()
    conn.execute("DELETE FROM cardsabi_merchants")
    conn.execute("DELETE FROM cardsabi_categories")
    conn.execute("DELETE FROM cardsabi_countries")

    for merchant in merchants:
        number = str(merchant.get("merchantNumber") or "").strip()
        name = str(merchant.get("name") or "").strip()
        if number and name:
            conn.execute(
                "INSERT INTO cardsabi_merchants VALUES (?, ?, ?)",
                (number, name, timestamp),
            )
    for category in _clean_strings(categories):
        conn.execute("INSERT INTO cardsabi_categories VALUES (?, ?)", (category, timestamp))
    for country in _clean_strings(countries):
        conn.execute("INSERT INTO cardsabi_countries VALUES (?, ?)", (country, timestamp))

    conn.execute(
        """
        UPDATE cardsabi_brand_mappings
        SET category_name = NULL, updated_at = ?
        WHERE category_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM cardsabi_categories c
              WHERE c.category_name = cardsabi_brand_mappings.category_name
          )
        """,
        (timestamp,),
    )
    conn.execute(
        """
        UPDATE cardsabi_country_mappings
        SET cardsabi_country = NULL, updated_at = ?
        WHERE cardsabi_country IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM cardsabi_countries c
              WHERE c.country_name = cardsabi_country_mappings.cardsabi_country
          )
        """,
        (timestamp,),
    )
    ensure_mapping_rows(conn)
    ensure_category_settings(conn)


def ensure_mapping_rows(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    categories = [row["category_name"] for row in conn.execute("SELECT category_name FROM cardsabi_categories")]
    category_lookup = {item.casefold(): item for item in categories}
    countries = [row["country_name"] for row in conn.execute("SELECT country_name FROM cardsabi_countries")]
    country_lookup = {item.casefold(): item for item in countries}

    brands = conn.execute("SELECT name FROM card_brands WHERE is_active = 1 ORDER BY name").fetchall()
    for row in brands:
        brand = row["name"]
        candidates = DEFAULT_CATEGORY_CANDIDATES.get(brand, (brand,))
        category_name = next(
            (category_lookup[candidate.casefold()] for candidate in candidates if candidate.casefold() in category_lookup),
            None,
        )
        existing = conn.execute(
            "SELECT category_name FROM cardsabi_brand_mappings WHERE parser_brand = ?",
            (brand,),
        ).fetchone()
        if existing:
            if not existing["category_name"] and category_name:
                conn.execute(
                    "UPDATE cardsabi_brand_mappings SET category_name = ?, updated_at = ? WHERE parser_brand = ?",
                    (category_name, timestamp, brand),
                )
            continue
        conn.execute(
            "INSERT INTO cardsabi_brand_mappings VALUES (?, ?, NULL, ?)",
            (brand, category_name, timestamp),
        )

    parser_countries = conn.execute(
        "SELECT DISTINCT country FROM card_markets WHERE is_active = 1 ORDER BY country"
    ).fetchall()
    for row in parser_countries:
        parser_country = row["country"]
        suggested = DEFAULT_COUNTRY_CODES.get(parser_country, parser_country)
        cardsabi_country = country_lookup.get(suggested.casefold())
        existing = conn.execute(
            "SELECT cardsabi_country FROM cardsabi_country_mappings WHERE parser_country = ?",
            (parser_country,),
        ).fetchone()
        if existing:
            if not existing["cardsabi_country"] and cardsabi_country:
                conn.execute(
                    "UPDATE cardsabi_country_mappings SET cardsabi_country = ?, updated_at = ? WHERE parser_country = ?",
                    (cardsabi_country, timestamp, parser_country),
                )
            continue
        conn.execute(
            "INSERT INTO cardsabi_country_mappings VALUES (?, ?, ?)",
            (parser_country, cardsabi_country, timestamp),
        )


def ensure_category_settings(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO cardsabi_category_settings (category_name, card_speed, updated_at)
        SELECT category_name, NULL, ? FROM cardsabi_categories WHERE 1
        ON CONFLICT(category_name) DO NOTHING
        """,
        (timestamp,),
    )
    conn.execute(
        """
        UPDATE cardsabi_category_settings
        SET card_speed = (
                SELECT m.card_speed
                FROM cardsabi_brand_mappings m
                WHERE m.category_name = cardsabi_category_settings.category_name
                  AND m.card_speed IN ('Fast', 'Slow')
                ORDER BY m.parser_brand
                LIMIT 1
            ),
            updated_at = ?
        WHERE card_speed IS NULL
          AND EXISTS (
              SELECT 1
              FROM cardsabi_brand_mappings m
              WHERE m.category_name = cardsabi_category_settings.category_name
                AND m.card_speed IN ('Fast', 'Slow')
          )
        """,
        (timestamp,),
    )


def list_merchants(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM cardsabi_merchants ORDER BY merchant_name, merchant_number"
        ).fetchall()
    ]


def get_merchant(conn: sqlite3.Connection, merchant_number: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM cardsabi_merchants WHERE merchant_number = ?",
        (merchant_number.strip(),),
    ).fetchone()
    return dict(row) if row else None


def list_categories(conn: sqlite3.Connection) -> list[str]:
    return [row["category_name"] for row in conn.execute("SELECT category_name FROM cardsabi_categories ORDER BY category_name")]


def list_category_settings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_category_settings(conn)
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT c.category_name, s.card_speed, s.updated_at
            FROM cardsabi_categories c
            LEFT JOIN cardsabi_category_settings s ON s.category_name = c.category_name
            ORDER BY c.category_name
            """
        ).fetchall()
    ]


def category_setting_dict(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {row["category_name"]: row for row in list_category_settings(conn)}


def save_category_settings(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    allowed_categories = set(list_categories(conn))
    timestamp = now_iso()
    for row in rows:
        category_name = row.get("category_name", "").strip()
        card_speed = row.get("card_speed", "").strip() or None
        if category_name not in allowed_categories:
            raise ValueError(f"Cardsabi 品牌不存在：{category_name or '空白'}")
        if card_speed and card_speed not in {"Fast", "Slow"}:
            raise ValueError(f"卡速无效：{card_speed}")
        conn.execute(
            """
            INSERT INTO cardsabi_category_settings (category_name, card_speed, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(category_name) DO UPDATE SET
                card_speed = excluded.card_speed,
                updated_at = excluded.updated_at
            """,
            (category_name, card_speed, timestamp),
        )


def list_countries(conn: sqlite3.Connection) -> list[str]:
    return [row["country_name"] for row in conn.execute("SELECT country_name FROM cardsabi_countries ORDER BY country_name")]


def list_brand_mappings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_mapping_rows(conn)
    rows = conn.execute(
        """
        SELECT b.name AS parser_brand, m.category_name, m.card_speed, m.updated_at
        FROM card_brands b
        LEFT JOIN cardsabi_brand_mappings m ON m.parser_brand = b.name
        WHERE b.is_active = 1
        ORDER BY b.name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def brand_mapping_dict(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {row["parser_brand"]: row for row in list_brand_mappings(conn)}


def save_brand_mappings(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    allowed_categories = set(list_categories(conn))
    timestamp = now_iso()
    for row in rows:
        parser_brand = row["parser_brand"].strip()
        category_name = row.get("category_name", "").strip() or None
        card_speed = row.get("card_speed", "").strip() or None
        if category_name and category_name not in allowed_categories:
            raise ValueError(f"Cardsabi 品牌不存在：{category_name}")
        if card_speed and card_speed not in {"Fast", "Slow"}:
            raise ValueError(f"卡速无效：{card_speed}")
        conn.execute(
            """
            INSERT INTO cardsabi_brand_mappings (parser_brand, category_name, card_speed, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(parser_brand) DO UPDATE SET
                category_name = excluded.category_name,
                card_speed = excluded.card_speed,
                updated_at = excluded.updated_at
            """,
            (parser_brand, category_name, card_speed, timestamp),
        )


def list_country_mappings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_mapping_rows(conn)
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM cardsabi_country_mappings ORDER BY parser_country"
        ).fetchall()
    ]


def country_mapping_dict(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row["parser_country"]: row["cardsabi_country"]
        for row in list_country_mappings(conn)
        if row["cardsabi_country"]
    }


def save_country_mappings(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    allowed_countries = set(list_countries(conn))
    timestamp = now_iso()
    for row in rows:
        parser_country = row["parser_country"].strip()
        cardsabi_country = row.get("cardsabi_country", "").strip() or None
        if cardsabi_country and cardsabi_country not in allowed_countries:
            raise ValueError(f"Cardsabi 国家不存在：{cardsabi_country}")
        conn.execute(
            """
            INSERT INTO cardsabi_country_mappings (parser_country, cardsabi_country, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(parser_country) DO UPDATE SET
                cardsabi_country = excluded.cardsabi_country,
                updated_at = excluded.updated_at
            """,
            (parser_country, cardsabi_country, timestamp),
        )


def record_sync_history(
    conn: sqlite3.Connection,
    *,
    merchant_number: str,
    merchant_name: str,
    category_name: str,
    source_text: str,
    request_payload: dict[str, Any] | None,
    response_code: str,
    response_message: str,
    status: str,
    operator: str,
    parsed_count: int,
    sent_count: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO cardsabi_sync_history (
            merchant_number, merchant_name, category_name, source_text,
            request_json, response_code, response_message, status,
            operator, parsed_count, sent_count, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            merchant_number,
            merchant_name,
            category_name,
            source_text,
            json.dumps(request_payload, ensure_ascii=False) if request_payload else None,
            response_code,
            response_message,
            status,
            operator.strip(),
            parsed_count,
            sent_count,
            now_iso(),
        ),
    )
    cleanup_sync_history(conn)
    return int(cursor.lastrowid)


def _ensure_sync_history_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(cardsabi_sync_history)").fetchall()}
    if "operator" not in columns:
        conn.execute("ALTER TABLE cardsabi_sync_history ADD COLUMN operator TEXT")


def list_sync_history(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    cleanup_sync_history(conn)
    rows = conn.execute(
        "SELECT * FROM cardsabi_sync_history ORDER BY created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def cleanup_sync_history(conn: sqlite3.Connection, retention_days: int = HISTORY_RETENTION_DAYS) -> int:
    cutoff = (datetime.now() - timedelta(days=retention_days)).replace(microsecond=0).isoformat(sep=" ")
    cursor = conn.execute("DELETE FROM cardsabi_sync_history WHERE created_at < ?", (cutoff,))
    return cursor.rowcount


def catalog_status(conn: sqlite3.Connection) -> dict[str, Any]:
    merchant_count = conn.execute("SELECT COUNT(*) FROM cardsabi_merchants").fetchone()[0]
    category_count = conn.execute("SELECT COUNT(*) FROM cardsabi_categories").fetchone()[0]
    country_count = conn.execute("SELECT COUNT(*) FROM cardsabi_countries").fetchone()[0]
    row = conn.execute(
        """
        SELECT MAX(synced_at) AS synced_at FROM (
            SELECT synced_at FROM cardsabi_merchants
            UNION ALL SELECT synced_at FROM cardsabi_categories
            UNION ALL SELECT synced_at FROM cardsabi_countries
        )
        """
    ).fetchone()
    return {
        "merchant_count": merchant_count,
        "category_count": category_count,
        "country_count": country_count,
        "synced_at": row["synced_at"] if row else None,
    }


def _clean_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
