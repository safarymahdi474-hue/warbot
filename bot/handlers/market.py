from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import AuctionListing, ItemType, MarketListing, User
from bot.utils.items import get_inventory
from bot.utils.exchange import RESOURCE_LABELS as EXCHANGE_RESOURCE_LABELS
from bot.utils.exchange import SELL_PRICES, buy_price, buy_resource, sell_resource
from bot.utils.market import (
    RESOURCE_LABELS,
    buy_market_listing,
    cancel_market_listing,
    create_auction_listing,
    create_market_listing,
    finish_expired_auctions,
    list_active_auctions,
    list_active_market_listings,
    place_bid,
)

router = Router(name="market")


class SellListing(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_price = State()


class ExchangeAction(StatesGroup):
    waiting_for_quantity = State()


class AuctionCreation(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_price = State()


class AuctionBid(StatesGroup):
    waiting_for_amount = State()


# ---------------------------------------------------------------------------
# منوی اصلی بازار
# ---------------------------------------------------------------------------

def market_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💱 صرافی منابع (آنی)", callback_data="show_exchange")],
            [InlineKeyboardButton(text="🛒 مرور بازار آیتم‌ها", callback_data="browse_market")],
            [InlineKeyboardButton(text="📤 فروش آیتم در بازار", callback_data="sell_market_start")],
            [InlineKeyboardButton(text="🔨 مرور حراج‌ها", callback_data="browse_auctions")],
            [InlineKeyboardButton(text="🔼 ایجاد حراج", callback_data="create_auction_start")],
            [InlineKeyboardButton(text="📋 آگهی‌های من", callback_data="my_listings")],
        ]
    )


@router.message(Command("market"))
async def cmd_market(message: Message) -> None:
    await message.answer("🏪 بازار و حراج:", reply_markup=market_menu_keyboard())


@router.callback_query(F.data == "show_market_menu")
async def cb_market_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🏪 بازار و حراج:", reply_markup=market_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# صرافی منابع - خرید/فروش آنی با ربات (بدون آگهی)
# ---------------------------------------------------------------------------

