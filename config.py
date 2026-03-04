import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Корень проекта — каталог, где лежит config.py
BASE_DIR = Path(__file__).resolve().parent
# Загружаем .env из корня проекта, чтобы токен подхватывался при любом рабочем каталоге
load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    """
    Настройки приложения.

    Все чувствительные данные (токен бота, ADMIN_ID и т.п.)
    читаем только из переменных окружения / файла .env.
    """

    # Telegram: поддерживаем и TELEGRAM_BOT_TOKEN, и TELEGRAM_TOKEN
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or ""
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

# Проверка загрузки токена (для отладки)
print(f"Token loaded: {bool(settings.telegram_token)}")
