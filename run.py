"""
Точка входа по умолчанию: запускает только бота.
Для API используйте: python3 run_api.py
"""
from database import init_db_sync
from telegram_bot import build_application

if __name__ == "__main__":
    init_db_sync()
    app = build_application()
    app.run_polling()
