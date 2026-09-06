from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.config import settings
from bot.database.db import get_session
from bot.database.models import PurchaseRequest, ShopItem, User
from bot.utils.context import user_scope
from bot.utils.game_settings import (
    get_payment_card_holder,
    get_payment_card_number,
    set_payment_card_holder,
    set_payment_card_number,
)
from bot.utils.shop import (
    approve_purchase_request,
    build_reward_summary,
    create_purchase_request,
    create_shop_item,
    delete_shop_item,
    get_pending_requests,
    list_all_shop_items,
    list_shop_items,
    reject_purchase_request,
    toggle_shop_item_active,
    update_shop_item_price,
    update_shop_item_text,
)

router = Router(name="shop")


class BuyShopItem(StatesGroup):
    waiting_for_receipt = State()


class RejectPurchase(StatesGroup):
    waiting_for_reason = State()


class ShopAdminAdd(StatesGroup):
    waiting_for_info = State()


class ShopAdminEditPrice(StatesGroup):
    waiting_for_price = State()


class ShopAdminEditText(StatesGroup):
    waiting_for_text = State()


class ShopAdminSetCard(StatesGroup):
    waiting_for_info = State()


def shop_keyboard(items: list[ShopItem]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{i.icon} {i.name_fa} — 💳 {i.price_toman:,} تومن", callback_data=f"buy_shop_item:{i.id}"
            )
        ]
        for i in items
    ]
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_shop_text(items: list[ShopItem]) -> str:
    lines = ["🛍️ <b>فروشگاه پک‌های ویژه</b>\nخرید با کارت‌به‌کارت - بعد از ارسال فیش، ادمین تاییدش می‌کنه.\n"]
    for i in items:
        lines.append(f"{i.icon} <b>{i.name_fa}</b> — 💳 {i.price_toman:,} تومن\n   {i.description}")
    return "\n\n".join(lines)


@router.message(Command("shop"))
async def cmd_shop(message: Message) -> None:
    async with get_session() as session:
        items = await list_shop_items(session)
    await message.answer(build_shop_text(items), reply_markup=shop_keyboard(items), parse_mode="HTML")


