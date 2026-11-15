"""SQLAlchemy 2.0 引擎、会话与声明基类。

优先使用 .env 里配置的数据库（MySQL）；连不上时自动降级到本地 SQLite，
保证「一键启动」在评委机器上也能直接跑起来（可用 ALLOW_SQLITE_FALLBACK=0 关闭）。
"""
import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import BASE_DIR, settings

logger = logging.getLogger("ai-campus.db")

_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))


def _sqlite_url() -> str:
    """本地兜底数据库位置：backend/data/campus.db。"""
    data_dir = Path(BASE_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + (data_dir / "campus.db").as_posix()


def _probe(url: str) -> None:
    """用一次 SELECT 1 验证连接是否可用。"""
    probe = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={} if url.startswith("sqlite") else {"connect_timeout": _CONNECT_TIMEOUT},
    )
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        probe.dispose()


def _create_mysql_database(url: str) -> None:
    """MySQL 下库不存在时自动创建（utf8mb4），失败则抛异常由上层降级。"""
    from sqlalchemy.engine import URL, make_url

    parsed = make_url(url)
    # 注意：URL.set(database=None) 不会清除库名，必须用 URL.create 重建
    server_url = URL.create(
        drivername=parsed.drivername,
        username=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port,
        query=parsed.query,
    )
    server = create_engine(server_url, connect_args={"connect_timeout": _CONNECT_TIMEOUT})
    try:
        with server.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{parsed.database}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        server.dispose()


def _resolve_database() -> str:
    """返回真正可用的连接串；MySQL 不可用时降级 SQLite。"""
    url = settings.database_url
    if url.startswith("sqlite"):
        return url

    try:
        _probe(url)
        return url
    except Exception as error:  # noqa: BLE001 - 连接失败先尝试建库，再决定是否降级
        first_error = error

    if os.getenv("AUTO_CREATE_DATABASE", "1") == "1":
        try:
            _create_mysql_database(url)
            _probe(url)
            logger.info("已创建 MySQL 数据库 %s", url)
            return url
        except Exception as error:  # noqa: BLE001
            first_error = error

    if os.getenv("ALLOW_SQLITE_FALLBACK", "1") != "1":
        raise first_error

    fallback = _sqlite_url()
    logger.warning("MySQL 不可用（%s），已改用本地 SQLite：%s", str(first_error)[:120], fallback)
    settings.database_url = fallback
    settings.is_sqlite = True
    settings.db_note = "MySQL 不可用，已自动降级到 SQLite（backend/data/campus.db）"
    return fallback


DATABASE_URL = _resolve_database()

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
    pool_recycle=3600,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db():
    """FastAPI 依赖：每个请求一个数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。生产环境建议改用 Alembic 迁移。"""
    from . import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=engine)
