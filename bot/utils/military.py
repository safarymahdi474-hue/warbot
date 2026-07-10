from datetime import datetime, timedelta

from bot.config import settings
from bot.database.models import (
    ResearchType,
    TrainingOrder,
    UnitType,
    User,
    UserResearch,
    UserUnit,
)

# ---------------------------------------------------------------------------
# آموزش/خرید نیرو
# ---------------------------------------------------------------------------

def training_cost(unit_type: UnitType, quantity: int) -> dict[str, int]:
    return {
        "gold": unit_type.cost_gold * quantity,
        "iron": unit_type.cost_iron * quantity,
        "oil": unit_type.cost_oil * quantity,
    }


def training_duration(unit_type: UnitType, quantity: int, training_speed_percent: float) -> timedelta:
    seconds = unit_type.train_seconds_per_unit * quantity
    speed_multiplier = max(0.1, 1 - (training_speed_percent / 100))
    return timedelta(seconds=int(seconds * speed_multiplier))


def can_afford(user: User, cost: dict[str, int]) -> bool:
    return user.gold >= cost["gold"] and user.iron >= cost["iron"] and user.oil >= cost["oil"]


def start_training(
    user: User,
    unit_type: UnitType,
    quantity: int,
    training_speed_percent: float,
) -> TrainingOrder | str:
    """خروجی: در صورت موفقیت یک TrainingOrder (که باید session.add بشه)، وگرنه پیام خطا (str)."""
    if quantity <= 0:
        return "تعداد نامعتبره."
    if user.level < unit_type.min_player_level:
        return f"برای خرید {unit_type.name_fa} باید حداقل سطح {unit_type.min_player_level} باشی."

    cost = training_cost(unit_type, quantity)
    if not can_afford(user, cost):
        parts = [f"💰{cost['gold']} طلا"]
        if cost["iron"]:
            parts.append(f"⛏️{cost['iron']} آهن")
        if cost["oil"]:
            parts.append(f"🛢️{cost['oil']} نفت")
        return "منابع کافی نداری. هزینه لازم: " + " + ".join(parts)

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]
    user.oil -= cost["oil"]

    duration = training_duration(unit_type, quantity, training_speed_percent)
    return TrainingOrder(
        user_id=user.id,
        unit_type_id=unit_type.id,
        quantity=quantity,
        finish_at=datetime.utcnow() + duration,
    )


def finish_ready_training(orders: list[TrainingOrder], user_units: dict[int, UserUnit]) -> list[TrainingOrder]:
    """
    سفارش‌های تموم‌شده رو به تعداد نیروی کاربر اضافه می‌کنه.
    user_units باید دیکشنری {unit_type_id: UserUnit} باشه.
    خروجی: لیست سفارش‌هایی که باید از دیتابیس حذف بشن.
    """
    now = datetime.utcnow()
    finished = []
    for order in orders:
        if order.finish_at <= now:
            uu = user_units.get(order.unit_type_id)
            if uu is not None:
                uu.quantity += order.quantity
            finished.append(order)
    return finished


# ---------------------------------------------------------------------------
# ارتقای نیروها (سطح‌بندی که روی کل تعداد نیروی همون نوع اثر می‌ذاره)
# ---------------------------------------------------------------------------

def unit_upgrade_cost(unit_type: UnitType, current_level: int) -> dict[str, int]:
    growth = settings.UNIT_UPGRADE_COST_GROWTH**current_level
    return {
        "gold": int(unit_type.cost_gold * 2 * growth),
        "iron": int(unit_type.cost_iron * 2 * growth),
        "oil": int(unit_type.cost_oil * 2 * growth),
    }


def unit_upgrade_duration(current_level: int) -> timedelta:
    seconds = settings.UNIT_BASE_UPGRADE_SECONDS * (settings.UNIT_UPGRADE_TIME_GROWTH**current_level)
    return timedelta(seconds=int(seconds))


