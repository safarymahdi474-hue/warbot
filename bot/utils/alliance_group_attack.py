import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import (
    Alliance,
    AllianceGroupAttack,
    AllianceGroupAttackParticipant,
    BannedTelegramUser,
    User,
)
from bot.utils.alliance import add_war_score, get_active_war_between
from bot.utils.alliance_research import get_alliance_bonus_percent
from bot.utils.battle import (
    air_defense_reduction_percent,
    compute_air_defense_power,
    compute_air_offense_power,
    compute_power,
    destroy_units,
    load_combat_units_and_research,
)
from bot.utils.context import current_room, room_condition
from bot.utils.global_events import get_xp_multiplier
from bot.utils.items import get_active_boost_percent
from bot.utils.military import get_bonus_percent
from bot.utils.progression import add_xp


def can_manage_group_attack(user: User) -> str | None:
    """None یعنی مجازه. فقط رهبر/افسر اتحاد می‌تونه حمله‌ی گروهی بسازه."""
    if user.alliance_id is None:
        return "اول باید عضو یک اتحاد بشی."
    if user.alliance_role not in ("leader", "officer"):
        return "فقط رهبر یا افسر اتحاد می‌تونه حمله‌ی گروهی سازمان بده."
    return None


async def get_active_group_attack(session: AsyncSession, alliance_id: int) -> AllianceGroupAttack | None:
    result = await session.execute(
        select(AllianceGroupAttack).where(
            AllianceGroupAttack.alliance_id == alliance_id,
            AllianceGroupAttack.status == "gathering",
        )
    )
    return result.scalar_one_or_none()


async def find_group_attack_targets(session: AsyncSession, alliance_id: int, exclude_user_id: int) -> list[User]:
    """بازیکن‌های غیرهم‌اتحاد توی همین روم، مرتب‌شده بر اساس سطح (قوی‌ترین‌ها اول)."""
    banned_subquery = select(BannedTelegramUser.telegram_id)
    result = await session.execute(
        select(User)
        .where(
            User.id != exclude_user_id,
            room_condition(User.room_id),
            (User.alliance_id.is_(None)) | (User.alliance_id != alliance_id),
            User.telegram_id.not_in(banned_subquery),
        )
        .order_by(User.level.desc())
        .limit(settings.ALLIANCE_GROUP_ATTACK_MAX_TARGETS_SHOWN)
    )
    return list(result.scalars().all())


async def create_group_attack(
    session: AsyncSession, leader: User, target: User
) -> AllianceGroupAttack | str:
    error = can_manage_group_attack(leader)
    if error:
        return error
    if target.id == leader.id:
        return "نمی‌تونی به خودت حمله‌ی گروهی بسازی."
    if target.alliance_id == leader.alliance_id:
        return "نمی‌تونی به هم‌اتحادی‌ت حمله کنی."
    if target.room_id != current_room():
        return "این بازیکن مال این گروه/چت نیست."

    existing = await get_active_group_attack(session, leader.alliance_id)
    if existing is not None:
        return "همین الان یه حمله‌ی گروهی دیگه در حال جمع‌آوری عضوه."

    attack = AllianceGroupAttack(
        alliance_id=leader.alliance_id,
        leader_id=leader.id,
        target_user_id=target.id,
        status="gathering",
    )
    session.add(attack)
    await session.flush()

    session.add(AllianceGroupAttackParticipant(group_attack_id=attack.id, user_id=leader.id))
    return attack


