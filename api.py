from datetime import datetime
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import settings
from database import (
    init_db_sync,
    save_analysis,
    get_latest_analyses,
    set_mpstats_token,
)
from mpstats import MPStatsClient, NicheParams
from calculator import CalcInput, calculate_unit_economics
from currency import get_cny_rate_rub


# Создаём экземпляр FastAPI
app = FastAPI(title="Marketplace Analyzer API")


class AnalyzeRequest(BaseModel):
    """
    Тело запроса для анализа ниши через WebApp.
    """

    user_id: int
    query: str
    budget: float
    platform: str  # "wb" / "ozon" / "both"
    period_months: int  # 1 / 3 / 6
    sale_price: float


class AnalyzeResponse(BaseModel):
    """
    Ответ API: данные MPStats + фин. калькулятор.
    """

    analysis: Dict[str, Any]
    calculator: Dict[str, Any]
    verdict: str
    verdict_label: str
    saved_id: int


class TokenRequest(BaseModel):
    """
    Обновление MPStats-токена из WebApp.
    """

    user_id: int
    token: str


@app.on_event("startup")
def on_startup() -> None:
    """
    Хук запуска FastAPI: инициализируем базу.
    Используем синхронную версию, чтобы не блокировать event loop.
    """
    init_db_sync()


@app.get("/")
async def root():
    return {"status": "Bot is running"}


@app.get("/api/health")
def health() -> Dict[str, str]:
    """
    Простой health-check для Render.
    """
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/webapp")
async def webapp():
    """
    Отдача WebApp дашборда (index.html).
    """
    return FileResponse("webapp/index.html")


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Анализ ниши + фин. калькулятор.

    WebApp присылает все необходимые параметры, включая user_id.
    """
    client = MPStatsClient()
    params = NicheParams(
        user_id=req.user_id,
        query=req.query,
        budget=req.budget,
        platform=req.platform,
        period_months=req.period_months,
    )

    # 1. Анализ ниши через MPStats (или демо-данные)
    analysis = client.analyze_niche(params)

    # 2. Определяем, растёт ли ниша
    trend = analysis.get("trend", "stable")
    is_growing = trend == "growth"

    # 3. Для калькулятора нам нужен курс доллара (упрощённо возьмём CNY и переведём)
    # Можно будет заменить на реальный курс USD при необходимости.
    cny_rate = get_cny_rate_rub()
    usd_to_rub = cny_rate * 2  # грубая оценка, чтобы не тянуть ещё одно API

    # Здесь WebApp должен сам собрать все остальные поля для CalcInput.
    # На уровне API мы для простоты используем минимальный набор и разумные
    # значения по умолчанию.
    calc_input = CalcInput(
        purchase_price=req.sale_price * 0.3,  # допустим, себестоимость 30% от цены
        weight_kg=0.5,
        volume_l=2.0,
        platform="wb" if req.platform.lower() == "wb" else "ozon",
        commission_percent=15.0 if req.platform.lower() == "wb" else 12.0,
        spp_percent=5.0,
        tax_mode="usn_6",
        logistics_usd_per_kg=5.0,
        logistics_usd_to_rub=usd_to_rub,
        fulfillment_rub_per_item=50.0,
        ads_percent=15.0,
        other_expenses_rub=15000.0,
        budget_rub=req.budget,
    )

    calc_res = calculate_unit_economics(
        inputs=calc_input,
        sale_price=req.sale_price,
        is_niche_growing=is_growing,
    )

    # 4. Сохраняем анализ в БД
    from json import dumps

    saved_id = save_analysis(
        user_id=req.user_id,
        query=req.query,
        platform=req.platform,
        budget=req.budget,
        result_json=dumps(analysis, ensure_ascii=False),
        verdict=calc_res.verdict,
    )

    return AnalyzeResponse(
        analysis=analysis,
        calculator={
            "units_by_budget": calc_res.units_by_budget,
            "full_cost_per_unit": calc_res.full_cost_per_unit,
            "break_even_price": calc_res.break_even_price,
            "margin_percent": calc_res.margin_percent,
            "profit_per_unit": calc_res.profit_per_unit,
            "roi_percent": calc_res.roi_percent,
            "payback_months": calc_res.payback_months,
            "profit_per_month": calc_res.profit_per_month,
        },
        verdict=calc_res.verdict,
        verdict_label=calc_res.verdict_label,
        saved_id=saved_id,
    )


@app.get("/api/history/{user_id}")
def api_history(user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает последние 5 анализов пользователя для WebApp.
    """
    return get_latest_analyses(user_id=user_id, limit=5)


@app.post("/api/settings/token")
def api_set_token(req: TokenRequest) -> Dict[str, str]:
    """
    Установка MPStats-токена через WebApp.
    """
    if not req.token.strip():
        raise HTTPException(status_code=400, detail="Токен не может быть пустым")
    set_mpstats_token(req.user_id, req.token.strip())
    return {"status": "ok"}


# Экспортируем app для использования в run.py
__all__ = ["app"]

