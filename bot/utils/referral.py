from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User


async def count_referrals(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(select(func.count(User.id)).where(User.referred_by_id == user_id))
    return result.scalar_one()


async def get_referred_users(session: AsyncSession, user_id: int, limit: int = 15) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.referred_by_id == user_id)
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_referral_leaderboard(session: AsyncSession, limit: int = 20) -> list[tuple[User, int]]:
    """
    خروجی: لیست (کاربر معرف, تعداد رفرالش) مرتب‌شده نزولی بر اساس تعداد رفرال.
    این سراسریه (روی کل ربات، نه محدود به یک روم) چون ادمین باید تصویر کامل رو ببینه.
    """
    result = await session.execute(
        select(User.referred_by_id, func.count(User.id).label("cnt"))
        .where(User.referred_by_id.isnot(None))
        .group_by(User.referred_by_id)
        .order_by(func.count(User.id).desc())
        .limit(limit)
    )
    rows = result.all()

    leaderboard: list[tuple[User, int]] = []
    for referrer_id, cnt in rows:
        referrer = await session.get(User, referrer_id)
        if referrer is not None:
            leaderboard.append((referrer, cnt))
    return leaderboard
