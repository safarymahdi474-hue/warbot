from datetime import datetime, timedelta

from bot.config import settings
from bot.database.models import User

# ---------------------------------------------------------------------------
# هدیه آنلاین (هر چند ساعت یک‌بار، فقط با باز کردن ربات)
# با گرفتنش چند روز پشت‌سرهم (تقویمی)، هر روز یه مقدار طلای اضافه به پاداش
# پایه اضافه میشه. اگه یه روز کامل رد بشه و نگیره، استریک صفر میشه.
# ---------------------------------------------------------------------------

def can_claim_online_gift(user: User) -> bool:
    if user.last_online_gift_claim is None:
        return True
    return datetime.utcnow() - user.last_online_gift_claim >= timedelta(
        hours=settings.ONLINE_GIFT_COOLDOWN_HOURS
    )


def _update_streak(user: User, now: datetime) -> int:
    """استریک رو بر اساس تاریخ (نه ساعت) آپدیت می‌کنه و مقدار جدیدش رو برمی‌گردونه."""
    if user.last_online_gift_claim is None:
        user.online_gift_streak = 1
        return user.online_gift_streak

    last_date = user.last_online_gift_claim.date()
    today = now.date()
    day_diff = (today - last_date).days

    if day_diff == 0:
        # همون روز، فقط یه بار دیگه تو کول‌داون - استریک عوض نمیشه
        if user.online_gift_streak <= 0:
            user.online_gift_streak = 1
    elif day_diff == 1:
        # درست روز بعد گرفته - استریک ادامه پیدا می‌کنه
        user.online_gift_streak += 1
    else:
        # حداقل یه روز کامل رد شده - استریک از نو شروع میشه
        user.online_gift_streak = 1

    return user.online_gift_streak


def claim_online_gift(user: User) -> dict:
    now = datetime.utcnow()
    streak = _update_streak(user, now)
    streak_days_counted = min(streak, settings.ONLINE_GIFT_STREAK_MAX_DAYS)
    streak_bonus = (streak_days_counted - 1) * settings.ONLINE_GIFT_STREAK_BONUS_GOLD
    total_gold = settings.ONLINE_GIFT_GOLD + streak_bonus

    user.gold += total_gold
    user.energy = min(user.max_energy, user.energy + settings.ONLINE_GIFT_ENERGY)
    user.last_online_gift_claim = now

    return {
        "gold": total_gold,
        "base_gold": settings.ONLINE_GIFT_GOLD,
        "streak_bonus": streak_bonus,
        "streak": streak,
        "energy": settings.ONLINE_GIFT_ENERGY,
    }


def time_until_online_gift(user: User) -> timedelta | None:
    if user.last_online_gift_claim is None:
        return None
    remaining = timedelta(hours=settings.ONLINE_GIFT_COOLDOWN_HOURS) - (
        datetime.utcnow() - user.last_online_gift_claim
    )
    return remaining if remaining.total_seconds() > 0 else None
