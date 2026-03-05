from dataclasses import dataclass


@dataclass
class WBConstants:
    """
    Средние значения для расчётов по WB.

    ВАЖНО: все эти значения ориентировочные и нужны для
    автоматического подбора товара и юнит-экономики.
    Если условия на WB поменяются — достаточно обновить
    только этот файл.
    """

    # Средняя комиссия WB по категориям (если нет точных данных)
    commission_default: float = 15.0

    # Средняя логистика по России (Москва+регионы), руб/шт
    logistics_rub_per_unit: float = 150.0

    # Средняя стоимость хранения, руб/литр/день
    storage_rub_per_liter_per_day: float = 0.07

    # СПП по умолчанию, %
    spp_percent_default: float = 5.0

    # Налоговый режим по умолчанию
    tax_mode_default: str = "usn_6"

    # Логистика из Китая, $/кг
    logistics_usd_per_kg: float = 5.0

    # Реклама, % от выручки
    ads_percent_default: float = 15.0

    # Прочие фиксированные расходы, руб/мес
    other_expenses_rub_default: float = 15_000.0

    # Фулфилмент, руб/шт
    fulfillment_rub_per_item_default: float = 50.0


WB_DEFAULTS = WBConstants()


__all__ = ["WBConstants", "WB_DEFAULTS"]

