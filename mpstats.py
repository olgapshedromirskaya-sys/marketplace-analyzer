from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from database import get_mpstats_token


@dataclass
class NicheParams:
    """
    Параметры запроса анализа ниши.
    """

    user_id: int
    query: str  # ключевое слово или категория
    budget: float  # бюджет в рублях
    platform: str  # "wb", "ozon" или "both"
    period_months: int  # 1 / 3 / 6


class MPStatsClient:
    """
    Клиент для работы с MPStats API.

    ВАЖНО: сам токен не хранится здесь и не берётся из .env.
    Для каждого пользователя токен хранится в SQLite (таблица users)
    и вытаскивается функцией get_mpstats_token.
    """

    def __init__(self, base_url: str = "https://mpstats.io/api"):
        # Базовый URL можно будет поменять, если потребуется
        self.base_url = base_url.rstrip("/")

    def _get_headers(self, token: str) -> Dict[str, str]:
        """
        Формирует заголовки для запроса к MPStats.
        """
        return {
            "X-Mpstats-TOKEN": token,
            "Accept": "application/json",
        }

    def analyze_niche(self, params: NicheParams) -> Dict[str, Any]:
        """
        Основной метод анализа ниши.

        1. Достаёт токен пользователя из базы.
        2. Если токена нет или запрос к API не удался — возвращает демо-данные.
        3. В боевом режиме здесь должен быть реальный вызов MPStats API.
        """
        token = get_mpstats_token(params.user_id)
        if not token:
            # Нет токена → демо-режим
            return self._demo_data(params, reason="no_token")

        try:
            # Примерный формат запроса к MPStats (нужно адаптировать под реальное API)
            url = f"{self.base_url}/niche/analyze"
            payload = {
                "query": params.query,
                "budget": params.budget,
                "platform": params.platform,
                "period_months": params.period_months,
            }
            resp = requests.post(url, json=payload, headers=self._get_headers(token), timeout=20)
            resp.raise_for_status()
            data = resp.json()

            # Здесь можно адаптировать структуру ответа к нашему единому формату
            return self._normalize_response(data, params)
        except Exception:
            # Любая ошибка → демо-данные
            return self._demo_data(params, reason="api_error")

    def _normalize_response(self, api_data: Dict[str, Any], params: NicheParams) -> Dict[str, Any]:
        """
        Преобразует ответ MPStats к единому формату, который использует бот и WebApp.
        Структура api_data зависит от реального API — здесь делаем универсальный маппинг.
        """
        # В примере предполагаем, что API уже возвращает почти нужные поля.
        # Если формат другой, это место нужно будет доработать.
        return {
            "query": params.query,
            "budget": params.budget,
            "platform": params.platform,
            "period_months": params.period_months,
            "revenue_per_month": api_data.get("revenue_per_month", 0),
            "sellers_count": api_data.get("sellers_count", 0),
            "buyout_rate": api_data.get("buyout_rate", 0.0),
            "noname_share": api_data.get("noname_share", 0.0),
            "top1_share": api_data.get("top1_share", 0.0),
            "trend": api_data.get("trend", "stable"),  # growth / fall / stable
            "seasonality_top_months": api_data.get("seasonality_top_months", []),
            "price_segments": api_data.get("price_segments", []),
            "top_competitors": api_data.get("top_competitors", []),
        }

    def _demo_data(self, params: NicheParams, reason: str) -> Dict[str, Any]:
        """
        Возвращает реалистичные демо-данные, если нет токена или API недоступен.
        """
        # Простая имитация в зависимости от платформы и периода.
        base_revenue = 1_500_000 if params.platform.lower() == "wb" else 1_200_000
        factor = {1: 1.0, 3: 0.9, 6: 0.85}.get(params.period_months, 1.0)
        revenue = base_revenue * factor

        trend = "growth" if params.period_months in (1, 3) else "stable"

        # Реалистичные конкуренты в зависимости от типа ниши
        top_competitors = self._demo_competitors(params)

        return {
            "demo": True,
            "demo_reason": reason,
            "query": params.query,
            "budget": params.budget,
            "platform": params.platform,
            "period_months": params.period_months,
            "revenue_per_month": revenue,
            "sellers_count": 120,
            "buyout_rate": 0.6,
            "noname_share": 0.4,
            "top1_share": 0.18,
            "trend": trend,  # growth / fall / stable
            "seasonality_top_months": ["март", "апрель", "ноябрь"],
            "price_segments": [
                {"segment": "низкий", "revenue_share": 0.25},
                {"segment": "средний", "revenue_share": 0.5},
                {"segment": "высокий", "revenue_share": 0.25},
            ],
            "top_competitors": top_competitors,
        }

    def _demo_competitors(self, params: NicheParams) -> List[Dict[str, Any]]:
        """
        Возвращает реалистичные демо-конкуренты для разных базовых категорий.

        Используется в том числе в режиме «Подобрать товар», чтобы карточки
        выглядели как реальные товары с WB.
        """
        q = params.query.lower()

        # 1. Термосы
        if "термос" in q:
            return [
                {
                    "name": "Термос Арктика 106-500 стальной 500 мл",
                    "price": 1890,
                    "sales_per_month": 1200,
                    "rating": 4.8,
                },
                {
                    "name": "Термокружка LaPlaya Office 500 мл нержавеющая сталь",
                    "price": 1590,
                    "sales_per_month": 950,
                    "rating": 4.6,
                },
                {
                    "name": "Термос Biostal NBP-500 туристический 500 мл",
                    "price": 1390,
                    "sales_per_month": 780,
                    "rating": 4.7,
                },
                {
                    "name": "Термос спортивный Tiger 0.5 л с поилкой",
                    "price": 2290,
                    "sales_per_month": 620,
                    "rating": 4.9,
                },
                {
                    "name": "Термос для еды Thermos King 470 мл",
                    "price": 2590,
                    "sales_per_month": 540,
                    "rating": 4.8,
                },
            ]

        # 2. Органайзеры для кабелей
        if "органайзер" in q or "кабел" in q:
            return [
                {
                    "name": "Органайзер для проводов Baseus Cube настольный",
                    "price": 690,
                    "sales_per_month": 1100,
                    "rating": 4.7,
                },
                {
                    "name": "Органайзер сумка для кабелей UGREEN двойной чехол",
                    "price": 1290,
                    "sales_per_month": 830,
                    "rating": 4.8,
                },
                {
                    "name": "Органайзер для кабелей Xiaomi Youpin настенный набор 10 шт",
                    "price": 490,
                    "sales_per_month": 1500,
                    "rating": 4.6,
                },
                {
                    "name": "Сумка-органайзер для электроники Mark Ryden Compact",
                    "price": 1590,
                    "sales_per_month": 540,
                    "rating": 4.7,
                },
                {
                    "name": "Органайзер для проводов силиконовый 5 каналов",
                    "price": 350,
                    "sales_per_month": 1900,
                    "rating": 4.5,
                },
            ]

        # 3. Силиконовые формы для выпечки
        if "форма" in q or "выпеч" in q:
            return [
                {
                    "name": "Форма силиконовая Доляна для кексов 6 ячеек",
                    "price": 490,
                    "sales_per_month": 1400,
                    "rating": 4.8,
                },
                {
                    "name": "Форма для кексов TimA силиконовая 12 ячеек",
                    "price": 690,
                    "sales_per_month": 980,
                    "rating": 4.7,
                },
                {
                    "name": "Набор форм для выпечки Marmiton сердечки 6 шт",
                    "price": 790,
                    "sales_per_month": 760,
                    "rating": 4.6,
                },
                {
                    "name": "Форма силиконовая Bradex для маффинов 24 ячейки",
                    "price": 1190,
                    "sales_per_month": 520,
                    "rating": 4.7,
                },
                {
                    "name": "Форма для хлеба Appetite силиконовая 26×11 см",
                    "price": 650,
                    "sales_per_month": 680,
                    "rating": 4.5,
                },
            ]

        # 4. Чехлы для AirPods
        if "airpods" in q:
            return [
                {
                    "name": "Чехол силиконовый для AirPods 2/1 с карабином",
                    "price": 390,
                    "sales_per_month": 2100,
                    "rating": 4.6,
                },
                {
                    "name": "Чехол ESR Hybrid для AirPods Pro TPU + пластик",
                    "price": 890,
                    "sales_per_month": 980,
                    "rating": 4.7,
                },
                {
                    "name": "Чехол для AirPods 3 Spigen Rugged Armor",
                    "price": 1290,
                    "sales_per_month": 650,
                    "rating": 4.8,
                },
                {
                    "name": "Чехол силиконовый для AirPods Pro с ушками",
                    "price": 450,
                    "sales_per_month": 1500,
                    "rating": 4.5,
                },
                {
                    "name": "Чехол-книжка для AirPods Pro 2 кожзам",
                    "price": 990,
                    "sales_per_month": 430,
                    "rating": 4.4,
                },
            ]

        # 5. Массажные роллеры
        if "роллер" in q or "массаж" in q:
            return [
                {
                    "name": "Массажный роллер Lite Weights EVA 45 см",
                    "price": 1590,
                    "sales_per_month": 870,
                    "rating": 4.7,
                },
                {
                    "name": "Роллер для пилатеса Starfit FA-502 60 см",
                    "price": 1890,
                    "sales_per_month": 720,
                    "rating": 4.8,
                },
                {
                    "name": "Массажный валик Bradex «Рельеф» 33 см",
                    "price": 1390,
                    "sales_per_month": 960,
                    "rating": 4.6,
                },
                {
                    "name": "Роллер с шипами для миофасциального массажа Indigo 33 см",
                    "price": 1790,
                    "sales_per_month": 540,
                    "rating": 4.7,
                },
                {
                    "name": "Набор массажный роллер + мяч Record",
                    "price": 2190,
                    "sales_per_month": 430,
                    "rating": 4.5,
                },
            ]

        # Запасной вариант — обобщённые, но правдоподобные названия
        return [
            {
                "name": "Товар без бренда стандарт",
                "price": 1490,
                "sales_per_month": 900,
                "rating": 4.6,
            },
            {
                "name": "Товар популярный средний сегмент",
                "price": 1290,
                "sales_per_month": 750,
                "rating": 4.5,
            },
            {
                "name": "Товар премиум категория",
                "price": 1790,
                "sales_per_month": 600,
                "rating": 4.8,
            },
            {
                "name": "Товар бюджетный вариант",
                "price": 990,
                "sales_per_month": 500,
                "rating": 4.3,
            },
            {
                "name": "Товар брендовый массовый",
                "price": 1590,
                "sales_per_month": 450,
                "rating": 4.6,
            },
        ]


__all__ = ["MPStatsClient", "NicheParams"]