def exchange_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for r in EXCHANGE_RESOURCE_LABELS:
        rows.append(
            [
                InlineKeyboardButton(text=f"🔻 فروش {EXCHANGE_RESOURCE_LABELS[r]}", callback_data=f"exchange:sell:{r}"),
                InlineKeyboardButton(text=f"🔺 خرید {EXCHANGE_RESOURCE_LABELS[r]}", callback_data=f"exchange:buy:{r}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_exchange_text(user: User) -> str:
    lines = ["💱 <b>صرافی منابع</b>\nخرید/فروش آنی با ربات، بدون نیاز به آگهی یا منتظر خریدار موندن.\n"]
    for r, label in EXCHANGE_RESOURCE_LABELS.items():
        owned = getattr(user, r)
        lines.append(
            f"{label}: موجودی تو {owned} | فروش به ربات: 💰{SELL_PRICES[r]}/واحد | "
            f"خرید از ربات: 💰{buy_price(r)}/واحد"
        )
    lines.append(f"\n💰 طلای تو: {user.gold}")
    return "\n".join(lines)


async def _exchange_view(telegram_id: int):
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None
        return build_exchange_text(user), exchange_keyboard()


@router.callback_query(F.data == "show_exchange")
async def cb_show_exchange(callback: CallbackQuery) -> None:
    text, keyboard = await _exchange_view(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:"))
async def cb_exchange_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, action, resource_type = callback.data.split(":")
    await state.update_data(action=action, resource_type=resource_type)

    if action == "sell":
        prompt = f"چند تا {EXCHANGE_RESOURCE_LABELS[resource_type]} می‌خوای بفروشی؟ (فقط عدد بفرست)"
    else:
        prompt = f"چند تا {EXCHANGE_RESOURCE_LABELS[resource_type]} می‌خوای بخری؟ (فقط عدد بفرست)"

    await callback.message.answer(prompt)
    await state.set_state(ExchangeAction.waiting_for_quantity)
    await callback.answer()


@router.message(ExchangeAction.waiting_for_quantity)
async def process_exchange_quantity(message: Message, state: FSMContext) -> None:
    try:
        quantity = int((message.text or "").strip())
        assert quantity > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return

    data = await state.get_data()
    await state.clear()
    action, resource_type = data["action"], data["resource_type"]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        if action == "sell":
            success_msg, error_msg = sell_resource(user, resource_type, quantity)
        else:
            success_msg, error_msg = buy_resource(user, resource_type, quantity)

        if error_msg:
            await message.answer(f"❌ {error_msg}")
            return

        user.market_trades_total += 1
        await session.commit()

    await message.answer(success_msg, reply_markup=market_menu_keyboard())


# ---------------------------------------------------------------------------
# مرور بازار / خرید
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "browse_market")
async def cb_browse_market(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return
        listings = await list_active_market_listings(session, exclude_seller_id=user.id)

    rows = []
    lines = ["🛒 <b>بازار</b>\n"]
    if not listings:
        lines.append("فعلاً هیچ آگهی فعالی نیست.")
    for listing in listings:
        if listing.resource_type:
            label = f"{RESOURCE_LABELS[listing.resource_type]} ×{listing.quantity}"
        else:
            label = f"{listing.item_type.icon} {listing.item_type.name_fa} ×{listing.quantity}"
        lines.append(f"{label} — 💰{listing.price_gold}")
        rows.append(
            [InlineKeyboardButton(text=f"🛒 خرید ({label} — 💰{listing.price_gold})", callback_data=f"buy_listing:{listing.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_listing:"))
async def cb_buy_listing(callback: CallbackQuery) -> None:
    listing_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        listing = await session.get(MarketListing, listing_id)
        if listing is None:
            await callback.answer("این آگهی پیدا نشد.", show_alert=True)
            return

        error = await buy_market_listing(session, user, listing)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer("✅ خرید انجام شد!", show_alert=True)

    await cb_browse_market(callback)


# ---------------------------------------------------------------------------
# فروش در بازار (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "sell_market_start")
async def cb_sell_market_start(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        items = await get_inventory(session, user.id) if user else []

    rows = [
        [
            InlineKeyboardButton(
                text=f"{ui.item_type.icon} {ui.item_type.name_fa} (×{ui.quantity})",
                callback_data=f"sell_item:{ui.item_type_id}",
            )
        ]
        for ui in items
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])

    if not items:
        await callback.message.edit_text(
            "آیتمی برای فروش نداری.\n\n(برای فروش منابع مثل آهن/نفت/غذا از «💱 صرافی منابع» استفاده کن.)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    else:
        await callback.message.edit_text(
            "کدوم آیتم رو می‌خوای توی بازار بذاری؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("sell_item:"))
async def cb_sell_item(callback: CallbackQuery, state: FSMContext) -> None:
    item_type_id = int(callback.data.split(":")[1])
    await state.update_data(item_type_id=item_type_id)
    await callback.message.answer("چند عدد می‌خوای بفروشی؟ (فقط عدد بفرست)")
    await state.set_state(SellListing.waiting_for_quantity)
    await callback.answer()


@router.message(SellListing.waiting_for_quantity)
async def process_sell_quantity(message: Message, state: FSMContext) -> None:
    try:
        quantity = int((message.text or "").strip())
        assert quantity > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return
    await state.update_data(quantity=quantity)
    await message.answer("قیمت کل (به طلا) چقدر باشه؟ (فقط عدد بفرست)")
    await state.set_state(SellListing.waiting_for_price)


@router.message(SellListing.waiting_for_price)
async def process_sell_price(message: Message, state: FSMContext) -> None:
    try:
        price = int((message.text or "").strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return

    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        listing = await create_market_listing(
            session, user, data["quantity"], price, item_type_id=data["item_type_id"]
        )

        if isinstance(listing, str):
            await message.answer(f"❌ {listing}")
            return

        await session.commit()

    await message.answer("✅ آگهی ثبت شد و توی بازار قابل مشاهده‌ست!", reply_markup=market_menu_keyboard())


# ---------------------------------------------------------------------------
# مرور حراج‌ها / پیشنهاد
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "browse_auctions")
async def cb_browse_auctions(callback: CallbackQuery) -> None:
    async with get_session() as session:
        await finish_expired_auctions(session)
        await session.commit()
        auctions = await list_active_auctions(session)

    rows = []
    lines = ["🔨 <b>حراج‌های فعال</b>\n"]
    if not auctions:
        lines.append("فعلاً هیچ حراج فعالی نیست.")
    for a in auctions:
        current = a.current_bid if a.current_bid > 0 else a.starting_price
        label_state = "پیشنهاد فعلی" if a.current_bid > 0 else "قیمت پایه"
        lines.append(
            f"{a.item_type.icon} {a.item_type.name_fa} ×{a.quantity} — {label_state}: 💰{current}"
        )
        rows.append(
            [InlineKeyboardButton(text=f"💰 پیشنهاد بده ({a.item_type.name_fa})", callback_data=f"bid_on:{a.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bid_on:"))
async def cb_bid_on(callback: CallbackQuery, state: FSMContext) -> None:
    auction_id = int(callback.data.split(":")[1])
    await state.update_data(auction_id=auction_id)
    await callback.message.answer("چقدر طلا پیشنهاد می‌دی؟ (فقط عدد بفرست)")
    await state.set_state(AuctionBid.waiting_for_amount)
    await callback.answer()


@router.message(AuctionBid.waiting_for_amount)
async def process_bid_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int((message.text or "").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return

    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        auction = await session.get(AuctionListing, data["auction_id"])
        if auction is None:
            await message.answer("این حراج دیگه پیدا نشد.")
            return

        error = await place_bid(session, user, auction, amount)
        if error:
            await message.answer(f"❌ {error}")
            return

        await session.commit()

    await message.answer("✅ پیشنهادت ثبت شد!", reply_markup=market_menu_keyboard())


# ---------------------------------------------------------------------------
# ایجاد حراج (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "create_auction_start")
async def cb_create_auction_start(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        items = await get_inventory(session, user.id) if user else []

    rows = [
        [InlineKeyboardButton(text=f"{ui.item_type.icon} {ui.item_type.name_fa} (×{ui.quantity})", callback_data=f"auction_item:{ui.item_type_id}")]
        for ui in items
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])

    if not items:
        await callback.message.edit_text(
            "هیچ آیتمی برای حراج گذاشتن نداری.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    else:
        await callback.message.edit_text(
            "کدوم آیتم رو می‌خوای حراج بذاری؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("auction_item:"))
async def cb_auction_item(callback: CallbackQuery, state: FSMContext) -> None:
    item_type_id = int(callback.data.split(":")[1])
    await state.update_data(item_type_id=item_type_id)
    await callback.message.answer("چند عدد می‌خوای حراج بذاری؟ (فقط عدد بفرست)")
    await state.set_state(AuctionCreation.waiting_for_quantity)
    await callback.answer()


@router.message(AuctionCreation.waiting_for_quantity)
async def process_auction_quantity(message: Message, state: FSMContext) -> None:
    try:
        quantity = int((message.text or "").strip())
        assert quantity > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return
    await state.update_data(quantity=quantity)
    await message.answer("قیمت پایه (به طلا) چقدر باشه؟ (فقط عدد بفرست)")
    await state.set_state(AuctionCreation.waiting_for_price)


def duration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="۱ ساعت", callback_data="auction_duration:1"),
                InlineKeyboardButton(text="۶ ساعت", callback_data="auction_duration:6"),
            ],
            [
                InlineKeyboardButton(text="۲۴ ساعت", callback_data="auction_duration:24"),
                InlineKeyboardButton(text="۴۸ ساعت", callback_data="auction_duration:48"),
            ],
        ]
    )


@router.message(AuctionCreation.waiting_for_price)
async def process_auction_price(message: Message, state: FSMContext) -> None:
    try:
        price = int((message.text or "").strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return
    await state.update_data(starting_price=price)
    await message.answer("مدت حراج چقدر باشه؟", reply_markup=duration_keyboard())


@router.callback_query(F.data.startswith("auction_duration:"))
async def cb_auction_duration(callback: CallbackQuery, state: FSMContext) -> None:
    duration_hours = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        auction = await create_auction_listing(
            session, user, data["item_type_id"], data["quantity"], data["starting_price"], duration_hours
        )
        if isinstance(auction, str):
            await callback.answer(auction, show_alert=True)
            return

        await session.commit()

    await callback.message.edit_text("✅ حراج ثبت شد!", reply_markup=market_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# آگهی‌های من (لغو آگهی‌های بازار + مشاهده حراج‌های خودم)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "my_listings")
async def cb_my_listings(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        result = await session.execute(
            select(MarketListing)
            .options(selectinload(MarketListing.item_type))
            .where(MarketListing.seller_id == user.id, MarketListing.status == "active")
        )
        my_market = list(result.scalars().all())

        await finish_expired_auctions(session)
        await session.commit()
        result = await session.execute(
            select(AuctionListing)
            .options(selectinload(AuctionListing.item_type))
            .where(AuctionListing.seller_id == user.id, AuctionListing.status == "active")
        )
        my_auctions = list(result.scalars().all())

    lines = ["📋 <b>آگهی‌های من</b>\n"]
    rows = []

    if my_market:
        lines.append("🛒 <b>بازار:</b>")
        for listing in my_market:
            label = (
                f"{RESOURCE_LABELS[listing.resource_type]} ×{listing.quantity}"
                if listing.resource_type
                else f"{listing.item_type.icon} {listing.item_type.name_fa} ×{listing.quantity}"
            )
            lines.append(f"  {label} — 💰{listing.price_gold}")
            rows.append(
                [InlineKeyboardButton(text=f"❌ لغو ({label})", callback_data=f"cancel_listing:{listing.id}")]
            )
    else:
        lines.append("🛒 آگهی فعالی در بازار نداری.")

    if my_auctions:
        lines.append("\n🔨 <b>حراج:</b> (قابل لغو نیست، صبر کن تا تموم بشه)")
        for a in my_auctions:
            current = a.current_bid if a.current_bid > 0 else a.starting_price
            lines.append(f"  {a.item_type.icon} {a.item_type.name_fa} ×{a.quantity} — فعلی: 💰{current}")

    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_market_menu")])

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_listing:"))
async def cb_cancel_listing(callback: CallbackQuery) -> None:
    listing_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        listing = await session.get(MarketListing, listing_id)
        if listing is None:
            await callback.answer("این آگهی پیدا نشد.", show_alert=True)
            return

        error = await cancel_market_listing(session, user, listing)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer("✅ آگهی لغو شد و کالا بهت برگشت.", show_alert=True)

    await cb_my_listings(callback)
