import random
from datetime import datetime, timedelta

from bot.config import settings
from bot.database.models import User
from bot.utils.progression import add_xp

# ---------------------------------------------------------------------------
# صندوق روزانه
# ---------------------------------------------------------------------------

def can_claim_daily_chest(user: User) -> bool:
    if user.last_daily_chest_claim is None:
        return True
    return datetime.utcnow() - user.last_daily_chest_claim >= timedelta(hours=20)


def claim_daily_chest(user: User) -> dict:
    gold = random.randint(settings.DAILY_CHEST_GOLD_MIN, settings.DAILY_CHEST_GOLD_MAX)
    user.gold += gold
    leveled_up = add_xp(user, settings.DAILY_CHEST_XP)
    user.last_daily_chest_claim = datetime.utcnow()
    return {"gold": gold, "xp": settings.DAILY_CHEST_XP, "leveled_up": leveled_up}


def time_until_daily_chest(user: User) -> timedelta | None:
    if user.last_daily_chest_claim is None:
        return None
    remaining = timedelta(hours=20) - (datetime.utcnow() - user.last_daily_chest_claim)
    return remaining if remaining.total_seconds() > 0 else None


# ---------------------------------------------------------------------------
# هدیه آنلاین (هر چند ساعت یک‌بار، فقط با باز کردن ربات)
# ---------------------------------------------------------------------------

def can_claim_online_gift(user: User) -> bool:
    if user.last_online_gift_claim is None:
        return True
    return datetime.utcnow() - user.last_online_gift_claim >= timedelta(
        hours=settings.ONLINE_GIFT_COOLDOWN_HOURS
    )


def claim_online_gift(user: User) -> dict:
    user.gold += settings.ONLINE_GIFT_GOLD
    user.energy = min(user.max_energy, user.energy + settings.ONLINE_GIFT_ENERGY)
    user.last_online_gift_claim = datetime.utcnow()
    return {"gold": settings.ONLINE_GIFT_GOLD, "energy": settings.ONLINE_GIFT_ENERGY}


def time_until_online_gift(user: User) -> timedelta | None:
    if user.last_online_gift_claim is None:
        return None
    remaining = timedelta(hours=settings.ONLINE_GIFT_COOLDOWN_HOURS) - (
        datetime.utcnow() - user.last_online_gift_claim
    )
    return remaining if remaining.total_seconds() > 0 else None


# ---------------------------------------------------------------------------
# گردونه شانس (۱ چرخش رایگان در روز)
# ---------------------------------------------------------------------------

# هر جایزه: (برچسب, وزن شانس, تابعی که روی user اعمال میشه و توضیح خروجی برمی‌گردونه)
WHEEL_PRIZES = [
    {"label": "💰 ۵۰ طلا", "weight": 25, "gold": 50},
    {"label": "💰 ۲۰۰ طلا", "weight": 20, "gold": 200},
    {"label": "💰 ۵۰۰ طلا", "weight": 10, "gold": 500},
    {"label": "⛏️ ۱۰۰ آهن", "weight": 15, "iron": 100},
    {"label": "🛢️ ۱۰۰ نفت", "weight": 15, "oil": 100},
    {"label": "🌾 ۳۰۰ غذا", "weight": 15, "food": 300},
    {"label": "⚡ ۵۰ انرژی", "weight": 15, "energy": 50},
    {"label": "⭐ ۱۰۰ XP", "weight": 10, "xp": 100},
    {"label": "🎉 جایزه بزرگ: ۲۰۰۰ طلا!", "weight": 2, "gold": 2000},
    {"label": "😢 پوچ", "weight": 10, "gold": 0},
]


def can_spin_wheel(user: User) -> bool:
    if user.last_wheel_spin_at is None:
        return True
    return datetime.utcnow() - user.last_wheel_spin_at >= timedelta(hours=settings.WHEEL_COOLDOWN_HOURS)


def time_until_wheel_spin(user: User) -> timedelta | None:
    if user.last_wheel_spin_at is None:
        return None
    remaining = timedelta(hours=settings.WHEEL_COOLDOWN_HOURS) - (
        datetime.utcnow() - user.last_wheel_spin_at
    )
    return remaining if remaining.total_seconds() > 0 else None


def spin_wheel(user: User) -> dict:
    weights = [p["weight"] for p in WHEEL_PRIZES]
    prize = random.choices(WHEEL_PRIZES, weights=weights, k=1)[0]

    if prize.get("gold"):
        user.gold += prize["gold"]
    if prize.get("iron"):
        user.iron = min(user.max_iron, user.iron + prize["iron"])
    if prize.get("oil"):
        user.oil = min(user.max_oil, user.oil + prize["oil"])
    if prize.get("food"):
        user.food = min(user.max_food, user.food + prize["food"])
    if prize.get("energy"):
        user.energy = min(user.max_energy, user.energy + prize["energy"])
    if prize.get("xp"):
        add_xp(user, prize["xp"])

    user.last_wheel_spin_at = datetime.utcnow()
    return prize
