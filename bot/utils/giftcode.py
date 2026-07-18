import random
import string

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import GiftCode, GiftCodeRedemption, User


def generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


async def create_gift_code(
    session: AsyncSession,
    admin_telegram_id: int,
    gold_reward: int,
    max_uses: int,
    custom_code: str | None = None,
) -> GiftCode | str:
    """خروجی: GiftCode در صورت موفقیت، وگرنه پیام خطا (str)."""
    if gold_reward <= 0:
        return "تعداد طلا باید مثبت باشه."
    if max_uses <= 0:
        return "تعداد دفعات استفاده باید مثبت باشه."

    code = (custom_code or generate_code()).strip().upper()
    if not code or len(code) > 32:
        return "کد نامعتبره (حداکثر ۳۲ کاراکتر)."

    result = await session.execute(select(GiftCode).where(GiftCode.code == code))
    if result.scalar_one_or_none() is not None:
        return "این کد از قبل وجود داره، یه کد دیگه انتخاب کن."

    gift_code = GiftCode(
        code=code,
        gold_reward=gold_reward,
        max_uses=max_uses,
        created_by_telegram_id=admin_telegram_id,
    )
    session.add(gift_code)
    await session.flush()
    return gift_code


async def redeem_gift_code(session: AsyncSession, user: User, code_str: str) -> tuple[int | None, str | None]:
    """خروجی: (سکه‌ی دریافتی, پیام خطا) - دقیقاً یکی از این دو پر میشه."""
    code_str = (code_str or "").strip().upper()
    if not code_str:
        return None, "کد رو وارد کن. مثال: /redeem ABCD1234"

    result = await session.execute(select(GiftCode).where(GiftCode.code == code_str))
    gift_code = result.scalar_one_or_none()
    if gift_code is None:
        return None, "این کد هدیه پیدا نشد."
    if not gift_code.active:
        return None, "این کد هدیه دیگه فعال نیست."
    if gift_code.uses_count >= gift_code.max_uses:
        return None, "ظرفیت استفاده از این کد تموم شده."

    result = await session.execute(
        select(GiftCodeRedemption).where(
            GiftCodeRedemption.gift_code_id == gift_code.id,
            GiftCodeRedemption.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return None, "قبلاً این کد رو استفاده کردی."

    gift_code.uses_count += 1
    user.gold += gift_code.gold_reward
    session.add(GiftCodeRedemption(gift_code_id=gift_code.id, user_id=user.id))

    return gift_code.gold_reward, None


async def get_recent_gift_codes(session: AsyncSession, limit: int = 15) -> list[GiftCode]:
    result = await session.execute(select(GiftCode).order_by(GiftCode.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def deactivate_gift_code(session: AsyncSession, code_str: str) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا."""
    code_str = (code_str or "").strip().upper()
    result = await session.execute(select(GiftCode).where(GiftCode.code == code_str))
    gift_code = result.scalar_one_or_none()
    if gift_code is None:
        return "این کد هدیه پیدا نشد."
    gift_code.active = False
    return None
