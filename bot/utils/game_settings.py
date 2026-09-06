from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AllianceWar, GameSetting

# ---------------------------------------------------------------------------
# تنظیمات سراسری قابل‌تغییر در لحظه توسط ادمین (بدون نیاز به ری‌دیپلوی)
# ---------------------------------------------------------------------------
WARS_ENABLED_KEY = "wars_enabled"
UNIT_PRICE_DISCOUNT_KEY = "unit_price_discount_percent"


async def get_bool_setting(session: AsyncSession, key: str, default: bool) -> bool:
    row = await session.get(GameSetting, key)
    if row is None:
        return default
    return row.value == "1"


async def set_bool_setting(session: AsyncSession, key: str, value: bool) -> None:
    row = await session.get(GameSetting, key)
    if row is None:
        row = GameSetting(key=key, value="1" if value else "0")
        session.add(row)
    else:
        row.value = "1" if value else "0"


async def get_int_setting(session: AsyncSession, key: str, default: int) -> int:
    row = await session.get(GameSetting, key)
    if row is None:
        return default
    try:
        return int(row.value)
    except ValueError:
        return default


async def set_int_setting(session: AsyncSession, key: str, value: int) -> None:
    row = await session.get(GameSetting, key)
    if row is None:
        row = GameSetting(key=key, value=str(value))
        session.add(row)
    else:
        row.value = str(value)


async def get_str_setting(session: AsyncSession, key: str, default: str) -> str:
    row = await session.get(GameSetting, key)
    if row is None or not row.value:
        return default
    return row.value


async def set_str_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(GameSetting, key)
    if row is None:
        row = GameSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value


async def are_wars_enabled(session: AsyncSession) -> bool:
    return await get_bool_setting(session, WARS_ENABLED_KEY, default=True)


async def set_wars_enabled(session: AsyncSession, enabled: bool) -> int:
    """
    فعال/غیرفعال می‌کنه. اگه غیرفعال بشه، همه‌ی جنگ‌های در حال انجام (تو همه‌ی
    روم‌ها) فوراً لغو میشن (status='cancelled').
    خروجی: تعداد جنگ‌هایی که لغو شدن (فقط وقتی enabled=False باشه، وگرنه ۰).
    """
    await set_bool_setting(session, WARS_ENABLED_KEY, enabled)

    cancelled_count = 0
    if not enabled:
        result = await session.execute(select(AllianceWar).where(AllianceWar.status == "active"))
        active_wars = list(result.scalars().all())
        for war in active_wars:
            war.status = "cancelled"
            cancelled_count += 1
    return cancelled_count


async def get_unit_price_discount_percent(session: AsyncSession) -> int:
    """درصد تخفیفی که ادمین از پنل روی هزینه‌ی ساخت همه‌ی نیروها گذاشته (پیش‌فرض ۲۰٪)."""
    return await get_int_setting(session, UNIT_PRICE_DISCOUNT_KEY, default=20)


async def set_unit_price_discount_percent(session: AsyncSession, percent: int) -> None:
    percent = max(0, min(95, percent))
    await set_int_setting(session, UNIT_PRICE_DISCOUNT_KEY, percent)


# ---------------------------------------------------------------------------
# اطلاعات کارت بانکی فروشگاه (قابل تغییر از پنل ادمین، بدون نیاز به ری‌دیپلوی)
# ---------------------------------------------------------------------------
PAYMENT_CARD_NUMBER_KEY = "payment_card_number"
PAYMENT_CARD_HOLDER_KEY = "payment_card_holder_name"


async def get_payment_card_number(session: AsyncSession) -> str:
    from bot.config import settings

    return await get_str_setting(session, PAYMENT_CARD_NUMBER_KEY, settings.PAYMENT_CARD_NUMBER)


async def set_payment_card_number(session: AsyncSession, value: str) -> None:
    await set_str_setting(session, PAYMENT_CARD_NUMBER_KEY, value.strip())


async def get_payment_card_holder(session: AsyncSession) -> str:
    from bot.config import settings

    return await get_str_setting(session, PAYMENT_CARD_HOLDER_KEY, settings.PAYMENT_CARD_HOLDER_NAME)


async def set_payment_card_holder(session: AsyncSession, value: str) -> None:
    await set_str_setting(session, PAYMENT_CARD_HOLDER_KEY, value.strip())
