from dataclasses import dataclass
from urllib.parse import quote

# Используем deep-translator вместо googletrans,
# чтобы избежать конфликтов по зависимостям.
from deep_translator import GoogleTranslator

from currency import get_cny_rate_rub


@dataclass
class ChinaSearchResult:
    """
    Результат подготовки поиска на 1688.
    """

    original_query: str
    chinese_query: str
    search_url: str
    cny_to_rub: float


def build_1688_search(query: str) -> ChinaSearchResult:
    """
    Переводит запрос на китайский и формирует ссылку для поиска на 1688.com.
    Также возвращает актуальный курс юаня к рублю.
    """
    try:
        # Переводим текст с русского на китайский через deep-translator
        chinese_query = GoogleTranslator(source="ru", target="zh-CN").translate(
            query
        )
    except Exception:
        # В случае ошибки перевода просто используем исходный запрос
        chinese_query = query

    # Кодируем запрос для URL без замены пробелов на '+'
    query_encoded = quote(chinese_query)

    # 1688 часто требует авторизацию, поэтому используем
    # международную версию Alibaba, которая открывается без логина
    search_url = f"https://www.alibaba.com/trade/search?SearchText={query_encoded}"

    cny_to_rub = get_cny_rate_rub()

    return ChinaSearchResult(
        original_query=query,
        chinese_query=chinese_query,
        search_url=search_url,
        cny_to_rub=cny_to_rub,
    )


__all__ = ["ChinaSearchResult", "build_1688_search"]