@router.callback_query(F.data == "show_shop")
async def cb_shop(callback: CallbackQuery) -> None:
    async with get_session() as session:
        items = await list_shop_items(session)
    try:
        await callback.message.edit_text(
            build_shop_text(items), reply_markup=shop_keyboard(items), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(build_shop_text(items), reply_markup=shop_keyboard(items), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# خرید یک آیتم - نمایش کارت + دریافت فیش از کاربر
# ---------------------------------------------------------------------------

def receipt_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 انصراف", callback_data="show_shop")]]
    )


@router.callback_query(F.data.startswith("buy_shop_item:"))
async def cb_buy_shop_item(callback: CallbackQuery, state: FSMContext) -> None:
    shop_item_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        shop_item = await session.get(ShopItem, shop_item_id)
        if shop_item is None or not shop_item.active:
            await callback.answer("این آیتم دیگه در دسترس نیست.", show_alert=True)
            return

    await state.update_data(shop_item_id=shop_item_id)
    async with get_session() as session:
        card_number = await get_payment_card_number(session)
        card_holder = await get_payment_card_holder(session)

    await callback.message.answer(
        f"💳 <b>پرداخت کارت‌به‌کارت</b>\n\n"
        f"مبلغ: <b>{shop_item.price_toman:,} تومن</b>\n"
        f"شماره کارت: <code>{card_number}</code>\n"
        f"به نام: {card_holder}\n\n"
        f"بعد از واریز، یه عکس از فیش/رسید تراکنش رو همین‌جا بفرست تا برای ادمین ارسال بشه.",
        reply_markup=receipt_prompt_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(BuyShopItem.waiting_for_receipt)
    await callback.answer()


@router.message(BuyShopItem.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    shop_item_id = data.get("shop_item_id")

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        shop_item = await session.get(ShopItem, shop_item_id) if shop_item_id else None

        if user is None or shop_item is None:
            await message.answer("❌ خطایی پیش اومد. دوباره از /shop امتحان کن.")
            return

        receipt_file_id = message.photo[-1].file_id
        request = await create_purchase_request(session, user, shop_item, receipt_file_id)
        await session.commit()

        request_id = request.id
        nickname = user.nickname
        price_toman = shop_item.price_toman
        item_name = shop_item.name_fa
        item_icon = shop_item.icon

    await message.answer(
        "✅ فیشت ثبت شد و برای بررسی به ادمین ارسال شد.\nنتیجه‌ش رو بهت اطلاع می‌دیم."
    )

    caption = (
        f"🧾 <b>درخواست خرید جدید</b>\n\n"
        f"👤 کاربر: {nickname}\n"
        f"{item_icon} آیتم: {item_name}\n"
        f"💳 مبلغ: {price_toman:,} تومن"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_purchase:{request_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"reject_purchase:{request_id}"),
            ]
        ]
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_photo(
                admin_id, receipt_file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception:
            pass  # ادمین شاید هنوز چت خصوصی با ربات رو باز نکرده


@router.message(BuyShopItem.waiting_for_receipt)
async def process_receipt_wrong_type(message: Message) -> None:
    await message.answer("لطفاً عکس فیش/رسید تراکنش رو بفرست (نه متن).")


# ---------------------------------------------------------------------------
# تایید/رد خرید (فقط ادمین)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("approve_purchase:"))
async def cb_approve_purchase(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه این کارو بکنه.", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        request = await session.get(PurchaseRequest, request_id)
        if request is None:
            await callback.answer("این درخواست پیدا نشد.", show_alert=True)
            return

        result = await approve_purchase_request(session, request, callback.from_user.id)
        if isinstance(result, str):
            await callback.answer(result, show_alert=True)
            return

        user, shop_item = result
        reward_summary = build_reward_summary(shop_item)
        user_telegram_id = user.telegram_id
        item_name = shop_item.name_fa
        await session.commit()

    try:
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ <b>تایید شد.</b>", parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer("✅ تایید شد و جایزه به کاربر داده شد.", show_alert=True)

    try:
        await callback.bot.send_message(
            user_telegram_id,
            f"🎉 خرید «{item_name}» تایید شد!\nدریافتی: {reward_summary}\n\n🙏 ممنون از حمایتت!",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject_purchase:"))
async def cb_reject_purchase(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه این کارو بکنه.", show_alert=True)
        return

    request_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        request = await session.get(PurchaseRequest, request_id)
        if request is None or request.status != "pending":
            await callback.answer("این درخواست دیگه در انتظار بررسی نیست.", show_alert=True)
            return

    await state.update_data(
        request_id=request_id,
        review_chat_id=callback.message.chat.id,
        review_message_id=callback.message.message_id,
        review_caption=callback.message.caption or "",
    )
    await callback.message.answer("دلیل رد این خرید رو بنویس (یا برای رد بدون دلیل «-» بفرست):")
    await state.set_state(RejectPurchase.waiting_for_reason)
    await callback.answer()


@router.message(RejectPurchase.waiting_for_reason)
async def process_reject_purchase_reason(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    reason = (message.text or "-").strip()
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        request = await session.get(PurchaseRequest, data["request_id"])
        if request is None:
            await message.answer("این درخواست دیگه پیدا نشد.")
            return

        error = reject_purchase_request(request, message.from_user.id, reason)
        if error:
            await message.answer(f"❌ {error}")
            return

        user = await session.get(User, request.user_id)
        user_telegram_id = user.telegram_id if user else None
        await session.commit()

    try:
        await message.bot.edit_message_caption(
            chat_id=data["review_chat_id"],
            message_id=data["review_message_id"],
            caption=data["review_caption"] + "\n\n❌ <b>رد شد.</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer("✅ رد خرید ثبت شد.")

    if user_telegram_id is not None:
        note = f"\nدلیل: {reason}" if reason and reason != "-" else ""
        try:
            await message.bot.send_message(user_telegram_id, f"❌ خریدت رد شد.{note}")
        except Exception:
            pass


@router.message(Command("pendingpurchases"))
async def cmd_pending_purchases(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    async with get_session() as session:
        pending = await get_pending_requests(session)

        if not pending:
            await message.answer("🧾 هیچ درخواست خرید در انتظار بررسی نیست.")
            return

        for request in pending:
            caption = (
                f"🧾 <b>درخواست خرید</b>\n\n"
                f"👤 کاربر: {request.user.nickname}\n"
                f"{request.shop_item.icon} آیتم: {request.shop_item.name_fa}\n"
                f"💳 مبلغ: {request.shop_item.price_toman:,} تومن"
            )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_purchase:{request.id}"),
                        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_purchase:{request.id}"),
                    ]
                ]
            )
            await message.answer_photo(request.receipt_file_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")


# ---------------------------------------------------------------------------
# پنل مدیریت کامل فروشگاه (فقط ادمین) - افزودن/ویرایش/حذف/فعال-غیرفعال + کارت
# ---------------------------------------------------------------------------

def shop_admin_keyboard(items: list[ShopItem]) -> InlineKeyboardMarkup:
    rows = []
    for i in items:
        status = "✅" if i.active else "⛔️"
        rows.append(
            [
                InlineKeyboardButton(text=f"{status} {i.icon} {i.name_fa} ({i.price_toman:,}ت)", callback_data=f"noop_shop_item:{i.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="✏️ قیمت", callback_data=f"shopadm_price:{i.id}"),
                InlineKeyboardButton(text="📝 متن", callback_data=f"shopadm_text:{i.id}"),
                InlineKeyboardButton(text="🔁 فعال/غیرفعال", callback_data=f"shopadm_toggle:{i.id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"shopadm_delete:{i.id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ افزودن آیتم جدید", callback_data="shopadm_add")])
    rows.append([InlineKeyboardButton(text="💳 تنظیم شماره کارت", callback_data="shopadm_setcard")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _build_shop_admin_view() -> tuple[str, InlineKeyboardMarkup]:
    async with get_session() as session:
        items = await list_all_shop_items(session)
        card_number = await get_payment_card_number(session)
        card_holder = await get_payment_card_holder(session)

    text = (
        "🛠️ <b>مدیریت فروشگاه</b>\n\n"
        f"💳 کارت فعلی: <code>{card_number}</code>\n"
        f"👤 به نام: {card_holder}\n\n"
        "زیر هر آیتم می‌تونی قیمت/متن/فعال‌بودن/حذفش رو تغییر بدی:"
    )
    return text, shop_admin_keyboard(items)


@router.message(Command("shopadmin"))
async def cmd_shop_admin(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return
    text, keyboard = await _build_shop_admin_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_shop_admin")
async def cb_shop_admin(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    text, keyboard = await _build_shop_admin_view()
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("noop_shop_item:"))
async def cb_noop_shop_item(callback: CallbackQuery) -> None:
    await callback.answer()


# --- تغییر قیمت ---
@router.callback_query(F.data.startswith("shopadm_price:"))
async def cb_shopadm_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[1])
    await state.update_data(item_id=item_id)
    await callback.message.answer("قیمت جدید رو به تومن بفرست (فقط عدد):")
    await state.set_state(ShopAdminEditPrice.waiting_for_price)
    await callback.answer()


@router.message(ShopAdminEditPrice.waiting_for_price)
async def process_shopadm_price(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    data = await state.get_data()
    await state.clear()
    try:
        price = int((message.text or "").strip().replace(",", ""))
        assert price >= 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد صحیح و مثبت بفرست.")
        return

    async with get_session() as session:
        error = await update_shop_item_price(session, data["item_id"], price)
        if error:
            await message.answer(f"❌ {error}")
            return
        await session.commit()

    await message.answer("✅ قیمت بروزرسانی شد.")
    text, keyboard = await _build_shop_admin_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- تغییر نام/توضیحات ---
@router.callback_query(F.data.startswith("shopadm_text:"))
async def cb_shopadm_text_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[1])
    await state.update_data(item_id=item_id)
    await callback.message.answer(
        "نام و توضیحات جدید رو تو یک پیام، تو دو خط جدا بفرست:\n"
        "خط اول: نام آیتم\n"
        "خط دوم: توضیحات"
    )
    await state.set_state(ShopAdminEditText.waiting_for_text)
    await callback.answer()


@router.message(ShopAdminEditText.waiting_for_text)
async def process_shopadm_text(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    data = await state.get_data()
    await state.clear()

    lines = (message.text or "").split("\n", 1)
    if len(lines) < 2 or not lines[0].strip():
        await message.answer("فرمت درست نبود؛ باید نام تو خط اول و توضیحات تو خط دوم باشه.")
        return
    name_fa, description = lines[0].strip(), lines[1].strip()

    async with get_session() as session:
        error = await update_shop_item_text(session, data["item_id"], name_fa, description)
        if error:
            await message.answer(f"❌ {error}")
            return
        await session.commit()

    await message.answer("✅ متن آیتم بروزرسانی شد.")
    text, keyboard = await _build_shop_admin_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- فعال/غیرفعال و حذف ---
@router.callback_query(F.data.startswith("shopadm_toggle:"))
async def cb_shopadm_toggle(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        error = await toggle_shop_item_active(session, item_id)
        if error:
            await callback.answer(error, show_alert=True)
            return
        await session.commit()

    text, keyboard = await _build_shop_admin_view()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("✅ وضعیت عوض شد.")


@router.callback_query(F.data.startswith("shopadm_delete:"))
async def cb_shopadm_delete(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    item_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        error = await delete_shop_item(session, item_id)
        if error:
            await callback.answer(error, show_alert=True)
            return
        await session.commit()

    text, keyboard = await _build_shop_admin_view()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("🗑 حذف شد.")


# --- افزودن آیتم جدید ---
@router.callback_query(F.data == "shopadm_add")
async def cb_shopadm_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    await callback.message.answer(
        "اطلاعات آیتم جدید رو تو یک پیام، هر بخش تو یه خط جدا بفرست:\n\n"
        "۱- نام آیتم\n"
        "۲- آیکون (یک ایموجی)\n"
        "۳- توضیحات\n"
        "۴- قیمت به تومن\n"
        "۵- طلای جایزه (۰ اگه نمی‌خوای)\n"
        "۶- سکه‌ی جایزه (۰ اگه نمی‌خوای)\n\n"
        "مثال:\n"
        "بسته طلای متوسط\n💰\nمقدار زیادی طلا می‌گیری\n80000\n5000\n0"
    )
    await state.set_state(ShopAdminAdd.waiting_for_info)
    await callback.answer()


@router.message(ShopAdminAdd.waiting_for_info)
async def process_shopadm_add(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    await state.clear()

    lines = [line.strip() for line in (message.text or "").split("\n")]
    if len(lines) < 6 or not lines[0]:
        await message.answer("فرمت درست نبود؛ باید دقیقاً ۶ خط بفرستی. دوباره از منوی مدیریت امتحان کن.")
        return

    name_fa, icon, description = lines[0], lines[1], lines[2]
    try:
        price_toman = int(lines[3].replace(",", ""))
        reward_gold = int(lines[4].replace(",", ""))
        reward_coins = int(lines[5].replace(",", ""))
    except ValueError:
        await message.answer("قیمت/طلا/سکه باید عدد باشن. دوباره از منوی مدیریت امتحان کن.")
        return

    async with get_session() as session:
        await create_shop_item(session, name_fa, icon, description, price_toman, reward_gold, reward_coins)
        await session.commit()

    await message.answer(f"✅ آیتم «{name_fa}» اضافه شد.")
    text, keyboard = await _build_shop_admin_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- تنظیم شماره کارت ---
@router.callback_query(F.data == "shopadm_setcard")
async def cb_shopadm_setcard_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    await callback.message.answer(
        "شماره کارت و نام صاحب حساب رو تو یک پیام، هرکدوم تو یه خط جدا بفرست:\n\n"
        "مثال:\n6037-9911-2233-4455\nعلی رضایی"
    )
    await state.set_state(ShopAdminSetCard.waiting_for_info)
    await callback.answer()


@router.message(ShopAdminSetCard.waiting_for_info)
async def process_shopadm_setcard(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    await state.clear()

    lines = [line.strip() for line in (message.text or "").split("\n") if line.strip()]
    if len(lines) < 2:
        await message.answer("فرمت درست نبود؛ شماره کارت تو خط اول، نام صاحب حساب تو خط دوم.")
        return

    card_number, card_holder = lines[0], lines[1]
    async with get_session() as session:
        await set_payment_card_number(session, card_number)
        await set_payment_card_holder(session, card_holder)
        await session.commit()

    await message.answer("✅ اطلاعات کارت بروزرسانی شد.")
    text, keyboard = await _build_shop_admin_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
