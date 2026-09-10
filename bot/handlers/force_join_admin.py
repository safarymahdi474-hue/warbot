from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.database.db import get_session
from bot.utils.force_join import add_channel, list_channels, remove_channel

router = Router(name="force_join_admin")


class ForceJoinAdd(StatesGroup):
    waiting_for_info = State()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


def panel_keyboard(channels) -> InlineKeyboardMarkup:
    rows = []
    for c in channels:
        expiry = "دائمی" if c.expires_at is None else "موقت"
        rows.append(
            [
                InlineKeyboardButton(text=f"📢 {c.title} ({expiry})", callback_data="noop_fj"),
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"fjadm_del:{c.id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ افزودن کانال جدید", callback_data="fjadm_add")])
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_fj_admin")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_panel_text(channels) -> str:
    lines = ["📢 <b>مدیریت عضویت اجباری</b>\n"]
    if not channels:
        lines.append("هیچ کانال عضویت اجباری‌ای فعال نیست.")
    else:
        from datetime import datetime

        now = datetime.utcnow()
        for c in channels:
            if c.expires_at is None:
                expiry = "دائمی"
            else:
                remaining = c.expires_at - now
                minutes_left = max(0, int(remaining.total_seconds() // 60))
                expiry = f"{minutes_left // 60} ساعت و {minutes_left % 60} دقیقه‌ی دیگه حذف میشه"
            lines.append(f"• <b>{c.title}</b> ({c.chat_id}) — {expiry}")
    return "\n".join(lines)


async def _build_view() -> tuple[str, InlineKeyboardMarkup]:
    async with get_session() as session:
        channels = await list_channels(session)
    return build_panel_text(channels), panel_keyboard(channels)


@router.message(Command("forcejoinadmin"))
async def cmd_force_join_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    text, keyboard = await _build_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_fj_admin")
async def cb_force_join_admin(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return
    text, keyboard = await _build_view()
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop_fj")
async def cb_noop_fj(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("fjadm_del:"))
async def cb_force_join_delete(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return

    channel_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        error = await remove_channel(session, channel_id)
        if error:
            await callback.answer(error, show_alert=True)
            return
        await session.commit()

    text, keyboard = await _build_view()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("🗑 حذف شد.")


@router.callback_query(F.data == "fjadm_add")
async def cb_force_join_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return

    await callback.message.answer(
        "اطلاعات کانال جدید رو تو یک پیام، هر بخش تو یه خط جدا بفرست:\n\n"
        "۱- آیدی کانال (مثلاً @mychannel یا -1001234567890)\n"
        "۲- لینک دعوت یا یوزرنیم (هرجور بنویسی خودش درست میشه)\n"
        "۳- اسمی که تو دکمه نشون داده بشه\n"
        "۴- ساعت انقضا (۰ برای دائمی)\n\n"
        "مثال:\n@mychannel\n@mychannel\nکانال اصلی ما\n0\n\n"
        "⚠️ حتماً ربات رو تو اون کانال ادمین کن، وگرنه چک عضویت کار نمی‌کنه."
    )
    await state.set_state(ForceJoinAdd.waiting_for_info)
    await callback.answer()


@router.message(ForceJoinAdd.waiting_for_info)
async def process_force_join_add(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()

    lines = [line.strip() for line in (message.text or "").split("\n") if line.strip()]
    if len(lines) < 4:
        await message.answer("فرمت درست نبود؛ باید دقیقاً ۴ خط بفرستی. دوباره از پنل امتحان کن.")
        return

    chat_id, invite_raw, title, hours_raw = lines[0], lines[1], lines[2], lines[3]
    try:
        hours = int(hours_raw)
    except ValueError:
        await message.answer("ساعت انقضا باید عدد باشه (۰ برای دائمی).")
        return

    async with get_session() as session:
        result = await add_channel(session, message.from_user.id, chat_id, invite_raw, title, hours)
        if isinstance(result, str):
            await message.answer(f"❌ {result}")
            return
        await session.commit()

    expiry_note = "دائمیه" if not hours else f"تا {hours} ساعت دیگه فعاله"
    await message.answer(f"✅ کانال «{title}» اضافه شد ({expiry_note}).")

    text, keyboard = await _build_view()
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
