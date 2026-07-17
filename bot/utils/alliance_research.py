from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Alliance, AllianceResearch, AllianceResearchType


async def get_or_create_alliance_research(
    session: AsyncSession, alliance_id: int, research_type_id: int
) -> AllianceResearch:
    result = await session.execute(
        select(AllianceResearch).where(
            AllianceResearch.alliance_id == alliance_id,
            AllianceResearch.research_type_id == research_type_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AllianceResearch(alliance_id=alliance_id, research_type_id=research_type_id, level=0)
        session.add(row)
        await session.flush()
    return row


async def load_alliance_researches_with_types(
    session: AsyncSession, alliance_id: int
) -> list[tuple[AllianceResearchType, AllianceResearch]]:
    result = await session.execute(select(AllianceResearchType))
    types = list(result.scalars().all())

    pairs = []
    for rt in types:
        row = await get_or_create_alliance_research(session, alliance_id, rt.id)
        pairs.append((rt, row))
    return pairs


def alliance_research_cost(research_type: AllianceResearchType, current_level: int) -> int:
    """هزینه‌ی ارتقا به لول بعدی - هرچی لول بالاتر، گرون‌تر."""
    return research_type.cost_gold_per_level * (current_level + 1)


def alliance_research_duration(research_type: AllianceResearchType, current_level: int) -> timedelta:
    return timedelta(seconds=research_type.base_research_seconds * (current_level + 1))


def start_alliance_research(
    alliance: Alliance, research: AllianceResearch, research_type: AllianceResearchType
) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا. هزینه از Alliance.treasury_gold کم میشه."""
    if research.upgrade_finish_at is not None:
        return "این تحقیق اتحادی همین الان در حال انجامه."
    if research.level >= research_type.max_level:
        return "این تحقیق اتحادی به حداکثر سطح رسیده."

    cost = alliance_research_cost(research_type, research.level)
    if alliance.treasury_gold < cost:
        return f"صندوق اتحاد کافی نداره. هزینه لازم: 💰{cost} (موجودی صندوق: 💰{alliance.treasury_gold})"

    alliance.treasury_gold -= cost
    research.upgrade_finish_at = datetime.utcnow() + alliance_research_duration(research_type, research.level)
    return None


def finish_ready_alliance_researches(researches: list[AllianceResearch]) -> list[AllianceResearch]:
    now = datetime.utcnow()
    finished = []
    for r in researches:
        if r.upgrade_finish_at is not None and r.upgrade_finish_at <= now:
            r.level += 1
            r.upgrade_finish_at = None
            finished.append(r)
    return finished


async def get_alliance_bonus_percent(session: AsyncSession, alliance_id: int | None, effect_type: str) -> float:
    """مجموع بونوس یک نوع اثر خاص از همه‌ی تحقیقات اتحادی این اتحاد."""
    if alliance_id is None:
        return 0.0
    result = await session.execute(
        select(AllianceResearch)
        .options(selectinload(AllianceResearch.research_type))
        .where(AllianceResearch.alliance_id == alliance_id)
    )
    rows = list(result.scalars().all())
    total = 0.0
    for r in rows:
        if r.research_type.effect_type == effect_type and r.level > 0:
            total += r.research_type.effect_per_level * r.level
    return total
