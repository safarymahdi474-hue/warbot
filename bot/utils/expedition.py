import math

from bot.config import settings
from bot.database.models import UserResearch, UserUnit
from bot.utils.military import effective_attack, effective_defense, get_bonus_percent

# هرچی نیروی اعزامی «کندتر» باشه، کاروان کندتر حرکت می‌کنه؛ زمان نهایی سفر
# بر اساس کندترین زیردسته‌ای که ارسال شده تعیین میشه (به‌دقیقه، پایه).
SUBCATEGORY_BASE_TRAVEL_MINUTES = {
    "infantry": 12,
    "tank": 10,
    "artillery": 9,
    "navy": 8,
    "drone": 5,
    "missile": 3,
    "fighter": 4,
    "bomber": 6,
    "air_defense": 12,  # پدافند تدافعیه، عملاً هیچ‌وقت اعزام نمیشه ولی برای اطمینان مقدار داره
}
DEFAULT_TRAVEL_MINUTES = 10


def compute_sent_units(user_units: list[UserUnit], user_level: int, percent: int) -> dict[int, int]:
    """
    از هر نوع نیروی بازشده (سطح کافی) و موجود، percent درصدش رو برای اعزام
    جدا می‌کنه. نیروی مجروح (wounded_quantity) هیچ‌وقت اعزام نمیشه.
    خروجی: {unit_type_id: تعداد اعزامی}
    """
    sent: dict[int, int] = {}
    for uu in user_units:
        if uu.quantity <= 0 or user_level < uu.unit_type.min_player_level:
            continue
        qty = math.floor(uu.quantity * percent / 100)
        if percent >= 100:
            qty = uu.quantity  # حمله با تمام قوا - بدون گرد کردن به پایین
        if qty > 0:
            sent[uu.unit_type_id] = qty
    return sent


def compute_travel_minutes(user_units: list[UserUnit], sent_units: dict[int, int]) -> int:
    """
    زمان رسیدن رو بر اساس کندترین زیردسته‌ی اعزامی + تعداد کل نیروی اعزامی حساب می‌کنه.
    """
    if not sent_units:
        return settings.EXPEDITION_MIN_MINUTES

    slowest = DEFAULT_TRAVEL_MINUTES
    total_quantity = 0
    units_by_id = {uu.unit_type_id: uu for uu in user_units}
    for unit_type_id, qty in sent_units.items():
        uu = units_by_id.get(unit_type_id)
        if uu is None or qty <= 0:
            continue
        total_quantity += qty
        base = SUBCATEGORY_BASE_TRAVEL_MINUTES.get(uu.unit_type.subcategory, DEFAULT_TRAVEL_MINUTES)
        slowest = max(slowest, base)

    extra = total_quantity // max(1, settings.EXPEDITION_QUANTITY_EXTRA_DIVISOR)
    minutes = slowest + extra
    return max(settings.EXPEDITION_MIN_MINUTES, min(settings.EXPEDITION_MAX_MINUTES, minutes))


def compute_power_from_sent(
    units: list[UserUnit],
    sent_units: dict[int, int],
    researches: list[UserResearch],
    country_military_bonus_percent: float,
    mode: str,
    extra_bonus_percent: float = 0.0,
) -> int:
    """دقیقاً مثل compute_power، ولی فقط سهم اعزامی هر نوع نیرو رو حساب می‌کنه، نه کل موجودی."""
    bonus = get_bonus_percent(researches, f"{mode}_percent") + extra_bonus_percent
    total = 0
    for uu in units:
        qty = sent_units.get(uu.unit_type_id, 0)
        if qty <= 0:
            continue
        ut = uu.unit_type
        per_unit = effective_attack(ut, bonus) if mode == "attack" else effective_defense(ut, bonus)
        per_unit = int(per_unit * (1 + country_military_bonus_percent / 100))
        total += per_unit * qty
    return total


def compute_air_offense_power_from_sent(
    units: list[UserUnit],
    sent_units: dict[int, int],
    researches: list[UserResearch],
    country_military_bonus_percent: float,
    extra_bonus_percent: float = 0.0,
) -> int:
    from bot.utils.battle import AIR_OFFENSE_SUBCATEGORIES

    bonus = get_bonus_percent(researches, "attack_percent") + extra_bonus_percent
    total = 0
    for uu in units:
        qty = sent_units.get(uu.unit_type_id, 0)
        if qty <= 0 or uu.unit_type.subcategory not in AIR_OFFENSE_SUBCATEGORIES:
            continue
        per_unit = effective_attack(uu.unit_type, bonus)
        per_unit = int(per_unit * (1 + country_military_bonus_percent / 100))
        total += per_unit * qty
    return total


def apply_sent_losses(units: list[UserUnit], sent_units: dict[int, int], loss_percent: float) -> int:
    """
    دقیقاً مثل destroy_units، ولی تلفات فقط از سهم اعزامی هر نوع نیرو کم میشه
    (نه از کل موجودی - چون بخشی از ارتش خونه مونده و درگیر نبرد نبوده).
    """
    import random

    total_lost = 0
    for uu in units:
        sent_qty = sent_units.get(uu.unit_type_id, 0)
        if sent_qty <= 0:
            continue
        loss = int(sent_qty * loss_percent)
        if loss <= 0 and sent_qty > 0 and loss_percent > 0:
            loss = 1 if random.random() < loss_percent * 4 else 0
        loss = min(loss, sent_qty, uu.quantity)
        if loss <= 0:
            continue

        wounded = int(loss * settings.WOUNDED_PERCENT_OF_LOSSES)
        uu.quantity -= loss
        uu.wounded_quantity += wounded
        total_lost += loss
    return total_lost
