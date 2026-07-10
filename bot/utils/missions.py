from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import MissionType, User, UserMissionProgress
from bot.utils.progression import add_xp


def period_key_for_scope(scope: str) -> str:
    now = datetime.utcnow()
    if scope == "daily":
        return now.strftime("%Y-%m-%d")
    if scope == "weekly":
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    raise ValueError(f"scope نامعتبر: {scope}")


async def get_or_create_progress(
    session: AsyncSession, user: User, mission_type: MissionType
) -> UserMissionProgress:
    period_key = period_key_for_scope(mission_type.scope)
    result = await session.execute(
        select(UserMissionProgress).where(
            UserMissionProgress.user_id == user.id,
            UserMissionProgress.mission_type_id == mission_type.id,
            UserMissionProgress.period_key == period_key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserMissionProgress(
            user_id=user.id, mission_type_id=mission_type.id, period_key=period_key, progress=0
        )
        session.add(row)
        await session.flush()
    return row


async def load_missions_with_progress(
    session: AsyncSession, user: User
) -> list[tuple[MissionType, UserMissionProgress]]:
    result = await session.execute(select(MissionType))
    mission_types = list(result.scalars().all())

    pairs = []
    for mt in mission_types:
        progress = await get_or_create_progress(session, user, mt)
        pairs.append((mt, progress))
    await session.commit()
    return pairs


async def record_progress(session: AsyncSession, user: User, event_type: str, amount: int = 1) -> None:
    """
    هر جای بازی که یک رویداد قابل‌ردیابی اتفاق بیفته (نبرد، آموزش نیرو، ارتقای
    ساختمان و ...) این تابع صدا زده میشه تا ماموریت‌های مرتبط رو پیش ببره.
    توجه: این تابع commit نمی‌کنه؛ commit نهایی به عهده‌ی صدازننده‌ست.
    """
    result = await session.execute(select(MissionType).where(MissionType.event_type == event_type))
    mission_types = list(result.scalars().all())
    if not mission_types:
        return

    for mt in mission_types:
        progress = await get_or_create_progress(session, user, mt)
        if progress.progress < mt.target_amount:
            progress.progress = min(mt.target_amount, progress.progress + amount)


async def claim_mission_reward(
    session: AsyncSession, user: User, mission_type_id: int
) -> tuple[MissionType | None, str | None]:
    """خروجی: (MissionType در صورت موفقیت وگرنه None, پیام خطا در صورت شکست وگرنه None)."""
    mission_type = await session.get(MissionType, mission_type_id)
    if mission_type is None:
        return None, "این ماموریت پیدا نشد."

    progress = await get_or_create_progress(session, user, mission_type)
    if progress.progress < mission_type.target_amount:
        return None, "هنوز این ماموریت رو کامل نکردی."
    if progress.claimed:
        return None, "قبلاً پاداش این ماموریت رو گرفتی."

    user.gold += mission_type.reward_gold
    user.iron += mission_type.reward_iron
    user.oil += mission_type.reward_oil
    user.food += mission_type.reward_food
    if mission_type.reward_xp:
        add_xp(user, mission_type.reward_xp)

    progress.claimed = True
    return mission_type, None