def start_unit_upgrade(user: User, user_unit: UserUnit, unit_type: UnitType) -> str | None:
    if user_unit.upgrade_finish_at is not None:
        return "این نیرو همین الان در حال ارتقاست."
    if user_unit.level >= unit_type.max_level:
        return "این نیرو به حداکثر سطح رسیده."
    if user_unit.quantity <= 0:
        return "اول باید حداقل یک واحد از این نیرو داشته باشی."

    cost = unit_upgrade_cost(unit_type, user_unit.level)
    if not can_afford(user, cost):
        parts = [f"💰{cost['gold']} طلا"]
        if cost["iron"]:
            parts.append(f"⛏️{cost['iron']} آهن")
        if cost["oil"]:
            parts.append(f"🛢️{cost['oil']} نفت")
        return "منابع کافی نداری. هزینه لازم: " + " + ".join(parts)

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]
    user.oil -= cost["oil"]
    user_unit.upgrade_finish_at = datetime.utcnow() + unit_upgrade_duration(user_unit.level)
    return None


def finish_ready_unit_upgrades(user_units: list[UserUnit]) -> list[UserUnit]:
    now = datetime.utcnow()
    finished = []
    for uu in user_units:
        if uu.upgrade_finish_at is not None and uu.upgrade_finish_at <= now:
            uu.level += 1
            uu.upgrade_finish_at = None
            finished.append(uu)
    return finished


def effective_attack(unit_type: UnitType, user_unit: UserUnit, attack_bonus_percent: float) -> int:
    level_multiplier = 1 + (user_unit.level - 1) * settings.UNIT_UPGRADE_STAT_BONUS_PER_LEVEL
    research_multiplier = 1 + (attack_bonus_percent / 100)
    return int(unit_type.base_attack * level_multiplier * research_multiplier)


def effective_defense(unit_type: UnitType, user_unit: UserUnit, defense_bonus_percent: float) -> int:
    level_multiplier = 1 + (user_unit.level - 1) * settings.UNIT_UPGRADE_STAT_BONUS_PER_LEVEL
    research_multiplier = 1 + (defense_bonus_percent / 100)
    return int(unit_type.base_defense * level_multiplier * research_multiplier)


# ---------------------------------------------------------------------------
# تحقیق و توسعه (بونوس سراسری روی کل ارتش)
# ---------------------------------------------------------------------------

def research_cost(research_type: ResearchType, current_level: int) -> dict[str, int]:
    growth = settings.RESEARCH_COST_GROWTH**current_level
    return {
        "gold": int(research_type.cost_gold * growth),
        "iron": int(research_type.cost_iron * growth),
        "oil": int(research_type.cost_oil * growth),
    }


def research_duration(research_type: ResearchType, current_level: int) -> timedelta:
    seconds = research_type.base_research_seconds * (settings.RESEARCH_TIME_GROWTH**current_level)
    return timedelta(seconds=int(seconds))


def start_research(user: User, user_research: UserResearch, research_type: ResearchType) -> str | None:
    if user_research.upgrade_finish_at is not None:
        return "این تحقیق همین الان در حال انجامه."
    if user_research.level >= research_type.max_level:
        return "این تحقیق به حداکثر سطح رسیده."

    cost = research_cost(research_type, user_research.level)
    if not can_afford(user, cost):
        parts = [f"💰{cost['gold']} طلا"]
        if cost["iron"]:
            parts.append(f"⛏️{cost['iron']} آهن")
        if cost["oil"]:
            parts.append(f"🛢️{cost['oil']} نفت")
        return "منابع کافی نداری. هزینه لازم: " + " + ".join(parts)

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]
    user.oil -= cost["oil"]
    user_research.upgrade_finish_at = datetime.utcnow() + research_duration(
        research_type, user_research.level
    )
    return None


def finish_ready_research(user_researches: list[UserResearch]) -> list[UserResearch]:
    now = datetime.utcnow()
    finished = []
    for ur in user_researches:
        if ur.upgrade_finish_at is not None and ur.upgrade_finish_at <= now:
            ur.level += 1
            ur.upgrade_finish_at = None
            finished.append(ur)
    return finished


def get_bonus_percent(user_researches: list[UserResearch], effect_type: str) -> float:
    total = 0.0
    for ur in user_researches:
        if ur.research_type.effect_type == effect_type and ur.level > 0:
            total += ur.research_type.effect_per_level * ur.level
    return total
