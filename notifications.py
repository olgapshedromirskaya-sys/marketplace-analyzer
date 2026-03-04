from datetime import datetime
from typing import Callable, Dict, Any, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from database import get_watchlist, update_watchlist_revenue
from mpstats import MPStatsClient, NicheParams


"""
В этом модуле реализуем планировщик уведомлений:

- Каждые 6 часов: проверка отслеживаемых ниш.
- Каждый день в 9:00 по Москве: краткая сводка.

Чтобы не завязываться на конкретную реализацию Telegram-бота,
мы ожидаем функцию send_message(user_id: int, text: str),
которую будет передавать модуль bot.py при инициализации.
"""


def setup_scheduler(
    scheduler: BackgroundScheduler,
    send_message: Callable[[int, str], None],
) -> None:
    """
    Регистрирует задачи в планировщике.
    """
    client = MPStatsClient()

    # Каждые 6 часов проверяем изменения выручки
    scheduler.add_job(
        check_watchlist_changes,
        IntervalTrigger(hours=6),
        kwargs={"client": client, "send_message": send_message},
        id="watchlist_check",
        replace_existing=True,
    )

    # Каждый день в 9:00 по Москве отправляем сводку
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=9, minute=0, timezone=settings.timezone),
        kwargs={"client": client, "send_message": send_message},
        id="daily_summary",
        replace_existing=True,
    )


def check_watchlist_changes(
    client: MPStatsClient,
    send_message: Callable[[int, str], None],
) -> None:
    """
    Проходит по всем отслеживаемым нишам и проверяет,
    изменилась ли выручка более чем на 10%.
    """
    watchlist = get_watchlist()
    for item in watchlist:
        try:
            params = NicheParams(
                user_id=item["user_id"],
                query=item["query"],
                budget=item.get("last_revenue") or 0,
                platform=item["platform"],
                period_months=1,
            )
            result = client.analyze_niche(params)
            new_rev = float(result.get("revenue_per_month", 0))
            old_rev = float(item.get("last_revenue") or 0)

            if old_rev <= 0:
                # Если раньше не было значения, просто сохраняем
                update_watchlist_revenue(item["id"], new_rev)
                continue

            change_percent = (new_rev - old_rev) / old_rev * 100

            if abs(change_percent) >= 10:
                direction = "выросла" if change_percent > 0 else "упала"
                arrow = "▲" if change_percent > 0 else "▼"
                text = (
                    f"👁 Ниша «{item['query']}» на {item['platform'].upper()} {direction} "
                    f"на {change_percent:.1f}% {arrow}\n\n"
                    f"Было: {old_rev:,.0f} ₽\n"
                    f"Стало: {new_rev:,.0f} ₽"
                )
                send_message(item["user_id"], text)

            # В любом случае обновляем значения
            update_watchlist_revenue(item["id"], new_rev)
        except Exception:
            # Любую ошибку гасим, чтобы не падал планировщик
            continue


def send_daily_summary(
    client: MPStatsClient,
    send_message: Callable[[int, str], None],
) -> None:
    """
    Каждый день в 9:00 МСК отправляем пользователям краткую сводку
    по их отслеживаемым нишам.
    """
    watchlist = get_watchlist()
    if not watchlist:
        return

    # Группируем по пользователям
    by_user: Dict[int, List[Dict[str, Any]]] = {}
    for item in watchlist:
        by_user.setdefault(item["user_id"], []).append(item)

    for user_id, items in by_user.items():
        lines = ["📊 Ежедневная сводка по отслеживаемым нишам:"]
        for item in items:
            try:
                params = NicheParams(
                    user_id=user_id,
                    query=item["query"],
                    budget=item.get("last_revenue") or 0,
                    platform=item["platform"],
                    period_months=1,
                )
                result = client.analyze_niche(params)
                rev = float(result.get("revenue_per_month", 0))
                trend = result.get("trend", "stable")
                trend_symbol = {"growth": "▲", "fall": "▼", "stable": "→"}.get(
                    trend, "→"
                )
                lines.append(
                    f"• «{item['query']}» ({item['platform'].upper()}): "
                    f"{rev:,.0f} ₽/мес {trend_symbol}"
                )
            except Exception:
                continue

        if len(lines) > 1:
            send_message(user_id, "\n".join(lines))


__all__ = ["setup_scheduler"]

