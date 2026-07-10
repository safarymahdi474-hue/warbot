from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import AdminLog, Alliance, AllianceWar, BannedTelegramUser, BattleReport, Room, User


async def ensure_admin_flag(session: AsyncSession, user: User) -> None:
    """اگه telegram_id کاربر توی لیست ادمین‌های config باشه، is_admin رو True می‌کنه."""
    if user.telegram_id in settings.admin_ids and not user.is_admin:
        user.is_admin = True


async def log_action(
    session: AsyncSession,
    action_type: str,
    actor_telegram_id: int,
    target_telegram_id: int | None = None,
    details: str = "",
) -> None:
    session.add(
        AdminLog(
            action_type=action_type,
            actor_telegram_id=actor_telegram_id,
            target_telegram_id=target_telegram_id,
            details=details,
        )
    )


async def ban_user(session: AsyncSession, admin_telegram_id: int, target: User, reason: str) -> None:
    existing = await session.get(BannedTelegramUser, target.telegram_id)
    if existing is None:
        session.add(
            BannedTelegramUser(telegram_id=target.telegram_id, reason=reason, banned_by=admin_telegram_id)
        )
    else:
        existing.reason = reason
        existing.banned_by = admin_telegram_id
    await log_action(session, "ban", admin_telegram_id, target.telegram_id, reason)


async def unban_user(session: AsyncSession, admin_telegram_id: int, target: User) -> None:
    existing = await session.get(BannedTelegramUser, target.telegram_id)
    if existing is not None:
        await session.delete(existing)
    await log_action(session, "unban", admin_telegram_id, target.telegram_id, "")


async def get_server_stats(session: AsyncSession) -> dict:
    total_users = (await session.execute(select(func.count(User.telegram_id.distinct())))).scalar_one()
    banned_users = (await session.execute(select(func.count(BannedTelegramUser.telegram_id)))).scalar_one()
    total_rooms = (await session.execute(select(func.count(Room.id)))).scalar_one()
    total_alliances = (await session.execute(select(func.count(Alliance.id)))).scalar_one()
    total_battles = (await session.execute(select(func.count(BattleReport.id)))).scalar_one()
    active_wars = (
        await session.execute(select(func.count(AllianceWar.id)).where(AllianceWar.status == "active"))
    ).scalar_one()
    top_level = (await session.execute(select(func.max(User.level)))).scalar_one()

    return {
        "total_users": total_users,
        "banned_users": banned_users,
        "total_rooms": total_rooms,
        "total_alliances": total_alliances,
        "total_battles": total_battles,
        "active_wars": active_wars,
        "top_level": top_level or 0,
    }


async def get_recent_logs(session: AsyncSession, limit: int = 15) -> list[AdminLog]:
    result = await session.execute(select(AdminLog).order_by(AdminLog.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def get_all_user_telegram_ids(session: AsyncSession) -> list[int]:
    banned_result = await session.execute(select(BannedTelegramUser.telegram_id))
    banned_ids = {row[0] for row in banned_result.all()}

    result = await session.execute(select(User.telegram_id).distinct())
    all_ids = {row[0] for row in result.all()}
    return list(all_ids - banned_ids)
