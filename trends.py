"""
Источник данных: Google Trends (pytrends).

Используется для трендвотчинга:
- Динамика запросов по товару
- Топ трендовых ниш
Работает БЕЗ ключа, бесплатно.
"""
from typing import Any, Dict, List, Optional

try:
    from pytrends.request import TrendReq
    PTRENDS_AVAILABLE = True
except ImportError:
    PTRENDS_AVAILABLE = False


def _get_client() -> Optional["TrendReq"]:
    if not PTRENDS_AVAILABLE:
        return None
    try:
        return TrendReq(hl="ru", tz=180)  # русский язык, МСК
    except Exception:
        return None


def get_trending_queries(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Топ трендовых запросов в Google Trends (Россия).
    Возвращает список вида [{"query": "...", "rank": 1}, ...].
    """
    client = _get_client()
    if not client:
        return []
    try:
        df = client.trending_searches(pn="russia")
        if df is None or df.empty:
            return []
        results = []
        for i, row in df.head(limit).iterrows():
            q = row.iloc[0] if hasattr(row, "iloc") else str(row.get(0, ""))
            if q:
                results.append({"query": str(q), "rank": len(results) + 1})
        return results
    except Exception:
        return []


def get_interest_over_time(keywords: List[str], period: str = "today 3-m") -> Dict[str, Any]:
    """
    Динамика интереса по ключевым словам за период.
    period: "now 1-H", "now 4-H", "now 1-d", "today 1-m", "today 3-m", "today 12-m"
    """
    client = _get_client()
    if not client or not keywords:
        return {"keywords": keywords, "data": {}}
    try:
        client.build_payload(keywords[:5], timeframe=period, geo="RU")
        df = client.interest_over_time()
        if df is None or df.empty:
            return {"keywords": keywords, "data": {}}
        out = {}
        for kw in keywords:
            if kw in df.columns and kw != "isPartial":
                out[kw] = df[kw].dropna().tolist()
        return {"keywords": keywords, "data": out, "timeline": df.index.tolist()}
    except Exception:
        return {"keywords": keywords, "data": {}}


def is_google_trends_available() -> bool:
    """Проверка доступности Google Trends (всегда True, если установлен pytrends)."""
    return PTRENDS_AVAILABLE and _get_client() is not None


__all__ = [
    "get_trending_queries",
    "get_interest_over_time",
    "is_google_trends_available",
    "PTRENDS_AVAILABLE",
]
