from dataclasses import dataclass
from typing import Dict, Literal


Platform = Literal["wb", "ozon"]
TaxMode = Literal["usn_6", "usn_15"]


@dataclass
class CalcInput:
    """
    Входные данные для финансового калькулятора.
    """

    purchase_price: float  # цена закупки (в рублях, после конвертации)
    weight_kg: float  # вес товара
    volume_l: float  # объём товара
    platform: Platform  # "wb" или "ozon"
    commission_percent: float  # комиссия маркетплейса, %
    spp_percent: float  # СПП, %
    tax_mode: TaxMode  # "usn_6" или "usn_15"
    logistics_usd_per_kg: float  # логистика из Китая в $/кг
    logistics_usd_to_rub: float  # курс доллара к рублю
    fulfillment_rub_per_item: float  # фулфилмент, руб/шт
    ads_percent: float  # реклама, % от выручки
    other_expenses_rub: float  # прочие расходы в руб/мес
    budget_rub: float  # бюджет в рублях


@dataclass
class CalcResult:
    """
    Результат финансового расчёта.
    """

    units_by_budget: int
    full_cost_per_unit: float
    break_even_price: float
    margin_percent: float
    profit_per_unit: float
    roi_percent: float
    payback_months: float
    profit_per_month: float
    verdict: str
    verdict_label: str


def calculate_unit_economics(
    inputs: CalcInput,
    sale_price: float,
    is_niche_growing: bool,
) -> CalcResult:
    """
    Основная функция калькулятора.

    - sale_price — планируемая цена продажи на маркетплейсе.
    - is_niche_growing — флаг, растёт ли ниша (по данным MPStats).
    """

    # Пересчёт логистики из $/кг в руб/шт
    logistics_rub_per_kg = inputs.logistics_usd_per_kg * inputs.logistics_usd_to_rub
    logistics_rub_per_item = logistics_rub_per_kg * inputs.weight_kg

    # Полная себестоимость единицы
    full_cost_per_unit = (
        inputs.purchase_price
        + logistics_rub_per_item
        + inputs.fulfillment_rub_per_item
    )

    # Сколько единиц можно купить на бюджет (округляем вниз)
    units_by_budget = int(max(inputs.budget_rub // full_cost_per_unit, 0))

    # Комиссия маркетплейса + СПП + реклама считаются от цены продажи
    commission = sale_price * (inputs.commission_percent / 100)
    spp = sale_price * (inputs.spp_percent / 100)
    ads = sale_price * (inputs.ads_percent / 100)

    # Налог (УСН 6% или 15%) — берём с валовой прибыли
    gross_profit_before_tax = sale_price - full_cost_per_unit - commission - spp - ads
    if inputs.tax_mode == "usn_6":
        tax = max(gross_profit_before_tax, 0) * 0.06
    else:
        tax = max(gross_profit_before_tax, 0) * 0.15

    profit_per_unit = gross_profit_before_tax - tax

    # Маржинальность
    margin_percent = (profit_per_unit / sale_price * 100) if sale_price > 0 else 0.0

    # Цена безубытка — когда прибыль = 0
    variable_costs_without_tax = (
        full_cost_per_unit + commission + spp + ads
    )
    if inputs.tax_mode == "usn_6":
        break_even_price = variable_costs_without_tax / (1 - 0.06) if variable_costs_without_tax > 0 else 0
    else:
        break_even_price = variable_costs_without_tax / (1 - 0.15) if variable_costs_without_tax > 0 else 0

    # ROI — отношение месячной прибыли к вложениям
    # Для простоты считаем, что за месяц продаём все закупленные единицы.
    total_profit_month = profit_per_unit * units_by_budget - inputs.other_expenses_rub
    total_investment = full_cost_per_unit * units_by_budget
    roi_percent = (
        (total_profit_month / total_investment * 100)
        if total_investment > 0
        else 0.0
    )

    # Окупаемость в месяцах (при текущей прибыли)
    payback_months = (
        (total_investment / total_profit_month) if total_profit_month > 0 else 0
    )

    # ВЕРДИКТ по условиям из ТЗ
    verdict, verdict_label = _make_verdict(
        margin_percent,
        roi_percent,
        is_niche_growing,
    )

    return CalcResult(
        units_by_budget=units_by_budget,
        full_cost_per_unit=full_cost_per_unit,
        break_even_price=break_even_price,
        margin_percent=margin_percent,
        profit_per_unit=profit_per_unit,
        roi_percent=roi_percent,
        payback_months=payback_months,
        profit_per_month=total_profit_month,
        verdict=verdict,
        verdict_label=verdict_label,
    )


def _make_verdict(
    margin_percent: float,
    roi_percent: float,
    is_niche_growing: bool,
) -> (str, str):
    """
    Возвращает текст вердикта и цветовую метку.

    Условия из ТЗ:
      🟢 БРАТЬ: маржа>25% И ROI>60% И ниша растёт
      🟡 РИСК: маржа 15-25% ИЛИ ROI 30-60%
      🔴 НЕ БРАТЬ: маржа<15% ИЛИ ROI<30%
    """

    if margin_percent > 25 and roi_percent > 60 and is_niche_growing:
        return "🟢 БРАТЬ", "green"

    if (15 <= margin_percent <= 25) or (30 <= roi_percent <= 60):
        return "🟡 РИСК", "yellow"

    if margin_percent < 15 or roi_percent < 30:
        return "🔴 НЕ БРАТЬ", "red"

    # На всякий случай дефолт
    return "🟡 РИСК", "yellow"


__all__ = ["CalcInput", "CalcResult", "calculate_unit_economics"]

