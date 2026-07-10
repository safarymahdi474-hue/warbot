from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import AchievementType, User, UserAchievement
from bot.utils.progression import add_xp


async def get_or_create_achievement_progress(
    session: AsyncSession, user: User, achievement_type: AchievementType
) -> UserAchievement:
    result = await session.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == user.id,
            UserAchievement.achievement_type_id == achievement_type.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserAchievement(user_id=user.id, achievement_type_id=achievement_type.id, claimed=False)
        session.add(row)
        await session.flush()
    return row


async def load_achievements_with_progress(
    session: AsyncSession, user: User
) -> list[tuple[AchievementType, UserAchievement, bool]]:
    """خروجی هر ردیف: (نوع دستاورد, ردیف پیشرفت, آیا شرایط الان برقراره)."""
    result = await session.execute(select(AchievementType))
    types = list(result.scalars().all())

    pairs = []
    for at in types:
        progress = await get_or_create_achievement_progress(session, user, at)
        current_value = getattr(user, at.condition_field, 0)
        is_ready = current_value >= at.condition_value
        pairs.append((at, progress, is_ready))
    await session.commit()
    return pairs


async def claim_achievement(
    session: AsyncSession, user: User, achievement_type_id: int
) -> tuple[AchievementType | None, str | None]:
    achievement_type = await session.get(AchievementType, achievement_type_id)
    if achievement_type is None:
        return None, "این دستاورد پیدا نشد."

    progress = await get_or_create_achievement_progress(session, user, achievement_type)
    if progress.claimed:
        return None, "قبلاً این دستاورد رو گرفتی."

    current_value = getattr(user, achievement_type.condition_field, 0)
    if current_value < achievement_type.condition_value:
        return None, "هنوز شرایط این دستاورد رو نداری."

    user.gold += achievement_type.reward_gold
    if achievement_type.reward_xp:
        add_xp(user, achievement_type.reward_xp)

    progress.claimed = True
    progress.claimed_at = datetime.utcnow()
    return achievement_type, None


async def check_referral_milestone(session: AsyncSession, user: User) -> None:
    """
    اگه کاربر به سطح REFERRAL_MILESTONE_LEVEL رسیده باشه و از طریق دعوت اومده باشه
    و هنوز پاداشش پرداخت نشده، به دعوت‌کننده طلا میده. (بررسی تنبل - مثل بقیه سیستم‌ها)
    """
    if user.referred_by_id is None or user.referral_milestone_paid:
        return
    if user.level < settings.REFERRAL_MILESTONE_LEVEL:
        return

    referrer = await session.get(User, user.referred_by_id)
    if referrer is not None:
        referrer.gold += settings.REFERRAL_MILESTONE_GOLD
    user.referral_milestone_paid = True
