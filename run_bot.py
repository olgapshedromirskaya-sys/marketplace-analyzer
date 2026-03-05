"""
Запуск только Telegram-бота.
Команда: python3 run_bot.py

Для деплоя на Render добавлен простой HTTP health-check сервер,
который отвечает на GET-запросы строкой 'Bot is running'.
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram_bot import build_application


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        # Отключаем лишний лог HTTP-сервера, чтобы не засорять логи Render
        pass


def run_health_server():
    """
    Простой HTTP-сервер для Render на порту из переменной PORT.
    """
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    # Запускаем health-check сервер в отдельном daemon-потоке
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Запускаем Telegram-бота (long polling)
    app = build_application()
    app.run_polling()