async def join_group_attack(session: AsyncSession, user: User, attack: AllianceGroupAttack) -> str | None:
    if attack.status != "gathering":
        return "این حمله دیگه در حال جمع‌آوری عضو نیست."
    if user.alliance_id != attack.alliance_id:
        return "این حمله‌ی گروهی مال اتحاد تو نیست."

    result = await session.execute(
        select(AllianceGroupAttackParticipant).where(
            AllianceGroupAttackParticipant.group_attack_id == attack.id,
            AllianceGroupAttackParticipant.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return "قبلاً به این حمله پیوستی."

    session.add(AllianceGroupAttackParticipant(group_attack_id=attack.id, user_id=user.id))
    return None


async def get_participants(session: AsyncSession, attack: AllianceGroupAttack) -> list[User]:
    result = await session.execute(
        select(AllianceGroupAttackParticipant).where(
            AllianceGroupAttackParticipant.group_attack_id == attack.id
        )
    )
    rows = list(result.scalars().all())
    users = []
    for row in rows:
        u = await session.get(User, row.user_id, options=[selectinload(User.country)])
        if u is not None:
            users.append(u)
    return users


async def resolve_group_attack(session: AsyncSession, attack: AllianceGroupAttack) -> dict | str:
    """
    قدرت حمله‌ی همه‌ی شرکت‌کننده‌ها رو جمع می‌کنه و در برابر قدرت دفاعی هدف روی می‌ندازه.
    خروجی: dict با جزئیات نتیجه، یا پیام خطا (str).
    """
    if attack.status != "gathering":
        return "این حمله دیگه در حال جمع‌آوری عضو نیست."

    participants = await get_participants(session, attack)
    if len(participants) < settings.ALLIANCE_GROUP_ATTACK_MIN_PARTICIPANTS:
        return f"حداقل {settings.ALLIANCE_GROUP_ATTACK_MIN_PARTICIPANTS} نفر باید بپیوندن تا حمله شروع بشه."

    target = await session.get(User, attack.target_user_id, options=[selectinload(User.country)])
    if target is None:
        return "هدف این حمله دیگه در دسترس نیست."

    # 🏛️ آکادمی نظامی اتحاد: فقط وقتی اتحاد مهاجم با اتحاد هدف در جنگ فعاله
    war = None
    academy_bonus = 0.0
    if target.alliance_id and target.alliance_id != attack.alliance_id:
        war = await get_active_war_between(session, attack.alliance_id, target.alliance_id)
        if war is not None:
            academy_bonus = await get_alliance_bonus_percent(
                session, attack.alliance_id, "alliance_attack_percent"
            )

    # --- محاسبه‌ی قدرت هر شرکت‌کننده و جمع کل ---
    participant_data = []
    total_attack_power = 0
    total_air_power = 0
    for user in participants:
        units, research = await load_combat_units_and_research(session, user.id)
        country_bonus = user.country.military_bonus_percent if user.country else 0.0
        boost = await get_active_boost_percent(session, user.id, "attack_percent") + academy_bonus
        power = compute_power(units, research, country_bonus, "attack", boost)
        air_power = compute_air_offense_power(units, research, country_bonus, boost)
        total_attack_power += power
        total_air_power += air_power
        participant_data.append({"user": user, "units": units, "research": research, "power": power})

    target_units, target_research = await load_combat_units_and_research(session, target.id)
    target_country_bonus = target.country.military_bonus_percent if target.country else 0.0
    target_boost = await get_active_boost_percent(session, target.id, "defense_percent")
    target_power = compute_power(
        target_units, target_research, target_country_bonus, "defense", target_boost
    )

    # 🛰️ پدافند هوایی هدف: قدرت واقعی واحدهای پدافندی‌اش، سهم هوایی حمله‌ی
    # تیم رو خنثی می‌کنه - نه یه بونوس تحقیقی ثابت.
    air_ratio = (total_air_power / total_attack_power) if total_attack_power > 0 else 0.0
    target_air_defense_power = compute_air_defense_power(target_units, target_research, target_country_bonus, target_boost)
    air_reduction = air_defense_reduction_percent(target_air_defense_power)
    if air_ratio > 0 and air_reduction > 0:
        air_power_effective = total_attack_power * air_ratio
        total_attack_power = int(total_attack_power - air_power_effective * (air_reduction / 100))

    roll_attackers = total_attack_power * random.uniform(0.9, 1.1)
    roll_target = target_power * random.uniform(0.9, 1.1)
    attackers_won = roll_attackers >= roll_target

    # --- آسیب و غارت ---
    total_loot = {"gold": 0, "iron": 0, "oil": 0, "food": 0}
    if attackers_won:
        target_hp_loss = int(target.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100)
        target_unit_loss_pct = settings.LOSER_UNIT_LOSS_PERCENT
        own_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        own_hp_loss_pct = settings.WINNER_HP_LOSS_PERCENT

        leader_data = next((d for d in participant_data if d["user"].id == attack.leader_id), None)
        leader_loot_bonus = (
            get_bonus_percent(leader_data["research"], "loot_bonus_percent") if leader_data else 0.0
        )
        pct = (settings.PVP_LOOT_PERCENT / 100) * (1 + leader_loot_bonus / 100)
        for field in total_loot:
            available = getattr(target, field)
            amount = int(available * pct)
            total_loot[field] = amount
            setattr(target, field, available - amount)
    else:
        target_hp_loss = int(target.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100)
        target_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        own_unit_loss_pct = settings.LOSER_UNIT_LOSS_PERCENT
        own_hp_loss_pct = settings.LOSER_HP_LOSS_PERCENT

    # 🧱 استحکامات: هدف همیشه در حال دفاعه، پس تخفیف تلفاتش همیشه اعمال میشه
    fortification_reduction = get_bonus_percent(target_research, "defense_unit_loss_reduction_percent")
    target_unit_loss_pct = target_unit_loss_pct * max(0.0, 1 - fortification_reduction / 100)

    # 🩹 پزشکی نظامی هدف
    target_medicine = get_bonus_percent(target_research, "hp_loss_reduction_percent")
    target_hp_loss = int(target_hp_loss * max(0.0, 1 - target_medicine / 100))

    target.hp = max(1, target.hp - target_hp_loss)
    target_units_lost = destroy_units(target_units, target_unit_loss_pct)

    # --- تقسیم غارت: بخشی به صندوق اتحاد، بقیه مساوی بین شرکت‌کننده‌ها ---
    alliance = await session.get(Alliance, attack.alliance_id)
    treasury_gold_share = 0
    per_participant_gold = 0
    per_participant_iron = total_loot["iron"] // max(len(participant_data), 1)
    per_participant_oil = total_loot["oil"] // max(len(participant_data), 1)
    per_participant_food = total_loot["food"] // max(len(participant_data), 1)

    if attackers_won and total_loot["gold"] > 0:
        treasury_gold_share = int(total_loot["gold"] * settings.ALLIANCE_GROUP_ATTACK_TREASURY_CUT_PERCENT / 100)
        remaining_gold = total_loot["gold"] - treasury_gold_share
        per_participant_gold = remaining_gold // max(len(participant_data), 1)
        if alliance is not None:
            alliance.treasury_gold += treasury_gold_share

    xp_per_participant = (60 + target.level * 5) if attackers_won else 15
    xp_multiplier = await get_xp_multiplier(session, current_room())
    xp_per_participant = int(xp_per_participant * xp_multiplier)

    results = []
    for data in participant_data:
        user = data["user"]
        own_hp_loss = int(user.max_hp * own_hp_loss_pct / 100)
        own_medicine = get_bonus_percent(data["research"], "hp_loss_reduction_percent")
        own_hp_loss = int(own_hp_loss * max(0.0, 1 - own_medicine / 100))
        user.hp = max(1, user.hp - own_hp_loss)
        own_units_lost = destroy_units(data["units"], own_unit_loss_pct)

        user.gold += per_participant_gold
        user.iron = min(user.max_iron, user.iron + per_participant_iron)
        user.oil = min(user.max_oil, user.oil + per_participant_oil)
        user.food = min(user.max_food, user.food + per_participant_food)

        if attackers_won:
            user.battles_won_total += 1
        leveled_up = add_xp(user, xp_per_participant)

        results.append(
            {
                "nickname": user.nickname,
                "own_units_lost": own_units_lost,
                "own_hp_loss": own_hp_loss,
                "leveled_up": leveled_up,
            }
        )

    # --- امتیاز جنگ اتحاد (اگه در جنگ باشن - war از بالا قبلاً واکشی شده) ---
    war_note_alliance_id = None
    if war is not None:
        winner_alliance_id = attack.alliance_id if attackers_won else target.alliance_id
        await add_war_score(session, war, winner_alliance_id, int(total_attack_power))
        war_note_alliance_id = winner_alliance_id

    attack.status = "resolved"
    attack.resolved_at = datetime.utcnow()

    return {
        "attackers_won": attackers_won,
        "total_attack_power": int(total_attack_power),
        "target_power": int(target_power),
        "target_nickname": target.nickname,
        "target_units_lost": target_units_lost,
        "target_hp": target.hp,
        "target_max_hp": target.max_hp,
        "loot": total_loot,
        "treasury_gold_share": treasury_gold_share,
        "per_participant_gold": per_participant_gold,
        "participant_count": len(participant_data),
        "participant_results": results,
        "war_score_added": war_note_alliance_id is not None,
    }


async def cancel_group_attack(session: AsyncSession, user: User, attack: AllianceGroupAttack) -> str | None:
    if attack.leader_id != user.id and user.alliance_role != "leader":
        return "فقط رهبر یا کسی که این حمله رو ساخته می‌تونه لغوش کنه."
    if attack.status != "gathering":
        return "این حمله دیگه در حال جمع‌آوری عضو نیست."
    attack.status = "cancelled"
    return None
