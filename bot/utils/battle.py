import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import BattleReport, User, UserResearch, UserUnit
from bot.utils.alliance import get_active_war_between
from bot.utils.alliance_research import get_alliance_bonus_percent
from bot.utils.context import current_room
from bot.utils.global_events import get_xp_multiplier
from bot.utils.items import get_active_boost_percent
from bot.utils.military import effective_attack, effective_defense, get_bonus_percent
from bot.utils.progression import add_xp

# ---------------------------------------------------------------------------
# سختی نبرد با ربات (NPC) - هیچ کاربر واقعی درگیر نمیشه
# ---------------------------------------------------------------------------
BOT_DIFFICULTIES = {
    "easy": {"label": "🟢 آسان", "power_mult": 0.6, "gold_reward": 150, "xp_reward": 40},
    "medium": {"label": "🟡 متوسط", "power_mult": 1.0, "gold_reward": 350, "xp_reward": 90},
    "hard": {"label": "🔴 سخت", "power_mult": 1.5, "gold_reward": 700, "xp_reward": 180},
}


# ---------------------------------------------------------------------------
# استراتژی حمله - قبل از هر نبرد (بات یا PvP) انتخاب میشه
# ---------------------------------------------------------------------------
ATTACK_STRATEGIES = {
    "balanced": {
        "label": "⚖️ حمله متعادل",
        "desc": "همون تعادل همیشگی بین آسیب و غارت.",
        "power_mult": 1.0,
        "loot_mult": 1.0,
        "enemy_unit_loss_mult": 1.0,
        "own_hp_loss_mult": 1.0,
    },
    "damage": {
        "label": "⚔️ ضربه به نیروها",
        "desc": "آسیب بیشتر به نیروهای حریف، ولی غارت کمتر.",
        "power_mult": 1.10,
        "loot_mult": 0.6,
        "enemy_unit_loss_mult": 1.6,
        "own_hp_loss_mult": 1.1,
    },
    "loot": {
        "label": "💰 غارت منابع",
        "desc": "غارت و طلای بیشتر، ولی آسیب کمتر به نیروهای حریف.",
        "power_mult": 0.9,
        "loot_mult": 1.6,
        "enemy_unit_loss_mult": 0.5,
        "own_hp_loss_mult": 1.0,
    },
}


def get_strategy(key: str) -> dict:
    return ATTACK_STRATEGIES.get(key, ATTACK_STRATEGIES["balanced"])


# ---------------------------------------------------------------------------
# اتفاق‌های شانسی حین نبرد - قبل از تعیین برنده رخ می‌دن و قدرت‌ها رو تغییر می‌دن
# ---------------------------------------------------------------------------
BATTLE_EVENTS = [
    {"key": "none", "weight": 55, "side": None, "power_mult": 1.0, "label": None},
    {
        "key": "ambush",
        "weight": 10,
        "side": "defender",
        "power_mult": 1.25,
        "label": "🌙 <b>کمین!</b> حریف غافلگیرت کرد و قدرتش موقتاً بالا رفت.",
    },
    {
        "key": "critical_hit",
        "weight": 10,
        "side": "attacker",
        "power_mult": 1.30,
        "label": "💥 <b>ضربه‌ی بحرانی!</b> قدرت حمله‌ت به‌طرز غیرمنتظره‌ای بالا رفت.",
    },
    {
        "key": "intel",
        "weight": 8,
        "side": "attacker",
        "power_mult": 1.15,
        "label": "🕵️ <b>اطلاعات جاسوسی!</b> نقطه‌ضعف حریف رو پیدا کردی.",
    },
    {
        "key": "reinforcements",
        "weight": 8,
        "side": "defender",
        "power_mult": 1.20,
        "label": "🪖 <b>نیروی کمکی!</b> به حریف کمک رسید و قدرتش بیشتر شد.",
    },
    {
        "key": "sandstorm",
        "weight": 9,
        "side": "both",
        "power_mult": 0.85,
        "label": "🌪️ <b>توفان شن!</b> دید و هماهنگی هر دو طرف کم شد و قدرت هر دو افت کرد.",
    },
]


