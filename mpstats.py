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
            "top_competitors": [
                {
                    "name": "Бренд A",
                    "price": 1490,
                    "sales_per_month": 900,
                    "rating": 4.7,
                },
                {
                    "name": "Бренд B",
                    "price": 1290,
                    "sales_per_month": 750,
                    "rating": 4.5,
                },
                {
                    "name": "Бренд C",
                    "price": 1790,
                    "sales_per_month": 600,
                    "rating": 4.8,
                },
                {
                    "name": "Бренд D",
                    "price": 990,
                    "sales_per_month": 500,
                    "rating": 4.3,
                },
                {
                    "name": "Бренд E",
                    "price": 1590,
                    "sales_per_month": 450,
                    "rating": 4.6,
                },
            ],
        }


__all__ = ["MPStatsClient", "NicheParams"]

