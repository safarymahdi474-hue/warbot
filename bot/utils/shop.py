from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import Purchase, PurchaseRequest, ShopItem, User, UserInventory


async def list_shop_items(session: AsyncSession) -> list[ShopItem]:
    result = await session.execute(
        select(ShopItem).options(selectinload(ShopItem.reward_item_type)).where(ShopItem.active == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def grant_purchase_reward(session: AsyncSession, user: User, shop_item: ShopItem, reference: str) -> None:
    """بعد از تایید ادمین صدا زده میشه."""
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
            stars_paid=0,
            telegram_payment_charge_id=reference,
        )
    )


def build_reward_summary(shop_item: ShopItem) -> str:
    parts = []
    if shop_item.reward_gold:
        parts.append(f"💰{shop_item.reward_gold}")
    if shop_item.reward_coins:
        parts.append(f"🪙{shop_item.reward_coins}")
    if shop_item.reward_item_quantity:
        parts.append(f"🎁×{shop_item.reward_item_quantity}")
    return " ".join(parts) if parts else "-"


async def create_purchase_request(
    session: AsyncSession, user: User, shop_item: ShopItem, receipt_file_id: str
) -> PurchaseRequest:
    request = PurchaseRequest(
        user_id=user.id,
        shop_item_id=shop_item.id,
        receipt_file_id=receipt_file_id,
        status="pending",
    )
    session.add(request)
    await session.flush()
    return request


async def get_pending_requests(session: AsyncSession, limit: int = 15) -> list[PurchaseRequest]:
    result = await session.execute(
        select(PurchaseRequest)
        .options(selectinload(PurchaseRequest.user), selectinload(PurchaseRequest.shop_item))
        .where(PurchaseRequest.status == "pending")
        .order_by(PurchaseRequest.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def approve_purchase_request(
    session: AsyncSession, request: PurchaseRequest, admin_telegram_id: int
) -> tuple[User, ShopItem] | str:
    """خروجی: (User, ShopItem) در صورت موفقیت، وگرنه پیام خطا."""
    if request.status != "pending":
        return "این درخواست قبلاً بررسی شده."

    user = await session.get(User, request.user_id)
    shop_item = await session.get(ShopItem, request.shop_item_id)
    if user is None or shop_item is None:
        return "کاربر یا آیتم پیدا نشد."

    await grant_purchase_reward(session, user, shop_item, f"card:{request.id}")

    request.status = "approved"
    request.reviewed_by_telegram_id = admin_telegram_id
    request.reviewed_at = datetime.utcnow()
    return user, shop_item


def reject_purchase_request(request: PurchaseRequest, admin_telegram_id: int, reason: str) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا."""
    if request.status != "pending":
        return "این درخواست قبلاً بررسی شده."

    request.status = "rejected"
    request.reviewed_by_telegram_id = admin_telegram_id
    request.reviewed_at = datetime.utcnow()
    reason = (reason or "").strip()
    request.admin_reply = reason[:256] if reason and reason != "-" else None
    return None


# ---------------------------------------------------------------------------
# مدیریت کامل فروشگاه از پنل ادمین (افزودن/ویرایش/حذف/فعال-غیرفعال)
# ---------------------------------------------------------------------------

async def list_all_shop_items(session: AsyncSession) -> list[ShopItem]:
    """همه‌ی آیتم‌ها (فعال و غیرفعال) - برای پنل مدیریت ادمین."""
    result = await session.execute(select(ShopItem).order_by(ShopItem.id))
    return list(result.scalars().all())


async def create_shop_item(
    session: AsyncSession,
    name_fa: str,
    icon: str,
    description: str,
    price_toman: int,
    reward_gold: int = 0,
    reward_coins: int = 0,
) -> ShopItem:
    import re
    import secrets

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name_fa).strip("_").lower() or "item"
    key = f"custom_{slug}_{secrets.token_hex(3)}"

    item = ShopItem(
        key=key,
        name_fa=name_fa[:128],
        icon=icon[:8] if icon else "🛍️",
        description=description[:256],
        price_toman=max(0, price_toman),
        reward_gold=max(0, reward_gold),
        reward_coins=max(0, reward_coins),
        active=True,
    )
    session.add(item)
    await session.flush()
    return item


async def update_shop_item_price(session: AsyncSession, item_id: int, price_toman: int) -> str | None:
    item = await session.get(ShopItem, item_id)
    if item is None:
        return "این آیتم پیدا نشد."
    if price_toman < 0:
        return "قیمت نمی‌تونه منفی باشه."
    item.price_toman = price_toman
    return None


async def update_shop_item_text(session: AsyncSession, item_id: int, name_fa: str, description: str) -> str | None:
    item = await session.get(ShopItem, item_id)
    if item is None:
        return "این آیتم پیدا نشد."
    item.name_fa = name_fa[:128]
    item.description = description[:256]
    return None


async def toggle_shop_item_active(session: AsyncSession, item_id: int) -> str | None:
    item = await session.get(ShopItem, item_id)
    if item is None:
        return "این آیتم پیدا نشد."
    item.active = not item.active
    return None


async def delete_shop_item(session: AsyncSession, item_id: int) -> str | None:
    item = await session.get(ShopItem, item_id)
    if item is None:
        return "این آیتم پیدا نشد."
    await session.delete(item)
    return None
