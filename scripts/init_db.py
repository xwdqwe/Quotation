from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import DB_PATH, get_connection, init_db  # noqa: E402
from app.pricing import recalculate_app_prices  # noqa: E402


def main() -> None:
    init_db(seed=True)
    with get_connection() as conn:
        recalculate_app_prices(conn)
        quote_count = conn.execute("SELECT COUNT(*) FROM supplier_quotes").fetchone()[0]
        price_count = conn.execute("SELECT COUNT(*) FROM app_price_records").fetchone()[0]
        suggestion_count = conn.execute("SELECT COUNT(*) FROM app_price_suggestions").fetchone()[0]
    print(f"数据库已初始化：{DB_PATH}")
    print(f"供应商报价：{quote_count} 条")
    print(f"APP 建议价记录：{price_count} 条")
    print(f"APP 待处理建议：{suggestion_count} 条")


if __name__ == "__main__":
    main()
