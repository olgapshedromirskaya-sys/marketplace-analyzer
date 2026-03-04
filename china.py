from dataclasses import dataclass
from urllib.parse import quote_plus

from googletrans import Translator

from currency import get_cny_rate_rub


translator = Translator()


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
        translation = translator.translate(query, src="ru", dest="zh-cn")
        chinese_query = translation.text
    except Exception:
        # В случае ошибки перевода просто используем исходный запрос
        chinese_query = query

    encoded = quote_plus(chinese_query)
    search_url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={encoded}"

    cny_to_rub = get_cny_rate_rub()

    return ChinaSearchResult(
        original_query=query,
        chinese_query=chinese_query,
        search_url=search_url,
        cny_to_rub=cny_to_rub,
    )


__all__ = ["ChinaSearchResult", "build_1688_search"]

