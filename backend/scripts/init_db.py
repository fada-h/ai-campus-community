"""初始化数据库：建库（MySQL）→ 建表 → 写入演示数据。

用法：
    python scripts/init_db.py

连接不上 MySQL 时会自动改用 backend/data/campus.db（SQLite），
所以没有数据库环境也能把演示数据建好。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


def main() -> None:
    mode = "SQLite（本地文件）" if settings.is_sqlite else "MySQL"
    print(f"[1/3] 数据库模式：{mode}")
    if settings.db_note:
        print(f"      {settings.db_note}")

    init_db()
    print("[2/3] 数据表已创建")

    with SessionLocal() as db:
        seeded = seed_if_empty(db)
    print("[3/3] 演示数据" + ("已写入" if seeded else "已存在，跳过"))
    print("\n完成。启动后端：uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
