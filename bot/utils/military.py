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
        "uranium": unit_type.cost_uranium * quantity,
    }


def training_duration(unit_type: UnitType, quantity: int, training_speed_percent: float) -> timedelta:
    seconds = unit_type.train_seconds_per_unit * quantity
    speed_multiplier = max(0.1, 1 - (training_speed_percent / 100))
    return timedelta(seconds=int(seconds * speed_multiplier))


def can_afford(user: User, cost: dict[str, int]) -> bool:
    return (
        user.gold >= cost["gold"]
        and user.iron >= cost["iron"]
        and user.oil >= cost["oil"]
        and user.uranium >= cost.get("uranium", 0)
    )


def _format_cost_parts(cost: dict[str, int]) -> list[str]:
    parts = [f"💰{cost['gold']} طلا"]
    if cost["iron"]:
        parts.append(f"⛏️{cost['iron']} آهن")
    if cost["oil"]:
        parts.append(f"🛢️{cost['oil']} نفت")
    if cost.get("uranium"):
        parts.append(f"☢️{cost['uranium']} اورانیوم")
    return parts


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
        return "منابع کافی نداری. هزینه لازم: " + " + ".join(_format_cost_parts(cost))

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]
    user.oil -= cost["oil"]
    user.uranium -= cost["uranium"]

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

def effective_attack(unit_type: UnitType, attack_bonus_percent: float) -> int:
    return int(unit_type.base_attack * (1 + attack_bonus_percent / 100))


def effective_defense(unit_type: UnitType, defense_bonus_percent: float) -> int:
    return int(unit_type.base_defense * (1 + defense_bonus_percent / 100))


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
    return timedelta(seconds=research_type.base_research_seconds * (settings.RESEARCH_TIME_GROWTH**current_level))


def start_research(user: User, user_research: UserResearch, research_type: ResearchType) -> str | None:
    if user_research.upgrade_finish_at is not None:
        return "این تحقیق همین الان در حال انجامه."
    if user_research.level >= research_type.max_level:
        return "این تحقیق به حداکثر سطح رسیده."

    cost = research_cost(research_type, user_research.level)
    if not (user.gold >= cost["gold"] and user.iron >= cost["iron"] and user.oil >= cost["oil"]):
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
