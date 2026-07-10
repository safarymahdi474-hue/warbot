from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Purchase, ShopItem, User, UserInventory


async def list_shop_items(session: AsyncSession) -> list[ShopItem]:
    result = await session.execute(
        select(ShopItem).options(selectinload(ShopItem.reward_item_type)).where(ShopItem.active == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def grant_purchase_reward(
    session: AsyncSession, user: User, shop_item: ShopItem, telegram_payment_charge_id: str
) -> None:
    """بعد از تایید پرداخت موفق (successful_payment) صدا زده میشه."""
    user.gold += shop_item.reward_gold
    user.coins += shop_item.reward_coins

    if shop_item.reward_item_type_id and shop_item.reward_item_quantity:
        result = await session.execute(
            select(UserInventory).where(
                UserInventory.user_id == user.id, UserInventory.item_type_id == shop_item.reward_item_type_id
            )
        )
        inv = result.scalar_one_or_none()
        if inv is None:
            inv = UserInventory(
                user_id=user.id, item_type_id=shop_item.reward_item_type_id, quantity=0
            )
            session.add(inv)
        inv.quantity += shop_item.reward_item_quantity

    session.add(
        Purchase(
            user_id=user.id,
            shop_item_id=shop_item.id,
            stars_paid=shop_item.price_stars,
            telegram_payment_charge_id=telegram_payment_charge_id,
        )
    )
