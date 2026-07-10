from datetime import datetime, timedelta

from bot.config import settings
from bot.database.models import BuildingType, User, UserBuilding

RESOURCE_FIELD = {"food": "food", "iron": "iron", "oil": "oil"}
RESOURCE_MAX_FIELD = {"food": "max_food", "iron": "max_iron", "oil": "max_oil"}
RESOURCE_LABEL = {"food": "🌾 غذا", "iron": "⛏️ آهن", "oil": "🛢️ نفت"}


def upgrade_cost(building_type: BuildingType, current_level: int) -> dict[str, int]:
    """هزینه‌ی ساخت (اگه level=0) یا ارتقا به لول بعدی."""
    growth = settings.RESOURCE_COST_GROWTH**current_level
    return {
        "gold": int(building_type.base_cost_gold * growth),
        "iron": int(building_type.base_cost_iron * growth),
    }


def upgrade_duration(building_type: BuildingType, current_level: int) -> timedelta:
    seconds = building_type.base_build_time_seconds * (
        settings.BUILD_TIME_GROWTH**current_level
    )
    return timedelta(seconds=int(seconds))


def can_afford(user: User, cost: dict[str, int]) -> bool:
    if user.gold < cost["gold"]:
        return False
    if cost["iron"] > 0 and user.iron < cost["iron"]:
        return False
    return True


def start_upgrade(user: User, user_building: UserBuilding, building_type: BuildingType) -> str | None:
    """
    اگه شرایط اوکی باشه، هزینه رو کم می‌کنه و ساخت/ارتقا رو شروع می‌کنه.
    خروجی: None اگه موفق بود، وگرنه پیام خطا برای نمایش به کاربر.
    """
    if user_building.upgrade_finish_at is not None:
        return "این ساختمان همین الان در حال ساخت/ارتقاست."
    if user_building.level >= building_type.max_level:
        return "این ساختمان به حداکثر سطح رسیده."

    cost = upgrade_cost(building_type, user_building.level)
    if not can_afford(user, cost):
        return f"طلا یا آهن کافی نداری. هزینه لازم: 💰{cost['gold']} طلا" + (
            f" + ⛏️{cost['iron']} آهن" if cost["iron"] else ""
        )

    user.gold -= cost["gold"]
    user.iron -= cost["iron"]
    user_building.upgrade_finish_at = datetime.utcnow() + upgrade_duration(
        building_type, user_building.level
    )
    return None


def finish_ready_upgrades(user_buildings: list[UserBuilding]) -> list[UserBuilding]:
    """ساختمان‌هایی که زمان ساختشون تموم شده رو یک لول بالا می‌بره."""
    now = datetime.utcnow()
    finished = []
    for ub in user_buildings:
        if ub.upgrade_finish_at is not None and ub.upgrade_finish_at <= now:
            ub.level += 1
            ub.upgrade_finish_at = None
            finished.append(ub)
    return finished


def recalculate_storage_caps(user: User, user_buildings: list[UserBuilding]) -> None:
    warehouse_level = 0
    for ub in user_buildings:
        if ub.building_type.key == "warehouse":
            warehouse_level = ub.level
            break
    bonus = warehouse_level * 500  # باید با storage_bonus_per_level انبار هماهنگ بمونه
    user.max_food = settings.BASE_RESOURCE_STORAGE + bonus
    user.max_iron = settings.BASE_RESOURCE_STORAGE + bonus
    user.max_oil = settings.BASE_RESOURCE_STORAGE + bonus


def collect_production(user: User, user_buildings: list[UserBuilding]) -> dict[str, int]:
    """
    از آخرین باری که جمع‌آوری شده تا الان، بر اساس لول ساختمون‌ها منبع تولید می‌کنه
    (تا سقف ظرفیت انبار). خروجی: مقدار هرمنبعی که همین الان اضافه شد.
    """
    now = datetime.utcnow()
    hours_passed = (now - user.last_resource_collect).total_seconds() / 3600
    gained = {"food": 0, "iron": 0, "oil": 0}

    if hours_passed > 0:
        for ub in user_buildings:
            bt = ub.building_type
            if bt.produces is None or ub.level <= 0:
                continue
            amount = int(bt.base_production_per_hour * ub.level * hours_passed)
            if amount <= 0:
                continue

            field = RESOURCE_FIELD[bt.produces]
            max_field = RESOURCE_MAX_FIELD[bt.produces]
            current = getattr(user, field)
            cap = getattr(user, max_field)
            added = max(0, min(amount, cap - current))
            setattr(user, field, current + added)
            gained[bt.produces] += added

        user.last_resource_collect = now

    return gained
