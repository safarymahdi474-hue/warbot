import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import BattleReport, User, UserResearch, UserUnit
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
    "elite": {"label": "🟣 نخبه", "power_mult": 2.2, "gold_reward": 1400, "xp_reward": 320},
    "boss": {"label": "☠️ باس فصلی", "power_mult": 3.2, "gold_reward": 3000, "xp_reward": 600},
}

# احتمال رویدادهای تصادفی در نبرد با ربات (روی یک رول واحد چک میشن، نه دو رول جدا)
AMBUSH_CHANCE = 0.12   # کمین: قدرت دشمن ۱۵٪ کمتر محاسبه میشه
CRITICAL_CHANCE = 0.10  # ضربه بحرانی: قدرت خودت ۱۵٪ بیشتر محاسبه میشه

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
        per_unit = effective_attack(ut, uu, bonus) if mode == "attack" else effective_defense(ut, uu, bonus)
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

    attacker_units, attacker_research = await load_combat_units_and_research(session, attacker.id)
    country_bonus = attacker.country.military_bonus_percent if attacker.country else 0.0
    attack_boost = await get_active_boost_percent(session, attacker.id, "attack_percent")
    attacker_power = compute_power(attacker_units, attacker_research, country_bonus, "attack", attack_boost)

    npc_power = int(max(attacker_power, 100) * diff["power_mult"] * random.uniform(0.85, 1.15))

    # رویداد تصادفی نبرد - روی یک رول واحد تا احتمالات هم‌پوشانی نداشته باشن
    random_event = None
    event_roll = random.random()
    if event_roll < AMBUSH_CHANCE:
        random_event = "ambush"
        npc_power = int(npc_power * 0.85)
    elif event_roll < AMBUSH_CHANCE + CRITICAL_CHANCE:
        random_event = "critical"
        attacker_power = int(attacker_power * 1.15)

    roll_attacker = attacker_power * random.uniform(0.9, 1.1)
    roll_npc = npc_power * random.uniform(0.9, 1.1)

    attacker.energy -= settings.ATTACK_ENERGY_COST
    won = roll_attacker >= roll_npc

    if won:
        hp_loss = int(attacker.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100)
        unit_loss_percent = settings.WINNER_UNIT_LOSS_PERCENT
        gold_reward = diff["gold_reward"]
        xp_reward = diff["xp_reward"]
    else:
        hp_loss = int(attacker.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100)
        unit_loss_percent = settings.LOSER_UNIT_LOSS_PERCENT
        gold_reward = diff["gold_reward"] // 4
        xp_reward = diff["xp_reward"] // 3

    attacker.hp = max(1, attacker.hp - hp_loss)
    units_lost = destroy_units(attacker_units, unit_loss_percent)
    attacker.gold += gold_reward
    if won:
        attacker.battles_won_total += 1
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
    report._leveled_up = leveled_up  # type: ignore[attr-defined]  # فقط برای نمایش پیام، در دیتابیس ذخیره نمیشه
    report._random_event = random_event  # type: ignore[attr-defined]  # فقط برای نمایش پیام، در دیتابیس ذخیره نمیشه
    return report


async def resolve_pvp_battle(session: AsyncSession, attacker: User, defender: User) -> BattleReport:
    attacker_units, attacker_research = await load_combat_units_and_research(session, attacker.id)
    defender_units, defender_research = await load_combat_units_and_research(session, defender.id)

    attacker_country_bonus = attacker.country.military_bonus_percent if attacker.country else 0.0
    defender_country_bonus = defender.country.military_bonus_percent if defender.country else 0.0

    attacker_attack_boost = await get_active_boost_percent(session, attacker.id, "attack_percent")
    defender_defense_boost = await get_active_boost_percent(session, defender.id, "defense_percent")

    attacker_power = compute_power(
        attacker_units, attacker_research, attacker_country_bonus, "attack", attacker_attack_boost
    )
    defender_power = compute_power(
        defender_units, defender_research, defender_country_bonus, "defense", defender_defense_boost
    )

    attacker.energy -= settings.ATTACK_ENERGY_COST

    roll_attacker = attacker_power * random.uniform(0.9, 1.1)
    roll_defender = defender_power * random.uniform(0.9, 1.1)
    attacker_won = roll_attacker >= roll_defender

    if attacker_won:
        attacker_hp_loss = int(attacker.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100)
        defender_hp_loss = int(defender.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100)
        attacker_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        defender_unit_loss_pct = settings.LOSER_UNIT_LOSS_PERCENT
        xp_reward = 60 + defender.level * 5
    else:
        attacker_hp_loss = int(attacker.max_hp * settings.LOSER_HP_LOSS_PERCENT / 100)
        defender_hp_loss = int(defender.max_hp * settings.WINNER_HP_LOSS_PERCENT / 100)
        attacker_unit_loss_pct = settings.LOSER_UNIT_LOSS_PERCENT
        defender_unit_loss_pct = settings.WINNER_UNIT_LOSS_PERCENT
        xp_reward = 15

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
        pct = settings.PVP_LOOT_PERCENT / 100
        for field in loot:
            available = getattr(defender, field)
            amount = int(available * pct)
            loot[field] = amount
            setattr(defender, field, available - amount)
            setattr(attacker, field, getattr(attacker, field) + amount)

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
    return report
