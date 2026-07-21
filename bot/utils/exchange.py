from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import User
from bot.utils.game_settings import get_int_setting, set_int_setting

DEFAULT_SELL_PRICES = {
    "iron": settings.EXCHANGE_SELL_PRICE_IRON,
    "oil": settings.EXCHANGE_SELL_PRICE_OIL,
    "food": settings.EXCHANGE_SELL_PRICE_FOOD,
    "uranium": settings.EXCHANGE_SELL_PRICE_URANIUM,
}

RESOURCE_LABELS = {
    "iron": "⛏️ آهن",
    "oil": "🛢️ نفت",
    "food": "🌾 غذا",
    "uranium": "☢️ اورانیوم",
}

_PRICE_KEY_PREFIX = "exchange_price_"
_MARKUP_KEY = "exchange_buy_markup_percent"


async def get_sell_price(session: AsyncSession, resource_type: str) -> int:
    """قیمتی که ربات این منبع رو می‌خره (قابل تغییر توسط ادمین، وگرنه پیش‌فرض config)."""
    default = DEFAULT_SELL_PRICES[resource_type]
    return await get_int_setting(session, f"{_PRICE_KEY_PREFIX}{resource_type}", default)


async def set_sell_price(session: AsyncSession, resource_type: str, price: int) -> None:
    await set_int_setting(session, f"{_PRICE_KEY_PREFIX}{resource_type}", price)


async def get_all_sell_prices(session: AsyncSession) -> dict[str, int]:
    return {rt: await get_sell_price(session, rt) for rt in DEFAULT_SELL_PRICES}


async def get_buy_markup_percent(session: AsyncSession) -> int:
    return await get_int_setting(session, _MARKUP_KEY, settings.EXCHANGE_BUY_MARKUP_PERCENT)


async def set_buy_markup_percent(session: AsyncSession, percent: int) -> None:
    await set_int_setting(session, _MARKUP_KEY, percent)


async def buy_price(session: AsyncSession, resource_type: str) -> int:
    sell = await get_sell_price(session, resource_type)
    markup = await get_buy_markup_percent(session)
    return max(sell + 1, round(sell * (1 + markup / 100)))


async def sell_resource(
    session: AsyncSession, user: User, resource_type: str, quantity: int
) -> tuple[str | None, str | None]:
    """خروجی: (پیام موفقیت, پیام خطا) - دقیقاً یکی از این دو پر میشه."""
    if quantity <= 0:
        return None, "تعداد باید مثبت باشه."
    current = getattr(user, resource_type)
    if current < quantity:
        return None, f"به این مقدار {RESOURCE_LABELS[resource_type]} نداری."

    sell_price = await get_sell_price(session, resource_type)
    gold_gained = sell_price * quantity
    setattr(user, resource_type, current - quantity)
    user.gold += gold_gained
    return f"✅ {quantity} {RESOURCE_LABELS[resource_type]} فروختی و 💰{gold_gained} گرفتی.", None


async def buy_resource(
    session: AsyncSession, user: User, resource_type: str, quantity: int
) -> tuple[str | None, str | None]:
    """خروجی: (پیام موفقیت, پیام خطا) - دقیقاً یکی از این دو پر میشه."""
    if quantity <= 0:
        return None, "تعداد باید مثبت باشه."

    price = await buy_price(session, resource_type)
    max_field = f"max_{resource_type}"
    current = getattr(user, resource_type)
    cap = getattr(user, max_field)

    if current >= cap:
        return None, "انبارت پره، جا برای این منبع نداری."

    actual_quantity = min(quantity, cap - current)
    actual_cost = price * actual_quantity
    if user.gold < actual_cost:
        # با طلای موجود، حداکثر چقدر می‌تونه بخره
        affordable = user.gold // price
        if affordable <= 0:
            return None, f"طلای کافی نداری. هر واحد {RESOURCE_LABELS[resource_type]} = 💰{price}"
        actual_quantity = min(actual_quantity, affordable)
        actual_cost = price * actual_quantity

    user.gold -= actual_cost
    setattr(user, resource_type, current + actual_quantity)

    msg = f"✅ {actual_quantity} {RESOURCE_LABELS[resource_type]} خریدی و 💰{actual_cost} پرداخت کردی."
    if actual_quantity < quantity:
        msg += "\n(به خاطر محدودیت انبار یا طلا، کمتر از درخواستت خریداری شد.)"
    return msg, None