def roll_battle_event(ambush_resist_percent: float = 0.0, crit_boost_percent: float = 0.0) -> dict:
    weights = [e["weight"] for e in BATTLE_EVENTS]
    event = random.choices(BATTLE_EVENTS, weights=weights, k=1)[0]
    if event["key"] == "ambush" and ambush_resist_percent > 0:
        # 🎖️ روحیه‌ی جنگی: شدت اثر منفی کمین رو کم می‌کنه (نه حذفش)؛ دیکشنری
        # اصلی BATTLE_EVENTS رو دستکاری نمی‌کنیم، یه کپی موقت می‌سازیم.
        reduced_mult = 1 + (event["power_mult"] - 1) * max(0.0, 1 - ambush_resist_percent / 100)
        event = {**event, "power_mult": reduced_mult}
    elif event["key"] == "critical_hit" and crit_boost_percent > 0:
        # 🎯 دقت توپخانه: شدت ضربه‌ی بحرانی رو بیشتر می‌کنه
        boosted_mult = 1 + (event["power_mult"] - 1) * (1 + crit_boost_percent / 100)
        event = {**event, "power_mult": boosted_mult}
    return event


async def load_combat_units_and_research(
    session: AsyncSession, user_id: int
) -> tuple[list[UserUnit], list[UserResearch]]:
    result = await session.execute(
        select(UserUnit).options(selectinload(UserUnit.unit_type)).where(UserUnit.user_id == user_id)
    )
    units = list(result.scalars().all())

    result = await session.execute(
        select(UserResearch)
        .options(selectinload(UserResearch.research_type))
        .where(UserResearch.user_id == user_id)
    )
    researches = list(result.scalars().all())
    return units, researches


def compute_power(
    units: list[UserUnit],
    researches: list[UserResearch],
    country_military_bonus_percent: float,
    mode: str,
    extra_bonus_percent: float = 0.0,
) -> int:
    """mode: 'attack' یا 'defense'. extra_bonus_percent برای بوست‌های موقت آیتم‌هاست."""
    bonus = get_bonus_percent(researches, f"{mode}_percent") + extra_bonus_percent
    total = 0
    for uu in units:
        if uu.quantity <= 0:
            continue
        ut = uu.unit_type
        per_unit = effective_attack(ut, bonus) if mode == "attack" else effective_defense(ut, bonus)
        per_unit = int(per_unit * (1 + country_military_bonus_percent / 100))
        total += per_unit * uu.quantity
    return total


def compute_category_power(
    units: list[UserUnit],
    researches: list[UserResearch],
    country_military_bonus_percent: float,
    mode: str,
    category: str,
    extra_bonus_percent: float = 0.0,
) -> int:
    """
    دقیقاً مثل compute_power، ولی فقط نیروهایی که category_group شون برابر
    category هست رو حساب می‌کنه (مثلاً category='air').
    توجه: این تابع موقتیه و تو فاز ۳ (بازطراحی پدافند هوایی) کامل عوض میشه.
    """
    bonus = get_bonus_percent(researches, f"{mode}_percent") + extra_bonus_percent
    total = 0
    for uu in units:
        if uu.quantity <= 0 or uu.unit_type.category_group != category:
            continue
        ut = uu.unit_type
        per_unit = effective_attack(ut, bonus) if mode == "attack" else effective_defense(ut, bonus)
        per_unit = int(per_unit * (1 + country_military_bonus_percent / 100))
        total += per_unit * uu.quantity
    return total


def destroy_units(units: list[UserUnit], loss_percent: float) -> int:
    """به تناسب loss_percent از هر نوع نیرو نابود می‌کنه. خروجی: تعداد کل نابودشده."""
    destroyed = 0
    for uu in units:
        if uu.quantity <= 0:
            continue
        loss = int(uu.quantity * loss_percent)
        if loss <= 0 and uu.quantity > 0 and loss_percent > 0:
            loss = 1 if random.random() < loss_percent * 4 else 0  # واحد کم هم شانس کمی برای از دست رفتن داره
        loss = min(loss, uu.quantity)
        uu.quantity -= loss
        destroyed += loss
    return destroyed


def can_attack(user: User) -> str | None:
    """None یعنی مجازه، وگرنه پیام خطا."""
    if user.energy < settings.ATTACK_ENERGY_COST:
        return f"انرژی کافی نداری. حداقل {settings.ATTACK_ENERGY_COST} انرژی لازمه."
    if user.hp < user.max_hp * settings.MIN_HP_PERCENT_TO_ATTACK / 100:
        return "جونت خیلی کمه! اول باید استراحت کنی تا HP برگرده."
    return None


