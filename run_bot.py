"""
Запуск Telegram-бота и FastAPI для деплоя на Render.
Команда: python3 run_bot.py

- Главный поток: Telegram бот (long polling).
- Поток 1: FastAPI (uvicorn) на PORT — /webapp, /api/*.
- Поток 2: простой health-check на отдельном порту (опционально).
"""

import os
import threading

import uvicorn

from api import app as fastapi_app
from telegram_bot import build_application


def run_fastapi():
    """Запуск FastAPI на PORT из окружения (для Render)."""
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    # Поток 1: FastAPI (веб и WebApp на /webapp)
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()

    # Главный поток: Telegram бот
    app = build_application()
    app.run_polling()
