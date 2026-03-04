from datetime import datetime, timedelta
from typing import Optional
import xml.etree.ElementTree as ET

import requests

from database import get_cached_currency, set_cached_currency


CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


def get_cny_rate_rub(cache_ttl_hours: int = 6) -> float:
    """
    Возвращает курс юаня к рублю.

    1. Пытается взять значение из кэша в SQLite.
    2. Если оно свежие (моложе cache_ttl_hours), возвращает кэш.
    3. Иначе делает запрос к ЦБ РФ и обновляет кэш.
    """
    cached = get_cached_currency("CNY")
    if cached:
        rate, updated_at = cached
        try:
            updated_dt = datetime.fromisoformat(updated_at)
            if datetime.utcnow() - updated_dt < timedelta(hours=cache_ttl_hours):
                return rate
        except Exception:
            # Если по какой-то причине парсинг даты не удался — игнорируем и идём за новым курсом
            pass

    try:
        resp = requests.get(CBR_URL, timeout=20)
        resp.raise_for_status()
        rate = _parse_cny_rate(resp.text)
        if rate:
            set_cached_currency("CNY", rate)
            return rate
    except Exception:
        # В случае ошибки стараемся использовать старое значение, если оно было
        if cached:
            return cached[0]

    # Если ничего нет — возвращаем безопасное значение по умолчанию
    return 13.0


def _parse_cny_rate(xml_text: str) -> Optional[float]:
    """
    Разбирает XML от ЦБ РФ и достаёт курс CNY.
    """
    try:
        root = ET.fromstring(xml_text)
        for valute in root.findall("Valute"):
            char_code = valute.findtext("CharCode")
            if char_code == "CNY":
                nominal_text = valute.findtext("Nominal") or "1"
                value_text = valute.findtext("Value") or "0"
                nominal = float(nominal_text.replace(",", "."))
                value = float(value_text.replace(",", "."))
                return value / nominal
    except Exception:
        return None
    return None


__all__ = ["get_cny_rate_rub"]

