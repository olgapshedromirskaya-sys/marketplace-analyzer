import threading

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

from api import app as fastapi_app
from telegram_bot import build_application
from config import settings
from notifications import setup_scheduler


# ВАЖНО:
# Этот файл запускает сразу три компонента:
# - FastAPI сервер (порт 8000 по умолчанию)
# - Telegram-бота
# - Планировщик уведомлений (APScheduler)


def start_api() -> None:
    """
    Запуск FastAPI сервера.
    """
    uvicorn.run(
        fastapi_app,
        host=settings.api_host,
        port=settings.api_port,
    )


def start_bot(app) -> None:
    """
    Запуск Telegram-бота (long polling).
    """
    app.run_polling(allowed_updates=app.resolve_used_update_types())


def main() -> None:
    """
    Точка входа.
    """
    # Создаём приложение Telegram-бота
    application = build_application()

    # Создаём планировщик уведомлений
    scheduler = BackgroundScheduler(timezone=settings.timezone)

    # Функция отправки сообщений, которую будет использовать scheduler.
    # ВАЖНО: используем create_task — это потокобезопасный способ
    # отправить сообщение в асинхронное приложение бота.
    def send_message(user_id: int, text: str) -> None:
        application.create_task(
            application.bot.send_message(chat_id=user_id, text=text)
        )

    setup_scheduler(scheduler, send_message)
    scheduler.start()

    # Запускаем FastAPI и бота в разных потоках
    api_thread = threading.Thread(target=start_api, name="api-thread", daemon=True)
    bot_thread = threading.Thread(
        target=start_bot, args=(application,), name="bot-thread", daemon=True
    )

    api_thread.start()
    bot_thread.start()

    # Ожидаем завершения потоков (обычно приложение работает постоянно)
    api_thread.join()
    bot_thread.join()


if __name__ == "__main__":
    main()

