from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.models import AuctionListing, MarketListing, User, UserInventory
from bot.utils.context import current_room, room_condition

RESOURCE_LABELS = {"iron": "⛏️ آهن", "oil": "🛢️ نفت", "food": "🌾 غذا"}


# ---------------------------------------------------------------------------
# کمکی: افزودن/کسر از اینونتوری یا منابع
# ---------------------------------------------------------------------------

async def _get_or_create_inventory_row(session: AsyncSession, user_id: int, item_type_id: int) -> UserInventory:
    result = await session.execute(
        select(UserInventory).where(
            UserInventory.user_id == user_id, UserInventory.item_type_id == item_type_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserInventory(user_id=user_id, item_type_id=item_type_id, quantity=0)
        session.add(row)
        await session.flush()
    return row


def _add_resource(user: User, resource_type: str, amount: int) -> None:
    if resource_type == "iron":
        user.iron = min(user.max_iron, user.iron + amount)
    elif resource_type == "oil":
        user.oil = min(user.max_oil, user.oil + amount)
    elif resource_type == "food":
        user.food = min(user.max_food, user.food + amount)


def _get_resource(user: User, resource_type: str) -> int:
    return getattr(user, resource_type)


def _sub_resource(user: User, resource_type: str, amount: int) -> None:
    setattr(user, resource_type, getattr(user, resource_type) - amount)


# ---------------------------------------------------------------------------
# بازار (خرید فوری)
# ---------------------------------------------------------------------------

async def create_market_listing(
    session: AsyncSession,
    seller: User,
    quantity: int,
    price_gold: int,
    resource_type: str | None = None,
    item_type_id: int | None = None,
) -> MarketListing | str:
    if quantity <= 0 or price_gold <= 0:
        return "تعداد و قیمت باید مثبت باشن."

    if resource_type is not None:
        if _get_resource(seller, resource_type) < quantity:
            return "به این مقدار از این منبع رو نداری."
        _sub_resource(seller, resource_type, quantity)
    elif item_type_id is not None:
        inv = await _get_or_create_inventory_row(session, seller.id, item_type_id)
        if inv.quantity < quantity:
            return "به این مقدار از این آیتم رو نداری."
        inv.quantity -= quantity
    else:
        return "چیزی برای فروش انتخاب نشده."

    listing = MarketListing(
        seller_id=seller.id,
        room_id=current_room(),
        resource_type=resource_type,
        item_type_id=item_type_id,
        quantity=quantity,
        price_gold=price_gold,
        status="active",
    )
    session.add(listing)
    return listing


async def buy_market_listing(session: AsyncSession, buyer: User, listing: MarketListing) -> str | None:
    if listing.status != "active":
        return "این آگهی دیگه فعال نیست."
    if listing.room_id != current_room():
        return "این آگهی مال این گروه/چت نیست."
    if listing.seller_id == buyer.id:
        return "نمی‌تونی از خودت خرید کنی."
    if buyer.gold < listing.price_gold:
        return "طلای کافی نداری."

    seller = await session.get(User, listing.seller_id)
    tax = int(listing.price_gold * settings.MARKET_TAX_PERCENT / 100)
    buyer.gold -= listing.price_gold
    if seller is not None:
        seller.gold += listing.price_gold - tax
        seller.market_trades_total += 1
    buyer.market_trades_total += 1

    if listing.resource_type is not None:
        _add_resource(buyer, listing.resource_type, listing.quantity)
    elif listing.item_type_id is not None:
        inv = await _get_or_create_inventory_row(session, buyer.id, listing.item_type_id)
        inv.quantity += listing.quantity

    listing.status = "sold"
    return None


async def cancel_market_listing(session: AsyncSession, user: User, listing: MarketListing) -> str | None:
    if listing.seller_id != user.id:
        return "این آگهی مال تو نیست."
    if listing.status != "active":
        return "این آگهی دیگه فعال نیست."

    if listing.resource_type is not None:
        _add_resource(user, listing.resource_type, listing.quantity)
    elif listing.item_type_id is not None:
        inv = await _get_or_create_inventory_row(session, user.id, listing.item_type_id)
        inv.quantity += listing.quantity

    listing.status = "cancelled"
    return None


async def list_active_market_listings(session: AsyncSession, exclude_seller_id: int | None = None) -> list[MarketListing]:
    query = select(MarketListing).options(selectinload(MarketListing.item_type)).where(
        MarketListing.status == "active", room_condition(MarketListing.room_id)
    )
    if exclude_seller_id is not None:
        query = query.where(MarketListing.seller_id != exclude_seller_id)
    result = await session.execute(query.order_by(MarketListing.created_at.desc()).limit(15))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# حراج (مزایده)
# ---------------------------------------------------------------------------

async def create_auction_listing(
    session: AsyncSession, seller: User, item_type_id: int, quantity: int, starting_price: int, duration_hours: int
) -> AuctionListing | str:
    if quantity <= 0 or starting_price <= 0:
        return "تعداد و قیمت پایه باید مثبت باشن."
    if not (settings.AUCTION_MIN_DURATION_HOURS <= duration_hours <= settings.AUCTION_MAX_DURATION_HOURS):
        return f"مدت حراج باید بین {settings.AUCTION_MIN_DURATION_HOURS} تا {settings.AUCTION_MAX_DURATION_HOURS} ساعت باشه."

    inv = await _get_or_create_inventory_row(session, seller.id, item_type_id)
    if inv.quantity < quantity:
        return "به این مقدار از این آیتم رو نداری."
    inv.quantity -= quantity

    auction = AuctionListing(
        seller_id=seller.id,
        room_id=current_room(),
        item_type_id=item_type_id,
        quantity=quantity,
        starting_price=starting_price,
        current_bid=0,
        current_bidder_id=None,
        ends_at=datetime.utcnow() + timedelta(hours=duration_hours),
        status="active",
    )
    session.add(auction)
    return auction


async def place_bid(session: AsyncSession, bidder: User, auction: AuctionListing, amount: int) -> str | None:
    if auction.status != "active":
        return "این حراج دیگه فعال نیست."
    if auction.room_id != current_room():
        return "این حراج مال این گروه/چت نیست."
    if auction.seller_id == bidder.id:
        return "نمی‌تونی روی حراج خودت پیشنهاد بدی."
    if datetime.utcnow() >= auction.ends_at:
        return "زمان این حراج تموم شده."

    min_required = (
        auction.starting_price
        if auction.current_bid == 0
        else int(auction.current_bid * (1 + settings.AUCTION_MIN_BID_INCREMENT_PERCENT / 100))
    )
    if amount < min_required:
        return f"پیشنهادت باید حداقل {min_required} طلا باشه."
    if bidder.gold < amount:
        return "طلای کافی نداری."

    # پیشنهاد قبلی رو برگردون
    if auction.current_bidder_id is not None:
        previous_bidder = await session.get(User, auction.current_bidder_id)
        if previous_bidder is not None:
            previous_bidder.gold += auction.current_bid

    bidder.gold -= amount
    auction.current_bid = amount
    auction.current_bidder_id = bidder.id
    return None


async def list_active_auctions(session: AsyncSession) -> list[AuctionListing]:
    result = await session.execute(
        select(AuctionListing)
        .options(selectinload(AuctionListing.item_type))
        .where(AuctionListing.status == "active", room_condition(AuctionListing.room_id))
        .order_by(AuctionListing.ends_at.asc())
        .limit(15)
    )
    return list(result.scalars().all())


async def finish_expired_auctions(session: AsyncSession) -> list[AuctionListing]:
    now = datetime.utcnow()
    result = await session.execute(select(AuctionListing).where(AuctionListing.status == "active"))
    active = list(result.scalars().all())

    finished = []
    for auction in active:
        if auction.ends_at <= now:
            if auction.current_bidder_id is not None:
                winner_inv = await _get_or_create_inventory_row(
                    session, auction.current_bidder_id, auction.item_type_id
                )
                winner_inv.quantity += auction.quantity

                winner = await session.get(User, auction.current_bidder_id)
                if winner is not None:
                    winner.market_trades_total += 1

                seller = await session.get(User, auction.seller_id)
                if seller is not None:
                    tax = int(auction.current_bid * settings.MARKET_TAX_PERCENT / 100)
                    seller.gold += auction.current_bid - tax
                    seller.market_trades_total += 1
            else:
                seller_inv = await _get_or_create_inventory_row(
                    session, auction.seller_id, auction.item_type_id
                )
                seller_inv.quantity += auction.quantity

            auction.status = "finished"
            finished.append(auction)
    return finished
