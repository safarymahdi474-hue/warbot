from datetime import datetime

from bot.config import settings
from bot.database.models import User


def regen_energy(user: User) -> User:
    """
    انرژی رو بر اساس زمان سپری‌شده از آخرین آپدیت، شارژ می‌کنه.
    این تابع رو باید قبل از هر نمایش پروفایل/انجام اکشن صدا بزنی.
    """
    now = datetime.utcnow()
    minutes_passed = int((now - user.last_energy_update).total_seconds() // 60)
    if minutes_passed <= 0:
        return user

    regenerated = minutes_passed * settings.ENERGY_REGEN_PER_MINUTE
    if regenerated > 0:
        user.energy = min(user.max_energy, user.energy + regenerated)
        user.last_energy_update = now
    return user


def xp_required_for_level(level: int) -> int:
    """XP لازم برای رسیدن از `level` به `level + 1`."""
    return int(settings.XP_BASE_TO_NEXT_LEVEL * (settings.XP_GROWTH_FACTOR ** (level - 1)))


def add_xp(user: User, amount: int) -> list[int]:
    """
    XP اضافه می‌کنه و اگه لازم بود چند بار پشت سر هم لول‌آپ می‌کنه.
    خروجی: لیست لول‌هایی که کاربر تازه بهشون رسیده (برای نمایش پیام تبریک).
    """
    leveled_up_to: list[int] = []
    user.xp += amount

    while user.xp >= xp_required_for_level(user.level):
        user.xp -= xp_required_for_level(user.level)
        user.level += 1
        # پاداش لول‌آپ: کمی جان و انرژی ماکزیمم بیشتر میشه
        user.max_hp += 5
        user.hp = user.max_hp
        user.max_energy += 2
        leveled_up_to.append(user.level)

    return leveled_up_to
