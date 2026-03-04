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
    PURCHASE_PRICE = auto()
    CURRENCY = auto()
    WEIGHT = auto()
    VOLUME = auto()
    PLATFORM = auto()
    COMMISSION = auto()
    SPP = auto()
    TAX = auto()
    LOGISTICS = auto()
    FULFILLMENT = auto()
    ADS = auto()
    OTHER_EXPENSES = auto()
    BUDGET = auto()
    SALE_PRICE = auto()
    NICHE_GROWTH = auto()


class ChinaStates(IntEnum):
    QUERY = auto()


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Главное меню бота с кнопками из ТЗ.
    """
    kb = [
        [
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
                web_app=WebAppInfo(url=getattr(settings, "webapp_url", "https://example.com")),
            ),
        ],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


def access_denied_text() -> str:
    """
    Сообщение при отсутствии доступа.
    """
    return "⛔ Доступ закрыт. Напишите администратору @olgapshedromirskaya"


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
    Показывает главное меню. Если пользователь ещё не в whitelist,
    даём понять, что доступ ограничен.
    """
    user = update.effective_user
    text = (
        "👋 Привет! Это бот анализа ниш маркетплейсов.\n\n"
        "Используйте кнопки в меню ниже.\n\n"
        "Команда /myid покажет ваш Telegram ID."
    )
    if not user_allowed(update):
        text += "\n\n" + access_denied_text()

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
    """
    /adduser [user_id] — добавить пользователя в whitelist.
    Доступно только администратору.
    """
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
    """
    /removeuser [user_id] — заблокировать пользователя.
    """
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
    """
    /users — список всех пользователей.
    """
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
    """
    Старт команды /settoken — просим прислать токен.
    """
    if not await ensure_access(update, context):
        return ConversationHandler.END

    await update.effective_chat.send_message(
        "Пожалуйста, отправьте ваш MPStats API токен одним сообщением."
    )
    return TokenStates.TOKEN


async def settoken_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Сохраняем токен в базе.
    """
    token = update.message.text.strip()
    if not token:
        await update.effective_chat.send_message("Токен не может быть пустым, попробуйте ещё раз.")
        return TokenStates.TOKEN

    set_mpstats_token(update.effective_user.id, token)
    await update.effective_chat.send_message("✅ Токен сохранён.")
    return ConversationHandler.END


async def settoken_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отмена установки токена.
    """
    await update.effective_chat.send_message("Отменено.")
    return ConversationHandler.END


# ===== АНАЛИЗ НИШИ =====


async def analyze_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Старт диалога анализа ниши.
    """
    if not await ensure_access(update, context):
        return ConversationHandler.END

    await update.effective_chat.send_message(
        "🔍 Введите ключевое слово или категорию для анализа."
    )
    return AnalyzeStates.KEYWORD


async def analyze_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг 1 — получаем ключевое слово.
    """
    context.user_data["an_query"] = update.message.text.strip()
    await update.effective_chat.send_message("Введите бюджет в рублях.")
    return AnalyzeStates.BUDGET


async def analyze_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Шаг 2 — бюджет.
    """
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
    """
    Шаг 3 — платформа.
    """
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
    """
    Шаг 4 — период, затем вызываем MPStats и показываем результат.
    """
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

    # Сохраняем анализ в БД (вердикт оставляем пустым, если калькулятор не вызывался)
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
    """
    Обработчик callback-кнопки «Добавить в отслеживание».
    Находим анализ в истории по ID и создаём запись в watchlist.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    try:
        _, sid = data.split(":", 1)
        analysis_id = int(sid)
    except Exception:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    # Берём последний анализ в истории, чтобы вытащить значения.
    # Для простоты не дублируем логику: повторный анализ пользователь
    # может сделать вручную.
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


# ===== ИСТОРИЯ АНАЛИЗОВ =====


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /history или кнопка «📊 История анализов».
    Показывает последние 5 анализов.
    """
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
    """
    Старт диалога финансового калькулятора.
    """
    if not await ensure_access(update, context):
        return ConversationHandler.END

    await update.effective_chat.send_message(
        "💰 Финансовый калькулятор.\n"
        "Сначала введите цену закупки за единицу (в рублях или юанях)."
    )
    return CalcStates.PURCHASE_PRICE


async def calc_purchase_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Цена закупки.
    """
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Не смог понять число, попробуйте ещё раз.")
        return CalcStates.PURCHASE_PRICE

    context.user_data["calc_purchase_price"] = price
    kb = ReplyKeyboardMarkup([["RUB", "CNY"]], resize_keyboard=True, one_time_keyboard=True)
    await update.effective_chat.send_message(
        "В какой валюте цена закупки? RUB или CNY.", reply_markup=kb
    )
    return CalcStates.CURRENCY


async def calc_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Валюта закупки — при необходимости конвертируем в рубли.
    """
    cur = update.message.text.strip().upper()
    price = context.user_data["calc_purchase_price"]

    if cur == "CNY":
        rate = get_cny_rate_rub()
        price_rub = price * rate
        context.user_data["calc_purchase_price_rub"] = price_rub
        await update.effective_chat.send_message(
            f"Конвертирую {price} CNY по курсу {rate:.2f} → {price_rub:.2f} ₽."
        )
    else:
        context.user_data["calc_purchase_price_rub"] = price

    await update.effective_chat.send_message("Введите вес товара (кг).")
    return CalcStates.WEIGHT


async def calc_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вес товара.
    """
    try:
        w = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (кг).")
        return CalcStates.WEIGHT

    context.user_data["calc_weight"] = w
    await update.effective_chat.send_message("Введите объём товара (литры).")
    return CalcStates.VOLUME


