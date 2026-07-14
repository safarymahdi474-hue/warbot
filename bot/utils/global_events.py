import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import GlobalEvent

# ---------------------------------------------------------------------------
# تعریف رویدادهای سراسری (نه فقط یک نبرد خاص - روی کل یک "روم" اثر می‌ذارن)
# ---------------------------------------------------------------------------
GLOBAL_EVENT_DEFS = {
    "sandstorm": {
        "label": "🌪️ توفان شن",
        "duration_hours": settings.SANDSTORM_DURATION_HOURS,
        "announcement": (
            "🌪️ <b>توفان شن شروع شد!</b>\n"
            f"به مدت {settings.SANDSTORM_DURATION_HOURS} ساعت، تولید نفت همه‌ی اعضای این فضای بازی افت می‌کنه."
        ),
    },
    "war_season": {
        "label": "⚔️ فصل جنگ",
        "duration_hours": settings.WAR_SEASON_DURATION_HOURS,
        "announcement": (
            "⚔️ <b>فصل جنگ شروع شد!</b>\n"
            f"به مدت {settings.WAR_SEASON_DURATION_HOURS} ساعت، XP همه‌ی نبردها (با ربات و PvP) دوبرابر میشه."
        ),
    },
}


async def get_active_events(session: AsyncSession, room_id: int | None) -> list[GlobalEvent]:
    now = datetime.utcnow()
    result = await session.execute(
        select(GlobalEvent).where(GlobalEvent.room_id == room_id, GlobalEvent.ends_at > now)
    )
    return list(result.scalars().all())


async def get_oil_production_multiplier(session: AsyncSession, room_id: int | None) -> float:
    events = await get_active_events(session, room_id)
    if any(e.event_type == "sandstorm" for e in events):
        return settings.SANDSTORM_OIL_MULTIPLIER
    return 1.0


async def get_xp_multiplier(session: AsyncSession, room_id: int | None) -> float:
    events = await get_active_events(session, room_id)
    if any(e.event_type == "war_season" for e in events):
        return settings.WAR_SEASON_XP_MULTIPLIER
    return 1.0


async def maybe_trigger_global_event(session: AsyncSession, room_id: int | None) -> GlobalEvent | None:
    """
    شانس کمی برای شروع یه رویداد سراسری جدید توی این روم (اگه از قبل هیچ
    رویداد فعالی نباشه). خروجی: GlobalEvent در صورت شروع رویداد جدید، وگرنه None.
    """
    if random.random() > (settings.GLOBAL_EVENT_TRIGGER_CHANCE_PERCENT / 100):
        return None

    existing = await get_active_events(session, room_id)
    if existing:
        return None

    event_type = random.choice(list(GLOBAL_EVENT_DEFS.keys()))
    definition = GLOBAL_EVENT_DEFS[event_type]
    event = GlobalEvent(
        room_id=room_id,
        event_type=event_type,
        ends_at=datetime.utcnow() + timedelta(hours=definition["duration_hours"]),
    )
    session.add(event)
    await session.flush()
    return event


def build_announcement(event: GlobalEvent) -> str:
    return GLOBAL_EVENT_DEFS[event.event_type]["announcement"]
