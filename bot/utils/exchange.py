from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import User
from bot.utils.game_settings import get_int_setting, get_str_setting, set_int_setting, set_str_setting

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
_PRICE_UPDATED_KEY_PREFIX = "exchange_price_updated_"
_MARKUP_KEY = "exchange_buy_markup_percent"


def _price_bounds(resource_type: str) -> tuple[int, int]:
    base = DEFAULT_SELL_PRICES[resource_type]
    low = max(1, round(base * settings.EXCHANGE_PRICE_MIN_MULTIPLIER))
    high = max(low + 1, round(base * settings.EXCHANGE_PRICE_MAX_MULTIPLIER))
    return low, high


async def _reverted_price(session: AsyncSession, resource_type: str, current_price: int) -> int:
    """
    هرچی زمان بیشتری از آخرین معامله‌ی این منبع گذشته باشه، قیمت به‌آرومی به
    سمت قیمت پایه (تعادلی) برمی‌گرده - تا وقتی کسی معامله نمی‌کنه، بازار
    آروم آروم به حالت عادی برگرده.
    """
    base = DEFAULT_SELL_PRICES[resource_type]
    updated_raw = await get_str_setting(session, f"{_PRICE_UPDATED_KEY_PREFIX}{resource_type}", "")
    if not updated_raw:
        return current_price
    try:
        last_updated = datetime.fromisoformat(updated_raw)
    except ValueError:
        return current_price

    hours_passed = (datetime.utcnow() - last_updated).total_seconds() / 3600
    if hours_passed <= 0:
        return current_price

    reversion_percent = min(100.0, settings.EXCHANGE_PRICE_REVERSION_PERCENT_PER_HOUR * hours_passed)
    reverted = current_price + (base - current_price) * (reversion_percent / 100)
    return round(reverted)


async def get_sell_price(session: AsyncSession, resource_type: str) -> int:
    """
    قیمت فعلی بازار برای این منبع. دیگه ثابت/دستی نیست: با هر خرید/فروش
    واقعی بازیکن‌ها جابه‌جا میشه (عرضه زیاد بشه ارزون‌تر، تقاضا زیاد بشه
    گرون‌تر) و با گذر زمان به‌آرومی به سمت قیمت پایه برمی‌گرده.
    """
    default = DEFAULT_SELL_PRICES[resource_type]
    current = await get_int_setting(session, f"{_PRICE_KEY_PREFIX}{resource_type}", default)
    return await _reverted_price(session, resource_type, current)


async def set_sell_price(session: AsyncSession, resource_type: str, price: int) -> None:
    """تنظیم دستی توسط ادمین (مثلاً برای ریست کردن بازار به یه قیمت مشخص)."""
    await set_int_setting(session, f"{_PRICE_KEY_PREFIX}{resource_type}", price)
    await set_str_setting(session, f"{_PRICE_UPDATED_KEY_PREFIX}{resource_type}", datetime.utcnow().isoformat())


async def _shift_price_after_trade(session: AsyncSession, resource_type: str, quantity: int, direction: int) -> None:
    """
    direction=+1: بازیکن از ربات خرید (تقاضا) - قیمت میره بالا.
    direction=-1: بازیکن به ربات فروخت (عرضه) - قیمت میاد پایین.
    """
    if quantity <= 0:
        return
    current = await get_sell_price(session, resource_type)
    low, high = _price_bounds(resource_type)
    impact = current * (settings.EXCHANGE_PRICE_IMPACT_PERCENT / 100) * quantity
    new_price = max(low, min(high, round(current + direction * impact)))
    await set_int_setting(session, f"{_PRICE_KEY_PREFIX}{resource_type}", new_price)
    await set_str_setting(session, f"{_PRICE_UPDATED_KEY_PREFIX}{resource_type}", datetime.utcnow().isoformat())


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

    # عرضه‌ی این منبع به بازار زیاد شد - قیمتش کمی می‌افته
    await _shift_price_after_trade(session, resource_type, quantity, direction=-1)

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

    # تقاضا برای این منبع زیاد شد - قیمتش کمی می‌ره بالا
    await _shift_price_after_trade(session, resource_type, actual_quantity, direction=1)

    msg = f"✅ {actual_quantity} {RESOURCE_LABELS[resource_type]} خریدی و 💰{actual_cost} پرداخت کردی."
    if actual_quantity < quantity:
        msg += "\n(به خاطر محدودیت انبار یا طلا، کمتر از درخواستت خریداری شد.)"
    return msg, None
