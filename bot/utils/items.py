import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import ActiveBoost, User, UserInventory


async def get_inventory(session: AsyncSession, user_id: int) -> list[UserInventory]:
    result = await session.execute(
        select(UserInventory)
        .options(selectinload(UserInventory.item_type))
        .where(UserInventory.user_id == user_id, UserInventory.quantity > 0)
    )
    return list(result.scalars().all())


def apply_random_resources(user: User) -> dict[str, int]:
    gained = {}
    gold = random.randint(100, 500)
    user.gold += gold
    gained["gold"] = gold
    if random.random() < 0.6:
        iron = random.randint(50, 150)
        user.iron = min(user.max_iron, user.iron + iron)
        gained["iron"] = iron
    if random.random() < 0.6:
        oil = random.randint(50, 150)
        user.oil = min(user.max_oil, user.oil + oil)
        gained["oil"] = oil
    return gained


async def use_item(
    session: AsyncSession, user: User, user_inventory: UserInventory
) -> tuple[str | None, str | None]:
    """خروجی: (پیام موفقیت, پیام خطا) — دقیقاً یکی از این دو مقدار داره."""
    if user_inventory.quantity <= 0:
        return None, "دیگه از این آیتم نداری."

    item = user_inventory.item_type
    user_inventory.quantity -= 1

    if item.effect_type == "energy":
        user.energy = min(user.max_energy, user.energy + item.effect_value)
        msg = f"⚡ +{item.effect_value} انرژی گرفتی."
    elif item.effect_type == "hp":
        user.hp = min(user.max_hp, user.hp + item.effect_value)
        msg = f"❤️ +{item.effect_value} HP گرفتی."
    elif item.effect_type in ("attack_percent", "defense_percent"):
        boost = ActiveBoost(
            user_id=user.id,
            boost_type=item.effect_type,
            value=item.effect_value,
            expires_at=datetime.utcnow() + timedelta(minutes=item.duration_minutes),
        )
        session.add(boost)
        label = "حمله" if item.effect_type == "attack_percent" else "دفاع"
        msg = f"✨ به مدت {item.duration_minutes} دقیقه {item.effect_value}٪ به {label}ات اضافه شد."
    elif item.effect_type == "random_resources":
        gained = apply_random_resources(user)
        parts = [f"💰{gained.get('gold', 0)}"]
        if gained.get("iron"):
            parts.append(f"⛏️{gained['iron']}")
        if gained.get("oil"):
            parts.append(f"🛢️{gained['oil']}")
        msg = "🎁 جعبه باز شد: " + " ".join(parts)
    else:
        user_inventory.quantity += 1  # نوع اثر ناشناخته - مصرف نشد
        return None, "این آیتم قابل استفاده نیست."

    return msg, None


async def get_active_boost_percent(session: AsyncSession, user_id: int, boost_type: str) -> float:
    """مجموع بوست‌های فعال (منقضی‌نشده) از یک نوع رو برمی‌گردونه. بوست‌های منقضی رو هم پاک می‌کنه."""
    now = datetime.utcnow()
    result = await session.execute(select(ActiveBoost).where(ActiveBoost.user_id == user_id))
    boosts = list(result.scalars().all())

    total = 0.0
    for b in boosts:
        if b.expires_at <= now:
            await session.delete(b)
        elif b.boost_type == boost_type:
            total += b.value
    return total
