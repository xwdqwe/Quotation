from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import DB_PATH, get_connection, init_db  # noqa: E402
from app.sync_store import catalog_status, init_sync_tables  # noqa: E402


def main() -> None:
    init_db(seed=False)
    with get_connection() as conn:
        init_sync_tables(conn)
        status = catalog_status(conn)
    print(f"数据库已初始化：{DB_PATH}")
    print("解析标准品牌和地区库已就绪。")
    print(
        "Cardsabi 目录缓存："
        f"商家 {status['merchant_count']} 个，品牌 {status['category_count']} 个，国家 {status['country_count']} 个"
    )
    print("首次使用请在“接口设置”中同步 Cardsabi 目录并配置品牌卡速。")


if __name__ == "__main__":
    main()
