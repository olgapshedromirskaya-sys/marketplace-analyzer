"""
Модуль Telegram-бота (дубликат логики из bot.py).
Используется в run.py, т.к. имя «bot» занято пакетом bot/.
"""
import logging
from enum import IntEnum, auto
from typing import Any, Dict

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import settings
from database import (
    add_user,
    remove_user,
    list_users,
    is_user_allowed,
    set_mpstats_token,
    get_mpstats_token,
    save_analysis,
    get_latest_analyses,
    add_to_watchlist,
)
from mpstats import MPStatsClient, NicheParams
from calculator import CalcInput, calculate_unit_economics
from china import build_1688_search
from currency import get_cny_rate_rub
from constants import WB_DEFAULTS
from calculator_handler import build_calculator_conv


logger = logging.getLogger(__name__)


# ===== СТАДИИ ДЛЯ ДИАЛОГОВ =====


class AnalyzeStates(IntEnum):
    KEYWORD = auto()
    BUDGET = auto()
    PLATFORM = auto()
    PERIOD = auto()


class TokenStates(IntEnum):
    TOKEN = auto()


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


class ChinaStates(IntEnum):
    QUERY = auto()


class AutoPickStates(IntEnum):
    """
    Стадии диалога автоматического подбора товара.
    """

    BUDGET = auto()
    PLATFORM = auto()
    MONTH = auto()


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Главное меню бота с кнопками из ТЗ.
    """
    kb = [
        [
            KeyboardButton("🎯 Подобрать товар"),
            KeyboardButton("🔍 Анализ ниши"),
            KeyboardButton("💰 Калькулятор"),
        ],
        [
            KeyboardButton("🇨🇳 Найти на 1688"),
            KeyboardButton("📊 История анализов"),
        ],
        [
            KeyboardButton("👁 Отслеживать нишу"),
            KeyboardButton("⚙️ Настройки"),
        ],
        [
            KeyboardButton(
                "🚀 Открыть WebApp",
                web_app=WebAppInfo(url="https://marketplace-analyzer.onrender.com/webapp"),
            ),
        ],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def access_denied_text() -> str:
    """
    Сообщение при отсутствии доступа.
    """
    return "⛔ Доступ закрыт. Для получения доступа обратитесь к администратору."


def user_is_admin(user_id: int) -> bool:
    """
    Проверка, является ли пользователь администратором.
    """
    return user_id == settings.admin_id


def user_allowed(update: Update) -> bool:
    """
    Проверка доступа пользователя: админ всегда имеет доступ,
    остальные — только если есть в whitelist.
    """
    uid = update.effective_user.id
    if user_is_admin(uid):
        return True
    return is_user_allowed(uid)


async def ensure_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Универсальная проверка доступа.
    Если доступа нет — отправляет сообщение и возвращает False.
    """
    if user_allowed(update):
        return True
    await update.effective_chat.send_message(access_denied_text())
    return False


# ===== ОСНОВНЫЕ КОМАНДЫ =====


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start.
    При отсутствии доступа — только текст отказа, без кнопок меню.
    """
    if not user_allowed(update):
        await update.effective_chat.send_message(access_denied_text())
        return

    text = (
        "👋 Привет! Это бот анализа ниш маркетплейсов.\n\n"
        "Используйте кнопки в меню ниже.\n\n"
        "Команда /myid покажет ваш Telegram ID."
    )
    await update.effective_chat.send_message(text, reply_markup=main_menu_keyboard())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /myid — всегда доступна всем.
    """
    user = update.effective_user
    await update.effective_chat.send_message(
        f"Ваш Telegram ID: {user.id}"
    )


# ===== АДМИН-КОМАНДЫ =====


async def adduser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not user_is_admin(update.effective_user.id):
        await update.effective_chat.send_message(access_denied_text())
        return
    if not context.args:
        await update.effective_chat.send_message("Использование: /adduser 123456789")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("user_id должен быть числом.")
        return
    add_user(uid, username=None, is_active=True)
    await update.effective_chat.send_message(f"Пользователь {uid} добавлен в whitelist.")


async def removeuser_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not user_is_admin(update.effective_user.id):
        await update.effective_chat.send_message(access_denied_text())
        return
    if not context.args:
        await update.effective_chat.send_message("Использование: /removeuser 123456789")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.effective_chat.send_message("user_id должен быть числом.")
        return
    remove_user(uid)
    await update.effective_chat.send_message(f"Пользователь {uid} заблокирован.")


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not user_is_admin(update.effective_user.id):
        await update.effective_chat.send_message(access_denied_text())
        return
    users = list_users()
    if not users:
        await update.effective_chat.send_message("Пользователей пока нет.")
        return
    lines = []
    for u in users:
        status = "✅" if u["is_active"] else "❌"
        lines.append(f"{status} {u['user_id']} ({u.get('username') or '-'})")
    await update.effective_chat.send_message("Пользователи:\n" + "\n".join(lines))


