import random
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import ActiveBoost, User
from bot.utils.battle import compute_power, load_combat_units_and_research
from bot.utils.items import get_active_boost_percent
from bot.utils.military import get_bonus_percent


def can_spy(user: User) -> str | None:
    """None یعنی مجازه، وگرنه پیام خطا."""
    if user.gold < settings.SPY_GOLD_COST:
        return f"طلای کافی نداری. جاسوسی {settings.SPY_GOLD_COST} طلا هزینه داره."
    if user.energy < settings.SPY_ENERGY_COST:
        return f"انرژی کافی نداری. جاسوسی {settings.SPY_ENERGY_COST} انرژی لازم داره."
    return None


async def perform_spy(session: AsyncSession, spy_user: User, target: User) -> dict:
    """
    هزینه رو از spy_user کم می‌کنه و یه بازه‌ی تقریبی از قدرت دفاعی هدف برمی‌گردونه
    (نه عدد دقیق - با درصد خطای SPY_ERROR_MARGIN_PERCENT).
    با شانس SPY_DETECTION_CHANCE_PERCENT جاسوسی لو میره: هدف یه بونوس دفاعی موقت می‌گیره.
    خروجی: {"low": int, "high": int, "detected": bool}
    """
    spy_user.gold -= settings.SPY_GOLD_COST
    spy_user.energy -= settings.SPY_ENERGY_COST

    target_units, target_research = await load_combat_units_and_research(session, target.id)
    target_country_bonus = target.country.military_bonus_percent if target.country else 0.0
    target_defense_boost = await get_active_boost_percent(session, target.id, "defense_percent")
    real_power = compute_power(
        target_units, target_research, target_country_bonus, "defense", target_defense_boost
    )

    _spy_units, spy_research = await load_combat_units_and_research(session, spy_user.id)
    spy_accuracy_bonus = get_bonus_percent(spy_research, "spy_accuracy_percent")
    margin = (settings.SPY_ERROR_MARGIN_PERCENT / 100) * max(0.1, 1 - spy_accuracy_bonus / 100)
    low = max(0, int(real_power * (1 - margin)))
    high = int(real_power * (1 + margin))

    counter_espionage = get_bonus_percent(target_research, "spy_detection_reduction_percent")
    effective_detection_chance = settings.SPY_DETECTION_CHANCE_PERCENT * max(0.0, 1 - counter_espionage / 100)
    detected = random.random() < (effective_detection_chance / 100)
    if detected:
        session.add(
            ActiveBoost(
                user_id=target.id,
                boost_type="defense_percent",
                value=settings.SPY_DETECTED_DEFENSE_BONUS,
                expires_at=datetime.utcnow()
                + timedelta(minutes=settings.SPY_DETECTED_DEFENSE_DURATION_MINUTES),
            )
        )

    return {"low": low, "high": high, "detected": detected}
