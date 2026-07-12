from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import PvpSeasonScore, User
from bot.utils.context import current_room, room_condition

# ---------------------------------------------------------------------------
# جایزه‌ی پایان فصل (هفتگی) برای ۳ نفر برتر بر اساس تعداد پیروزی PvP
# ---------------------------------------------------------------------------
SEASON_REWARDS = {
    1: {"gold": 3000, "label": "🥇 نفر اول"},
    2: {"gold": 1800, "label": "🥈 نفر دوم"},
    3: {"gold": 1000, "label": "🥉 نفر سوم"},
}


def current_week_key() -> str:
    now = datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def previous_week_key() -> str:
    now = datetime.utcnow() - timedelta(days=7)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def record_pvp_win(session: AsyncSession, user: User) -> None:
    """بعد از هر پیروزی PvP صدا زده میشه تا شمارنده‌ی هفته‌ی جاری بالا بره."""
    period_key = current_week_key()
    result = await session.execute(
        select(PvpSeasonScore).where(
            PvpSeasonScore.user_id == user.id, PvpSeasonScore.period_key == period_key
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PvpSeasonScore(user_id=user.id, period_key=period_key, room_id=current_room(), wins=0)
        session.add(row)
    row.wins += 1


async def get_weekly_leaderboard(session: AsyncSession, limit: int = 10) -> list[PvpSeasonScore]:
    period_key = current_week_key()
    result = await session.execute(
        select(PvpSeasonScore)
        .options(selectinload(PvpSeasonScore.user))
        .where(PvpSeasonScore.period_key == period_key, room_condition(PvpSeasonScore.room_id))
        .order_by(PvpSeasonScore.wins.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_claimable_season_reward(
    session: AsyncSession, user: User
) -> tuple[int, PvpSeasonScore] | None:
    """اگه توی هفته‌ی قبل جزو ۳ نفر برتر بوده و هنوز جایزه رو نگرفته، (rank, row) برمی‌گردونه."""
    period_key = previous_week_key()
    result = await session.execute(
        select(PvpSeasonScore)
        .where(PvpSeasonScore.period_key == period_key, room_condition(PvpSeasonScore.room_id))
        .order_by(PvpSeasonScore.wins.desc())
        .limit(3)
    )
    top3 = list(result.scalars().all())
    for rank, row in enumerate(top3, start=1):
        if row.user_id == user.id and row.wins > 0 and not row.reward_claimed:
            return rank, row
    return None


async def claim_season_reward(session: AsyncSession, user: User) -> tuple[int, dict] | str:
    """خروجی: (rank, reward dict) در صورت موفقیت، وگرنه پیام خطا (str)."""
    found = await get_claimable_season_reward(session, user)
    if found is None:
        return "جایزه‌ای برای دریافت نداری."
    rank, row = found
    reward = SEASON_REWARDS[rank]
    user.gold += reward["gold"]
    row.reward_claimed = True
    return rank, reward