async def resolve_bot_battle(
    session: AsyncSession, attacker: User, difficulty: str, strategy_key: str = "balanced"
) -> BattleReport:
    diff = BOT_DIFFICULTIES[difficulty]
    strategy = get_strategy(strategy_key)

    attacker_units, attacker_research = await load_combat_units_and_research(session, attacker.id)
    country_bonus = attacker.country.military_bonus_percent if attacker.country else 0.0
    attack_boost = await get_active_boost_percent(session, attacker.id, "attack_percent")
    attacker_power = compute_power(attacker_units, attacker_research, country_bonus, "attack", attack_boost)
    attacker_power = int(attacker_power * strategy["power_mult"])

    npc_power = int(max(attacker_power, 100) * diff["power_mult"] * random.uniform(0.85, 1.15))

    ambush_resist = get_bonus_percent(attacker_research, "ambush_resist_percent")
    crit_boost = get_bonus_percent(attacker_research, "critical_hit_boost_percent")
    event = roll_battle_event(ambush_resist, crit_boost)
    if event["side"] in ("attacker", "both"):
        attacker_power = int(attacker_power * event["power_mult"])
    if event["side"] in ("defender", "both"):
        npc_power = int(npc_power * event["power_mult"])

    roll_attacker = attacker_power * random.uniform(0.9, 1.1)
    roll_npc = npc_power * random.uniform(0.9, 1.1)

    attacker.energy -= settings.ATTACK_ENERGY_COST
    won = roll_attacker >= roll_npc

    if won:
        hp_loss = int(attacker.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100 * strategy["own_hp_loss_mult"])
        unit_loss_percent = settings.WINNER_UNIT_LOSS_PERCENT
        gold_reward = int(diff["gold_reward"] * strategy["loot_mult"])
        xp_reward = diff["xp_reward"]
    else:
        hp_loss = int(attacker.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100 * strategy["own_hp_loss_mult"])
        unit_loss_percent = settings.LOSER_UNIT_LOSS_PERCENT
        gold_reward = int((diff["gold_reward"] // 4) * strategy["loot_mult"])
        xp_reward = diff["xp_reward"] // 3

    medicine_bonus = get_bonus_percent(attacker_research, "hp_loss_reduction_percent")
    hp_loss = int(hp_loss * max(0.0, 1 - medicine_bonus / 100))
    attacker.hp = max(1, attacker.hp - hp_loss)
    units_lost = destroy_units(attacker_units, unit_loss_percent)
    attacker.gold += gold_reward
    if won:
        attacker.battles_won_total += 1
    xp_multiplier = await get_xp_multiplier(session, current_room())
    xp_reward = int(xp_reward * xp_multiplier)
    leveled_up = add_xp(attacker, xp_reward)

    report = BattleReport(
        attacker_id=attacker.id,
        defender_id=None,
        is_pvp=False,
        winner="attacker" if won else "defender",
        attacker_power=int(attacker_power),
        defender_power=int(npc_power),
        attacker_units_lost=units_lost,
        defender_units_lost=0,
        attacker_hp_lost=hp_loss,
        loot_gold=gold_reward,
        xp_gained=xp_reward,
    )
    session.add(report)
    report._leveled_up = leveled_up  # type: ignore[attr-defined]
    report._event = event  # type: ignore[attr-defined]
    return report


async def resolve_pvp_battle(
    session: AsyncSession, attacker: User, defender: User, strategy_key: str = "balanced"
) -> BattleReport:
    strategy = get_strategy(strategy_key)

    attacker_units, attacker_research = await load_combat_units_and_research(session, attacker.id)
    defender_units, defender_research = await load_combat_units_and_research(session, defender.id)

    attacker_country_bonus = attacker.country.military_bonus_percent if attacker.country else 0.0
    defender_country_bonus = defender.country.military_bonus_percent if defender.country else 0.0

    attacker_attack_boost = await get_active_boost_percent(session, attacker.id, "attack_percent")
    defender_defense_boost = await get_active_boost_percent(session, defender.id, "defense_percent")

    # 🏛️ آکادمی نظامی اتحاد: فقط وقتی اتحاد مهاجم با اتحاد مدافع در جنگه اعمال میشه
    if attacker.alliance_id and defender.alliance_id and attacker.alliance_id != defender.alliance_id:
        war = await get_active_war_between(session, attacker.alliance_id, defender.alliance_id)
        if war is not None:
            academy_bonus = await get_alliance_bonus_percent(
                session, attacker.alliance_id, "alliance_attack_percent"
            )
            attacker_attack_boost += academy_bonus

    attacker_power_raw = compute_power(
        attacker_units, attacker_research, attacker_country_bonus, "attack", attacker_attack_boost
    )
    attacker_air_power_raw = compute_category_power(
        attacker_units, attacker_research, attacker_country_bonus, "attack", "air", attacker_attack_boost
    )
    attacker_air_ratio = (attacker_air_power_raw / attacker_power_raw) if attacker_power_raw > 0 else 0.0

    attacker_power = int(attacker_power_raw * strategy["power_mult"])
    defender_power = compute_power(
        defender_units, defender_research, defender_country_bonus, "defense", defender_defense_boost
    )

    ambush_resist = get_bonus_percent(attacker_research, "ambush_resist_percent")
    crit_boost = get_bonus_percent(attacker_research, "critical_hit_boost_percent")
    event = roll_battle_event(ambush_resist, crit_boost)
    if event["side"] in ("attacker", "both"):
        attacker_power = int(attacker_power * event["power_mult"])
    if event["side"] in ("defender", "both"):
        defender_power = int(defender_power * event["power_mult"])

    # 🛰️ پدافند هوایی: فقط سهم قدرت مهاجم که از هواپیما میاد رو کم می‌کنه
    air_defense_bonus = get_bonus_percent(defender_research, "air_defense_percent")
    if attacker_air_ratio > 0 and air_defense_bonus > 0:
        attacker_air_power_effective = attacker_power * attacker_air_ratio
        attacker_power = int(attacker_power - attacker_air_power_effective * (air_defense_bonus / 100))

    attacker.energy -= settings.ATTACK_ENERGY_COST

    roll_attacker = attacker_power * random.uniform(0.9, 1.1)
    roll_defender = defender_power * random.uniform(0.9, 1.1)
    attacker_won = roll_attacker >= roll_defender

    if attacker_won:
        attacker_hp_loss = int(attacker.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100 * strategy["own_hp_loss_mult"])
        defender_hp_loss = int(defender.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100)
        attacker_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        defender_unit_loss_pct = min(settings.LOSER_UNIT_LOSS_PERCENT * strategy["enemy_unit_loss_mult"], 0.9)
        xp_reward = 60 + defender.level * 5
    else:
        attacker_hp_loss = int(attacker.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100 * strategy["own_hp_loss_mult"])
        defender_hp_loss = int(defender.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100)
        attacker_unit_loss_pct = settings.LOSER_UNIT_LOSS_PERCENT
        defender_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        xp_reward = 15

    # 🧱 استحکامات: مدافع همیشه (چه برنده چه بازنده) کمتر نیرو از دست میده
    fortification_reduction = get_bonus_percent(defender_research, "defense_unit_loss_reduction_percent")
    defender_unit_loss_pct = defender_unit_loss_pct * max(0.0, 1 - fortification_reduction / 100)

    # 🩹 پزشکی نظامی: هرکس این تحقیق رو داشته باشه، خودش کمتر HP از دست میده
    attacker_medicine = get_bonus_percent(attacker_research, "hp_loss_reduction_percent")
    defender_medicine = get_bonus_percent(defender_research, "hp_loss_reduction_percent")
    attacker_hp_loss = int(attacker_hp_loss * max(0.0, 1 - attacker_medicine / 100))
    defender_hp_loss = int(defender_hp_loss * max(0.0, 1 - defender_medicine / 100))

    attacker.hp = max(1, attacker.hp - attacker_hp_loss)
    defender.hp = max(1, defender.hp - defender_hp_loss)

    attacker_units_lost = destroy_units(attacker_units, attacker_unit_loss_pct)
    defender_units_lost = destroy_units(defender_units, defender_unit_loss_pct)

    if attacker_won:
        attacker.battles_won_total += 1
    else:
        defender.battles_won_total += 1

    loot = {"gold": 0, "iron": 0, "oil": 0, "food": 0}
    if attacker_won:
        loot_tactics_bonus = get_bonus_percent(attacker_research, "loot_bonus_percent")
        pct = (settings.PVP_LOOT_PERCENT / 100) * strategy["loot_mult"] * (1 + loot_tactics_bonus / 100)
        for field in loot:
            available = getattr(defender, field)
            amount = int(available * pct)
            loot[field] = amount
            setattr(defender, field, available - amount)
            setattr(attacker, field, getattr(attacker, field) + amount)

    xp_multiplier = await get_xp_multiplier(session, current_room())
    xp_reward = int(xp_reward * xp_multiplier)
    leveled_up = add_xp(attacker, xp_reward)

    report = BattleReport(
        attacker_id=attacker.id,
        defender_id=defender.id,
        is_pvp=True,
        winner="attacker" if attacker_won else "defender",
        attacker_power=int(attacker_power),
        defender_power=int(defender_power),
        attacker_units_lost=attacker_units_lost,
        defender_units_lost=defender_units_lost,
        attacker_hp_lost=attacker_hp_loss,
        loot_gold=loot["gold"],
        loot_iron=loot["iron"],
        loot_oil=loot["oil"],
        loot_food=loot["food"],
        xp_gained=xp_reward,
    )
    session.add(report)
    report._leveled_up = leveled_up  # type: ignore[attr-defined]
    report._event = event  # type: ignore[attr-defined]
    return report
