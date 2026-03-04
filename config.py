import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()


@dataclass
class Settings:
    """
    Настройки приложения.

    Все чувствительные данные (например, токен телеграм-бота, ADMIN_ID и т.п.)
    читаем только из переменных окружения / файла .env.
    """

    # Telegram
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    admin_id: int = int(os.getenv("ADMIN_ID", "0"))

    # База данных SQLite (файл лежит в корне проекта)
    db_path: str = os.getenv("DB_PATH", "marketplace.db")

    # Настройки FastAPI / Web-сервера
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # URL для Telegram WebApp (дашборд)
    webapp_url: str = os.getenv("WEBAPP_URL", "https://example.com")

    # Часовой пояс для уведомлений (используем для APScheduler)
    timezone: str = os.getenv("TIMEZONE", "Europe/Moscow")


settings = Settings()

