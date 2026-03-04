import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import settings


# Здесь мы храним имя файла базы данных SQLite
DB_PATH = settings.db_path


@contextmanager
def get_connection():
    """
    Контекстный менеджер для подключения к базе данных.

    Всегда закрывает соединение после использования.
    """
    conn = sqlite3.connect(DB_PATH)
    # Включаем возврат строк в виде dict-подобных кортежей
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db_core() -> None:
    """
    Синхронная внутренняя функция инициализации структуры БД.

    Вынесена отдельно, чтобы её можно было вызывать как из sync-кода,
    так и из async-обёртки init_db().
    """
    with get_connection() as conn:
        cur = conn.cursor()

        # Таблица пользователей
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                mpstats_token TEXT,
                is_active INTEGER DEFAULT 0,
                added_at TEXT
            )
            """
        )

        # Таблица анализов ниш
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                platform TEXT,
                budget REAL,
                created_at TEXT,
                result_json TEXT,
                verdict TEXT
            )
            """
        )

        # Таблица отслеживаемых ниш
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                platform TEXT,
                last_revenue REAL,
                last_checked TEXT
            )
            """
        )

        # Кэш курсов валют
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS currency_cache (
                currency TEXT PRIMARY KEY,
                rate REAL,
                updated_at TEXT
            )
            """
        )


async def init_db() -> None:
    """
    Асинхронная обёртка для инициализации БД.

    Позволяет вызывать init_db() через asyncio.run(init_db()),
    как в вашей команде из терминала.
    """
    _init_db_core()


def init_db_sync() -> None:
    """
    Синхронная версия инициализации БД для использования в обычном коде.
    """
    _init_db_core()


# ===== ОПЕРАЦИИ С ПОЛЬЗОВАТЕЛЯМИ =====


def add_user(user_id: int, username: Optional[str] = None, is_active: bool = True) -> None:
    """
    Добавляет пользователя в whitelist или активирует уже существующего.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, username, is_active, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                is_active = excluded.is_active
            """,
            (user_id, username, 1 if is_active else 0, datetime.utcnow().isoformat()),
        )


def remove_user(user_id: int) -> None:
    """
    Деактивирует пользователя (убирает из whitelist).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )


def list_users() -> List[Dict[str, Any]]:
    """
    Возвращает список всех пользователей.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY added_at DESC")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def is_user_allowed(user_id: int) -> bool:
    """
    Проверяет, есть ли пользователь в whitelist.
    Администратор всегда имеет доступ.
    """
    if user_id == settings.admin_id:
        return True
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_active FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
    return bool(row and row["is_active"])


def set_mpstats_token(user_id: int, token: str) -> None:
    """
    Сохраняет MPStats-токен для пользователя.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, mpstats_token, is_active, added_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                mpstats_token = excluded.mpstats_token,
                is_active     = 1
            """,
            (user_id, token, datetime.utcnow().isoformat()),
        )


def get_mpstats_token(user_id: int) -> Optional[str]:
    """
    Возвращает MPStats-токен пользователя или None, если он не задан.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT mpstats_token FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
    return row["mpstats_token"] if row and row["mpstats_token"] else None


# ===== АНАЛИЗЫ НИШ =====


def save_analysis(
    user_id: int,
    query: str,
    platform: str,
    budget: float,
    result_json: str,
    verdict: str,
) -> int:
    """
    Сохраняет результат анализа ниши и возвращает ID записи.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO analyses (user_id, query, platform, budget, created_at, result_json, verdict)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                query,
                platform,
                budget,
                datetime.utcnow().isoformat(),
                result_json,
                verdict,
            ),
        )
        return cur.lastrowid


def get_latest_analyses(user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Возвращает последние N анализов пользователя.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM analyses
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_analysis_by_id(analysis_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает один анализ по ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM analyses WHERE id = ?",
            (analysis_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ===== ОТСЛЕЖИВАНИЕ НИШ =====


def add_to_watchlist(
    user_id: int, query: str, platform: str, last_revenue: float
) -> int:
    """
    Добавляет нишу в отслеживание.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO watchlist (user_id, query, platform, last_revenue, last_checked)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                query,
                platform,
                last_revenue,
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def get_watchlist() -> List[Dict[str, Any]]:
    """
    Возвращает все записи отслеживания ниш.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM watchlist")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def update_watchlist_revenue(
    watch_id: int, new_revenue: float
) -> None:
    """
    Обновляет выручку и время последней проверки для записи отслеживания.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE watchlist
            SET last_revenue = ?, last_checked = ?
            WHERE id = ?
            """,
            (new_revenue, datetime.utcnow().isoformat(), watch_id),
        )


# ===== КЭШ ВАЛЮТ =====


def get_cached_currency(currency: str) -> Optional[Tuple[float, str]]:
    """
    Возвращает из кэша курс и время обновления для валюты.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT rate, updated_at FROM currency_cache WHERE currency = ?",
            (currency,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return float(row["rate"]), row["updated_at"]


def set_cached_currency(currency: str, rate: float) -> None:
    """
    Сохраняет курс валюты в кэш.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO currency_cache (currency, rate, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(currency) DO UPDATE SET
                rate = excluded.rate,
                updated_at = excluded.updated_at
            """,
            (currency, rate, datetime.utcnow().isoformat()),
        )


__all__ = [
    "init_db",
    "init_db_sync",
    "add_user",
    "remove_user",
    "list_users",
    "is_user_allowed",
    "set_mpstats_token",
    "get_mpstats_token",
    "save_analysis",
    "get_latest_analyses",
    "get_analysis_by_id",
    "add_to_watchlist",
    "get_watchlist",
    "update_watchlist_revenue",
    "get_cached_currency",
    "set_cached_currency",
]

