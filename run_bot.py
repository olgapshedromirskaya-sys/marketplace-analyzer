"""
Запуск только Telegram-бота.
Команда: python3 run_bot.py
"""
from telegram_bot import build_application

if __name__ == "__main__":
    app = build_application()
    app.run_polling()
