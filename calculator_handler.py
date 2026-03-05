from enum import IntEnum, auto

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


class CalcStates(IntEnum):
    """
    Стадии диалога финансового калькулятора.
    """

    NAME = auto()
    PURCHASE_PRICE = auto()
    SALE_PRICE = auto()
    BUDGET = auto()
    PLATFORM = auto()
    TAX = auto()


async def calc_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Старт упрощённого финансового калькулятора.
    """
    await update.effective_chat.send_message(
        "💰 Финансовый калькулятор.\n\n"
        "Введите название товара, который будем считать "
        "(например: «Термос 500 мл»)."
    )
    return CalcStates.NAME


async def calc_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["calc_name"] = update.message.text.strip()
    await update.effective_chat.send_message("Введите цену закупки в рублях:")
    return CalcStates.PURCHASE_PRICE


async def calc_purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Не смог понять число, попробуйте ещё раз (рубли).")
        return CalcStates.PURCHASE_PRICE

    context.user_data["calc_purchase_price_rub"] = price
    await update.effective_chat.send_message("Введите цену продажи на WB в рублях:")
    return CalcStates.SALE_PRICE


async def calc_sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        sale = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (рубли).")
        return CalcStates.SALE_PRICE

    context.user_data["calc_sale_price"] = sale
    await update.effective_chat.send_message("Введите ваш бюджет в рублях:")
    return CalcStates.BUDGET


async def calc_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        budget = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (рубли).")
        return CalcStates.BUDGET

    context.user_data["calc_budget"] = budget

    kb = ReplyKeyboardMarkup(
        [["WB", "Ozon"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Платформа: WB или Ozon.", reply_markup=kb
    )
    return CalcStates.PLATFORM


async def calc_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().lower()
    plat = "wb" if txt.startswith("wb") else "ozon"
    context.user_data["calc_platform"] = plat

    kb = ReplyKeyboardMarkup(
        [["УСН 6%", "УСН 15%"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Налоговый режим: УСН 6% или УСН 15%.", reply_markup=kb
    )
    return CalcStates.TAX


async def calc_tax(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    tax_rate = 0.15 if "15" in txt else 0.06

    name = context.user_data.get("calc_name", "Товар")
    purchase_rub = float(context.user_data.get("calc_purchase_price_rub", 0.0))
    sale_price = float(context.user_data.get("calc_sale_price", 0.0))
    budget = float(context.user_data.get("calc_budget", 0.0))

    # Константы из ТЗ (средние значения)
    commission_rate = 0.15
    logistics_wb = 150.0
    storage_wb = 15.0
    spp_rate = 0.05
    ads_rate = 0.15
    fulfillment = 50.0
    logistics_cn = 56.0
    other_total = 15_000.0

    # Полная себестоимость (для ROI и окупаемости)
    full_cost = purchase_rub + logistics_cn + fulfillment

    if full_cost <= 0:
        await update.effective_chat.send_message(
            "Себестоимость получилась некорректной (≤ 0). Проверьте входные данные.",
        )
        return ConversationHandler.END

    # Сколько единиц можно купить на бюджет
    units = int(budget // full_cost) if budget > 0 else 0
    if units <= 0:
        await update.effective_chat.send_message(
            "На указанный бюджет не удаётся закупить ни одной единицы товара.\n"
            "Увеличьте бюджет или снизьте себестоимость.",
        )
        return ConversationHandler.END

    # Расходы на продажу (по формуле из ТЗ)
    commission = sale_price * commission_rate
    wb_logistics = logistics_wb
    wb_storage = storage_wb
    spp = sale_price * spp_rate
    ads = sale_price * ads_rate
    tax = sale_price * tax_rate
    other_per_unit = other_total / units

    total_expenses = (
        commission
        + wb_logistics
        + wb_storage
        + spp
        + ads
        + tax
        + other_per_unit
    )

    # Чистая прибыль с единицы
    net_profit_per_unit = sale_price - full_cost - total_expenses

    # Маржинальность и ROI
    margin_percent = (
        net_profit_per_unit / sale_price * 100 if sale_price > 0 else 0.0
    )
    roi_percent = (
        net_profit_per_unit / full_cost * 100 if full_cost > 0 else 0.0
    )

    profit_month = net_profit_per_unit * units
    payback_months = (
        (full_cost / net_profit_per_unit) if net_profit_per_unit > 0 else 0.0
    )

    # Простой вердикт
    if margin_percent > 25 and roi_percent > 60:
        verdict = "🟢 БРАТЬ"
    elif (15 <= margin_percent <= 25) or (30 <= roi_percent <= 60):
        verdict = "🟡 РИСК"
    elif margin_percent < 15 or roi_percent < 30:
        verdict = "🔴 НЕ БРАТЬ"
    else:
        verdict = "🟡 РИСК"

    lines = [
        f"💰 КАЛЬКУЛЯТОР: {name}",
        "━━━━━━━━━━━━━━━",
        f"Цена продажи: {sale_price:.0f} ₽",
        f"Цена закупки: {purchase_rub:.0f} ₽",
        f"Единиц на бюджет: {units} шт",
        "━━━━━━━━━━━━━━━",
        "ВЫЧИТАЕМ:",
        f"- Комиссия WB (15%): — {commission:.0f} ₽",
        f"- Логистика WB: — {wb_logistics:.0f} ₽",
        f"- Хранение: — {wb_storage:.0f} ₽",
        f"- СПП (5%): — {spp:.0f} ₽",
        f"- Реклама (15%): — {ads:.0f} ₽",
        f"- Налог УСН {int(tax_rate*100)}%: — {tax:.0f} ₽",
        f"- Фулфилмент: — {fulfillment:.0f} ₽",
        f"- Прочие (/шт): — {other_per_unit:.0f} ₽",
        "━━━━━━━━━━━━━━━",
        f"Себестоимость: {full_cost:.0f} ₽",
        f"Итого расходов: {total_expenses:.0f} ₽",
        f"ЧИСТАЯ ПРИБЫЛЬ: {net_profit_per_unit:.0f} ₽/шт",
        "━━━━━━━━━━━━━━━",
        f"📊 Маржинальность: {margin_percent:.1f}%",
        f"📈 ROI: {roi_percent:.1f}%",
        f"⏱ Окупаемость: {payback_months:.1f} мес",
        f"💵 Прибыль в месяц: ~{profit_month:.0f} ₽",
        "━━━━━━━━━━━━━━━",
        verdict,
    ]

    await update.effective_chat.send_message("\n".join(lines))
    return ConversationHandler.END


async def calc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message("Калькулятор отменён.")
    return ConversationHandler.END


def build_calculator_conv() -> ConversationHandler:
    """
    Строит ConversationHandler для калькулятора.
    """
    return ConversationHandler(
        entry_points=[
            CommandHandler("calc", calc_entry),
            MessageHandler(filters.Regex(r"^💰 Калькулятор"), calc_entry),
        ],
        states={
            CalcStates.NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_name)
            ],
            CalcStates.PURCHASE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_purchase_price)
            ],
            CalcStates.SALE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_sale_price)
            ],
            CalcStates.BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_budget)
            ],
            CalcStates.PLATFORM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_platform)
            ],
            CalcStates.TAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_tax)
            ],
        },
        fallbacks=[CommandHandler("cancel", calc_cancel)],
    )

