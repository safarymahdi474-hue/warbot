from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Alliance, AllianceWar, User
from bot.utils.context import current_room, room_condition

# ---------------------------------------------------------------------------
# ساخت / عضویت / ترک
# ---------------------------------------------------------------------------

async def create_alliance(session: AsyncSession, leader: User, name: str, tag: str) -> Alliance | str:
    """خروجی: Alliance در صورت موفقیت، وگرنه پیام خطا (str)."""
    if leader.alliance_id is not None:
        return "تو همین الان عضو یک اتحادی. اول باید ازش خارج بشی."
    if leader.gold < settings.ALLIANCE_CREATE_COST_GOLD:
        return f"برای ساخت اتحاد به {settings.ALLIANCE_CREATE_COST_GOLD} طلا نیاز داری."
    if not (3 <= len(name) <= 64):
        return "اسم اتحاد باید بین ۳ تا ۶۴ حرف باشه."
    if not (2 <= len(tag) <= 8):
        return "تگ اتحاد باید بین ۲ تا ۸ حرف باشه."

    result = await session.execute(
        select(Alliance).where(Alliance.name == name, room_condition(Alliance.room_id))
    )
    if result.scalar_one_or_none() is not None:
        return "این اسم قبلاً استفاده شده."
    result = await session.execute(
        select(Alliance).where(Alliance.tag == tag, room_condition(Alliance.room_id))
    )
    if result.scalar_one_or_none() is not None:
        return "این تگ قبلاً استفاده شده."

    leader.gold -= settings.ALLIANCE_CREATE_COST_GOLD
    alliance = Alliance(
        name=name,
        tag=tag,
        leader_id=leader.id,
        member_limit=settings.ALLIANCE_MEMBER_LIMIT,
        room_id=current_room(),
    )
    session.add(alliance)
    await session.flush()

    leader.alliance_id = alliance.id
    leader.alliance_role = "leader"
    return alliance


async def join_alliance(session: AsyncSession, user: User, alliance: Alliance) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا."""
    if user.alliance_id is not None:
        return "تو همین الان عضو یک اتحادی."
    if alliance.room_id != current_room():
        return "این اتحاد مال این گروه/چت نیست."

    result = await session.execute(select(User).where(User.alliance_id == alliance.id))
    member_count = len(result.scalars().all())
    if member_count >= alliance.member_limit:
        return "این اتحاد پره."

    user.alliance_id = alliance.id
    user.alliance_role = "member"
    return None


async def leave_alliance(session: AsyncSession, user: User) -> str | None:
    """None یعنی موفق. اگه رهبر خارج بشه، اتحاد منحل میشه (همه اعضا بیرون میان)."""
    if user.alliance_id is None:
        return "تو عضو هیچ اتحادی نیستی."

    if user.alliance_role == "leader":
        result = await session.execute(select(User).where(User.alliance_id == user.alliance_id))
        members = list(result.scalars().all())
        for m in members:
            m.alliance_id = None
            m.alliance_role = None
        alliance = await session.get(Alliance, user.alliance_id)
        if alliance is not None:
            await session.delete(alliance)
    else:
        user.alliance_id = None
        user.alliance_role = None
    return None


async def kick_member(session: AsyncSession, leader: User, target: User) -> str | None:
    if leader.alliance_role not in ("leader", "officer"):
        return "فقط رهبر یا افسر می‌تونه عضو اخراج کنه."
    if target.alliance_id != leader.alliance_id:
        return "این کاربر عضو اتحاد تو نیست."
    if target.alliance_role == "leader":
        return "نمی‌تونی رهبر رو اخراج کنی."
    target.alliance_id = None
    target.alliance_role = None
    return None


# ---------------------------------------------------------------------------
# جنگ اتحادها
# ---------------------------------------------------------------------------

async def get_active_war_between(
    session: AsyncSession, alliance_a_id: int, alliance_b_id: int
) -> AllianceWar | None:
    result = await session.execute(
        select(AllianceWar).where(
            AllianceWar.status == "active",
            (
                (AllianceWar.alliance_a_id == alliance_a_id) & (AllianceWar.alliance_b_id == alliance_b_id)
            )
            | (
                (AllianceWar.alliance_a_id == alliance_b_id) & (AllianceWar.alliance_b_id == alliance_a_id)
            ),
        )
    )
    return result.scalar_one_or_none()


async def declare_war(
    session: AsyncSession, leader: User, target_alliance: Alliance
) -> AllianceWar | str:
    if leader.alliance_role != "leader":
        return "فقط رهبر اتحاد می‌تونه اعلام جنگ کنه."
    if leader.alliance_id == target_alliance.id:
        return "نمی‌تونی به اتحاد خودت اعلام جنگ کنی."
    if target_alliance.room_id != current_room():
        return "این اتحاد مال این گروه/چت نیست."

    existing = await get_active_war_between(session, leader.alliance_id, target_alliance.id)
    if existing is not None:
        return "همین الان با این اتحاد در جنگی."

    war = AllianceWar(
        alliance_a_id=leader.alliance_id,
        alliance_b_id=target_alliance.id,
        ends_at=datetime.utcnow() + timedelta(hours=settings.ALLIANCE_WAR_DURATION_HOURS),
        status="active",
    )
    session.add(war)
    return war


async def add_war_score(session: AsyncSession, war: AllianceWar, winner_alliance_id: int, points: int) -> None:
    if war.alliance_a_id == winner_alliance_id:
        war.score_a += points
    elif war.alliance_b_id == winner_alliance_id:
        war.score_b += points


async def finish_expired_wars(session: AsyncSession) -> list[AllianceWar]:
    now = datetime.utcnow()
    result = await session.execute(select(AllianceWar).where(AllianceWar.status == "active"))
    active_wars = list(result.scalars().all())

    finished = []
    for war in active_wars:
        if war.ends_at <= now:
            war.status = "finished"
            if war.score_a > war.score_b:
                war.winner_alliance_id = war.alliance_a_id
            elif war.score_b > war.score_a:
                war.winner_alliance_id = war.alliance_b_id
            else:
                war.winner_alliance_id = None  # مساوی
            finished.append(war)
    return finished