async def calc_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Объём товара.
    """
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
    """
    Платформа + значение комиссии по умолчанию.
    """
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
    """
    Комиссия маркетплейса.
    """
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
    """
    СПП.
    """
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
    """
    Налоговый режим.
    """
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
    """
    Логистика $/кг.
    """
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
    """
    Фулфилмент.
    """
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
    """
    Реклама.
    """
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
    """
    Прочие расходы.
    """
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
    """
    Бюджет.
    """
    try:
        budget = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.effective_chat.send_message("Введите число (рубли).")
        return CalcStates.BUDGET

    context.user_data["calc_budget"] = budget
    await update.effective_chat.send_message("Планируемая цена продажи (руб):")
    return CalcStates.SALE_PRICE


async def calc_sale_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Цена продажи.
    """
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
    """
    Финальный шаг — считаем юнит-экономику и показываем результат.
    """
    txt = update.message.text.strip().lower()
    is_growing = txt.startswith("д")  # «да»

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

    # Берём курс доллара из курса юаня (упрощение)
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
    """
    Отмена калькулятора.
    """
    await update.effective_chat.send_message("Калькулятор отменён.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ===== ПОИСК НА 1688 =====


async def china_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Старт диалога поиска на 1688.
    """
    if not await ensure_access(update, context):
        return ConversationHandler.END

    await update.effective_chat.send_message(
        "🇨🇳 Введите запрос на русском языке, я переведу его и подготовлю ссылку для 1688."
    )
    return ChinaStates.QUERY


async def china_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получаем запрос и отвечаем ссылкой.
    """
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
    """
    Отмена диалога 1688.
    """
    await update.effective_chat.send_message("Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


# ===== НАСТРОЙКИ =====


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Кнопка «⚙️ Настройки» — показываем краткую подсказку.
    """
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


# ===== ОБРАБОТКА ТЕКСТОВЫХ КНОПОК МЕНЮ =====


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Роутер для текстовых кнопок главного меню.
    """
    text = update.message.text.strip()

    if text.startswith("🔍"):
        await analyze_entry(update, context)
    elif text.startswith("💰"):
        await calc_entry(update, context)
    elif text.startswith("🇨🇳"):
        await china_entry(update, context)
    elif text.startswith("📊"):
        await history_cmd(update, context)
    elif text.startswith("⚙️"):
        await settings_menu(update, context)
    elif text.startswith("👁"):
        # Для простоты просто открываем историю и предлагаем включить отслеживание
        await history_cmd(update, context)
    else:
        await update.effective_chat.send_message(
            "Не понял сообщение. Используйте кнопки в меню или команды."
        )


# ===== СОЗДАНИЕ ПРИЛОЖЕНИЯ TELEGRAM-БОТА =====


def build_application() -> Application:
    """
    Создаёт и настраивает экземпляр Telegram Application без запуска.
    Его будет запускать run.py.
    """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    app = ApplicationBuilder().token(settings.telegram_token).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("adduser", adduser_cmd))
    app.add_handler(CommandHandler("removeuser", removeuser_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("history", history_cmd))

    # Диалог установки токена
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

    # Диалог анализа ниши
    analyze_conv = ConversationHandler(
        entry_points=[
            CommandHandler("analyze", analyze_entry),
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

    # Диалог калькулятора
    calc_conv = ConversationHandler(
        entry_points=[CommandHandler("calc", calc_entry)],
        states={
            CalcStates.PURCHASE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_purchase_price)
            ],
            CalcStates.CURRENCY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_currency)
            ],
            CalcStates.WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_weight)
            ],
            CalcStates.VOLUME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_volume)
            ],
            CalcStates.PLATFORM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_platform)
            ],
            CalcStates.COMMISSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_commission)
            ],
            CalcStates.SPP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_spp)
            ],
            CalcStates.TAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_tax)
            ],
            CalcStates.LOGISTICS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_logistics)
            ],
            CalcStates.FULFILLMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_fulfillment)
            ],
            CalcStates.ADS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_ads)
            ],
            CalcStates.OTHER_EXPENSES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_other)
            ],
            CalcStates.BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_budget)
            ],
            CalcStates.SALE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_sale_price)
            ],
            CalcStates.NICHE_GROWTH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calc_niche_growth)
            ],
        },
        fallbacks=[CommandHandler("cancel", calc_cancel)],
    )
    app.add_handler(calc_conv)

    # Диалог поиска на 1688
    china_conv = ConversationHandler(
        entry_points=[CommandHandler("china", china_entry)],
        states={
            ChinaStates.QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, china_query)
            ]
        },
        fallbacks=[CommandHandler("cancel", china_cancel)],
    )
    app.add_handler(china_conv)

    # Callback для добавления в отслеживание
    app.add_handler(CallbackQueryHandler(watch_add_callback, pattern=r"^watch_add:"))

    # Роутер текстовых сообщений (кнопки меню)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    return app


__all__ = ["build_application"]