# ===== УСТАНОВКА MPSTATS ТОКЕНА =====


async def settoken_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_access(update, context):
        return ConversationHandler.END
    await update.effective_chat.send_message(
        "Пожалуйста, отправьте ваш MPStats API токен одним сообщением."
    )
    return TokenStates.TOKEN


async def settoken_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = update.message.text.strip()
    if not token:
        await update.effective_chat.send_message("Токен не может быть пустым, попробуйте ещё раз.")
        return TokenStates.TOKEN
    set_mpstats_token(update.effective_user.id, token)
    await update.effective_chat.send_message("✅ Токен сохранён.")
    return ConversationHandler.END


async def settoken_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message("Отменено.")
    return ConversationHandler.END


# ===== АНАЛИЗ НИШИ =====


async def analyze_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_access(update, context):
        return ConversationHandler.END
    await update.effective_chat.send_message(
        "🔍 Введите ключевое слово или категорию для анализа."
    )
    return AnalyzeStates.KEYWORD


async def analyze_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["an_query"] = update.message.text.strip()
    await update.effective_chat.send_message("Введите бюджет в рублях.")
    return AnalyzeStates.BUDGET


async def analyze_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        budget = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Не смог понять число. Введите бюджет в рублях ещё раз.")
        return AnalyzeStates.BUDGET
    context.user_data["an_budget"] = budget
    kb = ReplyKeyboardMarkup(
        [["WB", "Ozon", "Обе"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Выберите платформу: WB / Ozon / Обе.", reply_markup=kb
    )
    return AnalyzeStates.PLATFORM


async def analyze_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text.startswith("wb"):
        plat = "wb"
    elif text.startswith("ozon"):
        plat = "ozon"
    else:
        plat = "both"
    context.user_data["an_platform"] = plat
    kb = ReplyKeyboardMarkup(
        [["1 мес", "3 мес", "6 мес"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message("Выберите период: 1 / 3 / 6 месяцев.", reply_markup=kb)
    return AnalyzeStates.PERIOD


async def analyze_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().split()[0]
    try:
        months = int(text)
    except ValueError:
        await update.effective_chat.send_message("Введите 1, 3 или 6.")
        return AnalyzeStates.PERIOD
    query = context.user_data["an_query"]
    budget = context.user_data["an_budget"]
    platform = context.user_data["an_platform"]
    client = MPStatsClient()
    params = NicheParams(
        user_id=update.effective_user.id,
        query=query,
        budget=budget,
        platform=platform,
        period_months=months,
    )
    from json import dumps
    try:
        result = client.analyze_niche(params)
    except Exception:
        result = client._demo_data(params, reason="exception")  # type: ignore
    revenue = result.get("revenue_per_month", 0)
    sellers = result.get("sellers_count", 0)
    buyout = result.get("buyout_rate", 0)
    noname = result.get("noname_share", 0)
    top1 = result.get("top1_share", 0)
    trend = result.get("trend", "stable")
    trend_symbol = {"growth": "РОСТ ▲", "fall": "ПАДЕНИЕ ▼", "stable": "СТАБИЛЬНО →"}.get(
        trend, "СТАБИЛЬНО →"
    )
    season = ", ".join(result.get("seasonality_top_months", []))
    lines = [
        f"🔍 Анализ ниши: «{query}»",
        f"Платформа: {platform.upper()}, период: {months} мес",
        "",
        f"Выручка ниши: {revenue:,.0f} ₽/мес",
        f"Кол-во продавцов: {sellers}",
        f"% выкупа: {buyout*100:.1f}%",
        f"% no-name товаров: {noname*100:.1f}%",
        f"Монополист (доля топ-1): {top1*100:.1f}%",
        f"Тренд: {trend_symbol}",
        f"Сезонность (топ-3 месяца): {season or 'данных нет'}",
        "",
        "Ценовые сегменты:",
    ]
    for seg in result.get("price_segments", []):
        lines.append(
            f"- {seg.get('segment')}: {seg.get('revenue_share', 0)*100:.1f}% выручки"
        )
    lines.append("")
    lines.append("Топ-5 конкурентов:")
    for c in result.get("top_competitors", []):
        lines.append(
            f"- {c.get('name')}: {c.get('price')} ₽, "
            f"{c.get('sales_per_month')} продаж/мес, рейтинг {c.get('rating')}"
        )
    saved_id = save_analysis(
        user_id=update.effective_user.id,
        query=query,
        platform=platform,
        budget=budget,
        result_json=dumps(result, ensure_ascii=False),
        verdict="",
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👁 Добавить в отслеживание", callback_data=f"watch_add:{saved_id}"
                )
            ]
        ]
    )
    await update.effective_chat.send_message("\n".join(lines), reply_markup=kb)
    return ConversationHandler.END


async def watch_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    try:
        _, sid = data.split(":", 1)
        analysis_id = int(sid)
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)
        return
    analyses = get_latest_analyses(update.effective_user.id, limit=10)
    found = next((a for a in analyses if a["id"] == analysis_id), None)
    if not found:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Не удалось найти анализ для отслеживания.")
        return
    from json import loads
    result = loads(found["result_json"])
    revenue = float(result.get("revenue_per_month", 0))
    add_to_watchlist(
        user_id=update.effective_user.id,
        query=found["query"],
        platform=found["platform"],
        last_revenue=revenue,
    )
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("👁 Ниша добавлена в отслеживание.")


# ===== ИСТОРИЯ =====


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_access(update, context):
        return
    analyses = get_latest_analyses(update.effective_user.id, limit=5)
    if not analyses:
        await update.effective_chat.send_message("История пуста.")
        return
    lines = ["📊 Последние анализы:"]
    for a in analyses:
        lines.append(
            f"#{a['id']} — «{a['query']}», {a['platform'].upper()}, "
            f"бюджет {a['budget']}, дата {a['created_at']}"
        )
    await update.effective_chat.send_message("\n".join(lines))


# ===== КАЛЬКУЛЯТОР =====


async def calc_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_access(update, context):
        return ConversationHandler.END
    await update.effective_chat.send_message(
        "💰 Финансовый калькулятор.\n"
        "Сначала введите цену закупки за единицу (в рублях или юанях)."
    )
    return CalcStates.PURCHASE_PRICE


async def calc_purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Не смог понять число, попробуйте ещё раз.")
        return CalcStates.PURCHASE_PRICE
    context.user_data["calc_purchase_price_rub"] = price
    await update.effective_chat.send_message("Введите цену продажи на WB в рублях:")
    return CalcStates.SALE_PRICE


async def calc_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        w = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (кг).")
        return CalcStates.WEIGHT
    context.user_data["calc_weight"] = w
    await update.effective_chat.send_message("Введите объём товара (литры).")
    return CalcStates.VOLUME


async def calc_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        v = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (литры).")
        return CalcStates.VOLUME
    context.user_data["calc_volume"] = v
    kb = ReplyKeyboardMarkup([["WB", "Ozon"]], resize_keyboard=True, one_time_keyboard=True)
    await update.effective_chat.send_message("Платформа: WB или Ozon.", reply_markup=kb)
    return CalcStates.PLATFORM


async def calc_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().lower()
    if txt.startswith("wb"):
        plat = "wb"
        default_commission = 15.0
    else:
        plat = "ozon"
        default_commission = 12.0
    context.user_data["calc_platform"] = plat
    context.user_data["calc_default_commission"] = default_commission
    await update.effective_chat.send_message(
        f"Комиссия маркетплейса, % (по умолчанию {default_commission}):"
    )
    return CalcStates.COMMISSION


async def calc_commission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        commission = context.user_data["calc_default_commission"]
    else:
        try:
            commission = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте по умолчанию.")
            return CalcStates.COMMISSION
    context.user_data["calc_commission"] = commission
    await update.effective_chat.send_message("СПП, % (по умолчанию 5):")
    return CalcStates.SPP


async def calc_spp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        spp = 5.0
    else:
        try:
            spp = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте пустым.")
            return CalcStates.SPP
    context.user_data["calc_spp"] = spp
    kb = ReplyKeyboardMarkup([["УСН 6%", "УСН 15%"]], resize_keyboard=True, one_time_keyboard=True)
    await update.effective_chat.send_message("Налог: УСН 6% или УСН 15%.", reply_markup=kb)
    return CalcStates.TAX


async def calc_tax(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip()
    if "15" in txt:
        tax_mode = "usn_15"
    else:
        tax_mode = "usn_6"
    context.user_data["calc_tax_mode"] = tax_mode
    await update.effective_chat.send_message(
        "Логистика из Китая, $/кг (по умолчанию 5):"
    )
    return CalcStates.LOGISTICS


async def calc_logistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        log = 5.0
    else:
        try:
            log = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте пустым.")
            return CalcStates.LOGISTICS
    context.user_data["calc_logistics"] = log
    await update.effective_chat.send_message(
        "Услуги фулфилмента, руб/шт (по умолчанию 50):"
    )
    return CalcStates.FULFILLMENT


async def calc_fulfillment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        ff = 50.0
    else:
        try:
            ff = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте пустым.")
            return CalcStates.FULFILLMENT
    context.user_data["calc_ff"] = ff
    await update.effective_chat.send_message(
        "Реклама, % от выручки (по умолчанию 15):"
    )
    return CalcStates.ADS


async def calc_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        ads = 15.0
    else:
        try:
            ads = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте пустым.")
            return CalcStates.ADS
    context.user_data["calc_ads"] = ads
    await update.effective_chat.send_message(
        "Прочие расходы, руб/мес (по умолчанию 15000):"
    )
    return CalcStates.OTHER_EXPENSES


async def calc_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().replace(",", ".")
    if not txt:
        other = 15000.0
    else:
        try:
            other = float(txt)
        except ValueError:
            await update.effective_chat.send_message("Введите число или оставьте пустым.")
            return CalcStates.OTHER_EXPENSES
    context.user_data["calc_other"] = other
    await update.effective_chat.send_message("Бюджет в рублях:")
    return CalcStates.BUDGET


async def calc_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        budget = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (рубли).")
        return CalcStates.BUDGET
    context.user_data["calc_budget"] = budget
    await update.effective_chat.send_message("Планируемая цена продажи (руб):")
    return CalcStates.SALE_PRICE


async def calc_sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        sale = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (руб).")
        return CalcStates.SALE_PRICE
    context.user_data["calc_sale_price"] = sale
    kb = ReplyKeyboardMarkup(
        [["Да", "Нет", "Не знаю"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Ниша растёт? (для вердикта) — Да / Нет / Не знаю.", reply_markup=kb
    )
    return CalcStates.NICHE_GROWTH


async def calc_niche_growth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    txt = update.message.text.strip().lower()
    is_growing = txt.startswith("д")
    price_rub = context.user_data["calc_purchase_price_rub"]
    weight = context.user_data["calc_weight"]
    volume = context.user_data["calc_volume"]
    platform = context.user_data["calc_platform"]
    commission = context.user_data["calc_commission"]
    spp = context.user_data["calc_spp"]
    tax_mode = context.user_data["calc_tax_mode"]
    logistics = context.user_data["calc_logistics"]
    ff = context.user_data["calc_ff"]
    ads = context.user_data["calc_ads"]
    other = context.user_data["calc_other"]
    budget = context.user_data["calc_budget"]
    sale_price = context.user_data["calc_sale_price"]
    cny_rate = get_cny_rate_rub()
    usd_rate = cny_rate * 2
    inp = CalcInput(
        purchase_price=price_rub,
        weight_kg=weight,
        volume_l=volume,
        platform=platform,
        commission_percent=commission,
        spp_percent=spp,
        tax_mode=tax_mode,
        logistics_usd_per_kg=logistics,
        logistics_usd_to_rub=usd_rate,
        fulfillment_rub_per_item=ff,
        ads_percent=ads,
        other_expenses_rub=other,
        budget_rub=budget,
    )
    res = calculate_unit_economics(
        inputs=inp,
        sale_price=sale_price,
        is_niche_growing=is_growing,
    )
    lines = [
        "💰 Результаты калькулятора:",
        f"Кол-во единиц на бюджет: {res.units_by_budget}",
        f"Полная себестоимость единицы: {res.full_cost_per_unit:.2f} ₽",
        f"Цена безубытка: {res.break_even_price:.2f} ₽",
        f"Маржинальность: {res.margin_percent:.1f}%",
        f"Прибыль с единицы: {res.profit_per_unit:.2f} ₽",
        f"ROI: {res.roi_percent:.1f}%",
        f"Окупаемость: {res.payback_months:.1f} мес.",
        f"Прогноз прибыли/мес: {res.profit_per_month:.0f} ₽",
        "",
        f"ВЕРДИКТ: {res.verdict}",
    ]
    await update.effective_chat.send_message("\n".join(lines), reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def calc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message("Калькулятор отменён.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ===== ПОИСК НА 1688 =====


async def china_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await ensure_access(update, context):
        return ConversationHandler.END
    await update.effective_chat.send_message(
        "🇨🇳 Введите запрос на русском языке, я переведу его и подготовлю ссылку для 1688."
    )
    return ChinaStates.QUERY


async def china_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query_text = update.message.text.strip()
    result = build_1688_search(query_text)
    text = (
        f"🇨🇳 Запрос: «{result.original_query}»\n"
        f"Китайский: «{result.chinese_query}»\n\n"
        f"🔗 Ссылка для поиска на 1688:\n{result.search_url}\n\n"
        f"Курс CNY→RUB по ЦБ РФ: {result.cny_to_rub:.2f} ₽"
    )
    await update.effective_chat.send_message(text, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def china_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_chat.send_message("Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ===== АВТОМАТИЧЕСКИЙ ПОДБОР ТОВАРА =====


async def autopick_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Старт диалога автоматического подбора товара.
    """
    if not await ensure_access(update, context):
        return ConversationHandler.END

    await update.effective_chat.send_message(
        "🎯 Автоматический подбор товара.\n\n"
        "Сначала введите ваш бюджет в рублях (например: 100000)."
    )
    return AutoPickStates.BUDGET


async def autopick_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг 1 — бюджет.
    """
    try:
        budget = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Не смог понять число. Введите бюджет ещё раз.")
        return AutoPickStates.BUDGET

    context.user_data["ap_budget"] = budget

    kb = ReplyKeyboardMarkup(
        [["WB", "Ozon", "Обе"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Платформа: WB / Ozon / Обе.", reply_markup=kb
    )
    return AutoPickStates.PLATFORM


async def autopick_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг 2 — выбираем платформу.
    """
    txt = update.message.text.strip().lower()
    if txt.startswith("wb"):
        plat = "wb"
    elif txt.startswith("ozon"):
        plat = "ozon"
    else:
        plat = "both"

    context.user_data["ap_platform"] = plat

    # Кнопки выбора месяца + «Пропустить»
    month_kb = ReplyKeyboardMarkup(
        [
            ["Январь", "Февраль", "Март"],
            ["Апрель", "Май", "Июнь"],
            ["Июль", "Август", "Сентябрь"],
            ["Октябрь", "Ноябрь", "Декабрь"],
            ["⏭ Пропустить"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "Выберите сезонный месяц или нажмите «⏭ Пропустить».",
        reply_markup=month_kb,
    )
    return AutoPickStates.MONTH


async def autopick_season(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг 3 — месяц сезона, затем запускаем подбор.
    """
    raw = update.message.text.strip()
    lower = raw.lower()
    # Любой вариант «пропустить» (в т.ч. кнопка «⏭ Пропустить») трактуем как отсутствие сезона
    if "пропустить" in lower:
        month = ""
    else:
        month = lower

    budget = context.user_data.get("ap_budget", 0.0)
    platform = context.user_data.get("ap_platform", "wb")

    await update.effective_chat.send_message("Ищу подходящие товары, подождите 5–10 секунд...")

    try:
        await run_auto_selection(update, context, budget, platform, month)
    except Exception:
        await update.effective_chat.send_message(
            "Произошла ошибка при подборе товара. Попробуйте ещё раз позже."
        )

    return ConversationHandler.END


async def autopick_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отмена автоподбора.
    """
    await update.effective_chat.send_message("Подбор товара отменён.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def run_auto_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    budget: float,
    platform: str,
    season_month: str,
) -> None:
    """
    Основная логика автоподбора:
    - вызывает MPStats для нескольких ниш (или использует демо);
    - фильтрует ниши по заданным критериям;
    - выбирает конкретные товары;
    - считает юнит-экономику и отправляет развернутые карточки.
    """
    user_id = update.effective_user.id
    has_token = get_mpstats_token(user_id) is not None

    client = MPStatsClient()

    # Набор базовых ниш (как для демо, так и для реального режима)
    base_queries = [
        ("Термос 500мл", "Термосы и термокружки"),
        ("Органайзер для кабелей", "Органайзеры"),
        ("Силиконовая форма для выпечки", "Товары для кухни"),
        ("Чехол для AirPods", "Аксессуары для электроники"),
        ("Массажный роллер", "Товары для спорта"),
    ]

    candidates = []

    # Шаг 1 — собираем данные по нишам через MPStats (или демо)
    for query_text, category in base_queries:
        params = NicheParams(
            user_id=user_id,
            query=query_text,
            budget=budget,
            platform=platform,
            period_months=3,
        )
        try:
            analysis = client.analyze_niche(params)
        except Exception:
            analysis = client._demo_data(params, reason="exception")  # type: ignore

        # Проверяем критерии ниши
        if not niche_passes_filters(analysis, season_month):
            continue

        # Выбираем среди конкурентов 1–2 товаров в диапазоне продаж 500–5000 шт/мес
        for comp in analysis.get("top_competitors", []):
            sales = comp.get("sales_per_month") or 0
            price = comp.get("price") or 0
            rating = comp.get("rating") or 0.0

            if not (500 <= sales <= 5000):
                continue
            if rating >= 4.7:
                continue
            if price <= 0:
                continue
            if price > budget:
                # Если цена одной единицы выше всего бюджета — пропускаем
                continue

            candidates.append(
                {
                    "query": query_text,
                    "category": category,
                    "analysis": analysis,
                    "comp": comp,
                    "platform": platform,
                }
            )

    if not candidates:
        await update.effective_chat.send_message(
            "😔 По вашим параметрам не найдено прибыльных товаров.\n"
            "Попробуйте увеличить бюджет или изменить платформу."
        )
        return

    # Шаг 2 — считаем юнит-экономику и фильтруем только прибыльные товары
    profitable: list[Dict[str, Any]] = []

    # Общие параметры для расчёта
    d = WB_DEFAULTS
    weight_kg = 0.5
    volume_l = 2.0
    cny_rate = get_cny_rate_rub()
    usd_rate = cny_rate * 2

    for item in candidates:
        if len(profitable) >= 5:
            break

        analysis = item["analysis"]
        comp = item["comp"]
        sale_price = float(comp.get("price") or 0)
        if sale_price <= 0:
            continue

        purchase_rub = sale_price * 0.2

        inp = CalcInput(
            purchase_price=purchase_rub,
            weight_kg=weight_kg,
            volume_l=volume_l,
            platform="wb" if platform == "wb" else "ozon",
            commission_percent=d.commission_default,
            spp_percent=d.spp_percent_default,
            tax_mode=d.tax_mode_default,  # type: ignore[arg-type]
            logistics_usd_per_kg=d.logistics_usd_per_kg,
            logistics_usd_to_rub=usd_rate,
            fulfillment_rub_per_item=d.fulfillment_rub_per_item_default,
            ads_percent=d.ads_percent_default,
            other_expenses_rub=d.other_expenses_rub_default,
            budget_rub=budget,
        )

        calc = calculate_unit_economics(
            inputs=inp,
            sale_price=sale_price,
            is_niche_growing=(analysis.get("trend") == "growth"),
        )

        # ЖЁСТКИЕ ФИЛЬТРЫ прибыльности
        if calc.profit_per_unit <= 0:
            continue
        if calc.margin_percent < 20:
            continue
        if calc.roi_percent < 50:
            continue
        if calc.payback_months > 1:
            continue
        if calc.profit_per_month < 15_000:
            continue

        profitable.append(item)

    if not profitable:
        await update.effective_chat.send_message(
            "😔 По вашим параметрам не найдено прибыльных товаров.\n"
            "Попробуйте увеличить бюджет или изменить платформу."
        )
        return

    # Для каждого прибыльного кандидата отправляем карточку
    for idx, item in enumerate(profitable, start=1):
        await send_autopick_card(
            update,
            context,
            idx,
            item,
            budget=budget,
            platform=platform,
            has_token=has_token,
        )

    if not has_token:
        await update.effective_chat.send_message(
            "🔑 Вы видите демо-подбор на основе тестовых данных.\n"
            "Добавьте MPStats токен в настройках (команда /settoken), "
            "чтобы получать реальные подборы под ваш аккаунт.",
            reply_markup=main_menu_keyboard(),
        )


def niche_passes_filters(analysis: Dict[str, Any], season_month: str) -> bool:
    """
    Проверяет, проходит ли ниша фильтры из ТЗ.
    Часть критериев воспроизводим приблизительно на основе имеющихся данных.
    """
    revenue = float(analysis.get("revenue_per_month") or 0)
    sellers = int(analysis.get("sellers_count") or 0)
    buyout = float(analysis.get("buyout_rate") or 0)
    noname = float(analysis.get("noname_share") or 0)
    top1 = float(analysis.get("top1_share") or 0)
    trend = analysis.get("trend", "stable")

    # Выручка ниши растёт (по тренду)
    if trend != "growth":
        return False

    # Монополистов нет
    if top1 >= 0.3:
        return False

    # no-name > 20%
    if noname <= 0.2:
        return False

    # % выкупа > 40%
    if buyout <= 0.4:
        return False

    # Продажи > 1000 шт/мес в нише (приблизительно оцениваем как выручка / средняя цена)
    avg_price = 1000.0
    approx_units = revenue / avg_price if avg_price > 0 else 0
    if approx_units <= 1000:
        return False

    # Сезонность — если задан месяц, он должен входить в топ-месяцы
    if season_month:
        months = [m.lower() for m in analysis.get("seasonality_top_months", [])]
        if season_month.lower() not in months:
            return False

    return True


async def send_autopick_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    index: int,
    item: Dict[str, Any],
    budget: float,
    platform: str,
    has_token: bool,
) -> None:
    """
    Формирует и отправляет текстовую карточку для одного подобранного товара.
    """
    analysis = item["analysis"]
    comp = item["comp"]
    query_text = item["query"]
    category = item["category"]

    name = comp.get("name") or query_text
    sale_price = float(comp.get("price") or 0)
    sales_per_month = int(comp.get("sales_per_month") or 0)

    # Поиск на 1688
    china_result = build_1688_search(name)

    # В демо режиме закупочную цену берём как 20% от цены продажи,
    # переведённую в юани по курсу ЦБ.
    if has_token:
        # Здесь в реальном режиме можно реализовать парсинг 1688.
        purchase_rub = sale_price * 0.2
    else:
        purchase_rub = sale_price * 0.2

    purchase_cny = purchase_rub / china_result.cny_to_rub if china_result.cny_to_rub > 0 else 0

    # Берём средние значения WB из constants.py
    d = WB_DEFAULTS

    # Для простоты считаем средний вес и объём,
    # в реальном режиме эти параметры можно уточнять.
    weight_kg = 0.5
    volume_l = 2.0

    # Курс «доллар→рубль» на основе курса юаня (приближение)
    cny_rate = china_result.cny_to_rub
    usd_rate = cny_rate * 2

    commission_percent = d.commission_default
    spp_percent = d.spp_percent_default
    ads_percent = d.ads_percent_default
    tax_mode = d.tax_mode_default

    # Считаем юнит-экономику через общий калькулятор
    inp = CalcInput(
        purchase_price=purchase_rub,
        weight_kg=weight_kg,
        volume_l=volume_l,
        platform="wb" if platform == "wb" else "ozon",
        commission_percent=commission_percent,
        spp_percent=spp_percent,
        tax_mode=tax_mode,
        logistics_usd_per_kg=d.logistics_usd_per_kg,
        logistics_usd_to_rub=usd_rate,
        fulfillment_rub_per_item=d.fulfillment_rub_per_item_default,
        ads_percent=ads_percent,
        other_expenses_rub=d.other_expenses_rub_default,
        budget_rub=budget,
    )

    calc = calculate_unit_economics(
        inputs=inp,
        sale_price=sale_price,
        is_niche_growing=(analysis.get("trend") == "growth"),
    )

    # Подробный разбор расходов
    wb_commission = sale_price * commission_percent / 100
    wb_logistics = d.logistics_rub_per_unit
    wb_storage = d.storage_rub_per_liter_per_day * volume_l * 30
    spp = sale_price * spp_percent / 100
    cn_logistics = d.logistics_usd_per_kg * usd_rate * weight_kg
    ads_cost = sale_price * ads_percent / 100
    ff = d.fulfillment_rub_per_item_default
    other_per_unit = (
        d.other_expenses_rub_default / calc.units_by_budget if calc.units_by_budget else 0
    )

    # Налог считаем из разницы дохода и суммарных затрат до налога
    pre_tax_margin = (
        sale_price
        - wb_commission
        - wb_logistics
        - wb_storage
        - spp
        - purchase_rub
        - cn_logistics
        - ads_cost
        - ff
        - other_per_unit
    )
    if tax_mode == "usn_6":
        tax = max(pre_tax_margin, 0) * 0.06
    else:
        tax = max(pre_tax_margin, 0) * 0.15

    net_profit_per_unit = pre_tax_margin - tax

    # Данные ниши
    revenue = float(analysis.get("revenue_per_month") or 0)
    sellers = int(analysis.get("sellers_count") or 0)
    buyout = float(analysis.get("buyout_rate") or 0)
    trend = analysis.get("trend", "stable")
    trend_text = "СТАБИЛЬНО"
    if trend == "growth":
        trend_text = "▲ РОСТ"
    elif trend == "fall":
        trend_text = "▼ ПАДЕНИЕ"

    missed_revenue = float(analysis.get("missed_revenue_amount") or 0)

    # Топ-3 конкурента для отображения с расшифровкой
    top3_lines = []
    for i, c in enumerate(analysis.get("top_competitors", [])[:3], start=1):
        cname = c.get("name") or "—"
        cprice = float(c.get("price") or 0)
        csales = int(c.get("sales_per_month") or 0)
        crating = float(c.get("rating") or 0)
        # Выручка конкурента = цена × продажи/мес
        crevenue = cprice * csales
        # Если нет индивидуального % выкупа — берём общий по нише
        cbuyout = float(c.get("buyout_rate") or buyout) * 100

        top3_lines.append(
            f"{i}. {cname}\n"
            f"   💰 Цена: {cprice:,.0f} ₽\n"
            f"   📦 Продаж: {csales} шт/мес\n"
            f"   💵 Выручка: {crevenue:,.0f} ₽/мес\n"
            f"   ⭐ Рейтинг: {crating:.1f}\n"
            f"   🔄 Выкуп: {cbuyout:.0f}%"
        )
    if not top3_lines:
        top3_lines.append("Нет данных по конкурентам.")

    demo_tag = "(демо) " if (analysis.get("demo") or not has_token) else ""

    card = (
        "═══════════════════════\n"
        f"🎯 ТОВАР: {name}\n"
        f"📦 Категория: {category}\n"
        "═══════════════════════\n\n"
        f"📊 ДАННЫЕ НИШИ {demo_tag}:\n"
        f"- Выручка ниши: {revenue:,.0f} руб/мес\n"
        f"- Продавцов: {sellers}\n"
        f"- % выкупа: {buyout*100:.1f}%\n"
        f"- Тренд: {trend_text}\n"
        f"- Монополист: ❌ Нет\n"
        f"- Упущенная выручка: {missed_revenue:,.0f} руб/мес\n\n"
        "🏆 КОНКУРЕНТЫ (топ-3):\n"
        + "\n".join(top3_lines)
        + "\n\n"
        f"🇨🇳 ЗАКУПКА НА 1688:\n"
        f"- Примерная цена: {purchase_cny:.2f}¥ ({purchase_rub:.0f}₽)\n"
        f"- Партия на бюджет: {calc.units_by_budget} шт\n"
        f"- Ссылка: {china_result.search_url}\n\n"
        "💰 ЮНИТ-ЭКОНОМИКА:\n"
        f"- Цена продажи: {sale_price:.0f}₽\n"
        f"- Себестоимость (полная): {calc.full_cost_per_unit:.0f}₽/шт\n"
        f"- Маржинальность: {calc.margin_percent:.1f}%\n"
        f"- ROI: {calc.roi_percent:.1f}%\n"
        f"- Окупаемость: {calc.payback_months:.1f} мес\n"
        f"- Прибыль/мес: {calc.profit_per_month:.0f}₽\n\n"
        f"{calc.verdict} ВЕРДИКТ\n\n"
        "ЦЕНА ПРОДАЖИ: {price:.0f} ₽\n"
        "─────────────────────\n"
        f"ВЫЧИТАЕМ:\n"
        f"- Комиссия ВБ ({commission_percent:.0f}%):        — {wb_commission:.0f} ₽\n"
        f"- Логистика ВБ (среднее):   — {wb_logistics:.0f} ₽\n"
        f"- Хранение ВБ (среднее):    — {wb_storage:.0f} ₽\n"
        f"- СПП ({spp_percent:.0f}%):                 — {spp:.0f} ₽\n"
        f"- Себестоимость товара:     — {purchase_rub:.0f} ₽\n"
        f"- Логистика из Китая:       — {cn_logistics:.0f} ₽\n"
        f"- Реклама ({ads_percent:.0f}%):            — {ads_cost:.0f} ₽\n"
        f"- Налог УСН:                 — {tax:.0f} ₽\n"
        f"- Фулфилмент:               — {ff:.0f} ₽\n"
        f"- Прочие (/ед.):            — {other_per_unit:.0f} ₽\n"
        "─────────────────────\n"
        f"ЧИСТАЯ ПРИБЫЛЬ:              {net_profit_per_unit:.0f} ₽/шт\n\n"
        "⚠️ Расчёт ориентировочный — логистика и хранение зависят от конкретного склада WB.\n"
        "═══════════════════════"
    ).format(price=sale_price)

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🇨🇳 Открыть на 1688", url=china_result.search_url)],
        ]
    )

    await update.effective_chat.send_message(card, reply_markup=keyboard)


# ===== НАСТРОЙКИ =====


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_access(update, context):
        return
    token = get_mpstats_token(update.effective_user.id)
    token_status = "✅ задан" if token else "❌ не задан"
    text = (
        "⚙️ Настройки:\n"
        f"- MPStats токен: {token_status} (команда /settoken)\n"
        "- История анализов: /history\n"
        "- Ваш Telegram ID: /myid\n"
    )
    await update.effective_chat.send_message(text)


# ===== РОУТЕР КНОПОК =====


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    # Диалоги (анализ ниши, калькулятор, подбор товара, поиск на 1688)
    # обрабатываются через ConversationHandler, поэтому здесь
    # оставляем только простые действия.
    if text.startswith("📊"):
        await history_cmd(update, context)
    elif text.startswith("⚙️"):
        await settings_menu(update, context)
    elif text.startswith("👁"):
        await history_cmd(update, context)
    else:
        await update.effective_chat.send_message(
            "Не понял сообщение. Используйте кнопки в меню или команды."
        )


# ===== СОЗДАНИЕ ПРИЛОЖЕНИЯ =====


def build_application() -> Application:
    """
    Создаёт и настраивает экземпляр Telegram Application.
    Используется в run.py.
    """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    app = ApplicationBuilder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("adduser", adduser_cmd))
    app.add_handler(CommandHandler("removeuser", removeuser_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    token_conv = ConversationHandler(
        entry_points=[CommandHandler("settoken", settoken_start)],
        states={
            TokenStates.TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settoken_save)
            ]
        },
        fallbacks=[CommandHandler("cancel", settoken_cancel)],
    )
    app.add_handler(token_conv)
    analyze_conv = ConversationHandler(
        entry_points=[
            CommandHandler("analyze", analyze_entry),
            MessageHandler(filters.Regex(r"^🔍 Анализ ниши"), analyze_entry),
        ],
        states={
            AnalyzeStates.KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_keyword)
            ],
            AnalyzeStates.BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_budget)
            ],
            AnalyzeStates.PLATFORM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_platform)
            ],
            AnalyzeStates.PERIOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_period)
            ],
        },
        fallbacks=[CommandHandler("cancel", analyze_entry)],
    )
    app.add_handler(analyze_conv)
    # Калькулятор — вынесен в отдельный модуль calculator_handler.py
    app.add_handler(build_calculator_conv())

    # Автоподбор товара
    autopick_conv = ConversationHandler(
        entry_points=[
            CommandHandler("autopick", autopick_entry),
            MessageHandler(filters.Regex(r"^🎯 Подобрать товар"), autopick_entry),
        ],
        states={
            AutoPickStates.BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, autopick_budget)
            ],
            AutoPickStates.PLATFORM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, autopick_platform)
            ],
            AutoPickStates.MONTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, autopick_season)
            ],
        },
        fallbacks=[CommandHandler("cancel", autopick_cancel)],
    )
    app.add_handler(autopick_conv)

    china_conv = ConversationHandler(
        entry_points=[
            CommandHandler("china", china_entry),
            MessageHandler(filters.Regex(r"^🇨🇳 Найти на 1688"), china_entry),
        ],
        states={
            ChinaStates.QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, china_query)
            ]
        },
        fallbacks=[CommandHandler("cancel", china_cancel)],
    )
    app.add_handler(china_conv)
    app.add_handler(CallbackQueryHandler(watch_add_callback, pattern=r"^watch_add:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    return app


__all__ = ["build_application"]
