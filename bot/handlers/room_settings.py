from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.db import get_session
from bot.utils.room_settings import get_room, is_group_admin

router = Router(name="room_settings")


def room_settings_keyboard(privacy_mode: bool) -> InlineKeyboardMarkup:
    label = "🔒 حالت خصوصی: روشن (بزن خاموش کن)" if privacy_mode else "🔓 حالت خصوصی: خاموش (بزن روشن کن)"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="toggle_room_privacy")]]
    )


def room_settings_text(title: str, privacy_mode: bool) -> str:
    status = "🔒 روشنه" if privacy_mode else "🔓 خاموشه"
    return (
        f"⚙️ <b>تنظیمات گروه «{title}»</b>\n\n"
        f"حالت خصوصی: {status}\n\n"
        "وقتی حالت خصوصی روشن باشه، جواب دستورهای حساس (پروفایل، منابع، ارتش، "
        "ساختمان‌ها) به‌جای اینکه تو گروه پابلیک بشه، پیوی خود شخص فرستاده میشه "
        "تا منابع و تعداد سربازها لو نره.\n\n"
        "فقط ادمین‌ها/سازنده‌ی خود این گروه تلگرامی می‌تونن این تنظیم رو عوض کنن."
    )


async def _require_group_and_admin(message_or_callback, is_callback: bool) -> tuple[bool, str | None]:
    chat = message_or_callback.message.chat if is_callback else message_or_callback.chat
    user_id = message_or_callback.from_user.id

    if chat.type == "private":
        return False, "این دستور فقط داخل یه گروه معنی داره."

    bot = message_or_callback.bot
    if not await is_group_admin(bot, chat.id, user_id):
        return False, "فقط ادمین‌ها یا سازنده‌ی این گروه می‌تونن تنظیماتش رو عوض کنن."

    return True, None


@router.message(Command("roomsettings"))
async def cmd_room_settings(message: Message) -> None:
    ok, error = await _require_group_and_admin(message, is_callback=False)
    if not ok:
        await message.answer(f"❌ {error}")
        return

    async with get_session() as session:
        from bot.utils.context import current_room  # جلوگیری از import چرخه‌ای احتمالی

        room = await get_room(session, current_room())
        privacy_mode = bool(room and room.privacy_mode)
        title = room.title if room else message.chat.title or "گروه"

    await message.answer(
        room_settings_text(title, privacy_mode),
        reply_markup=room_settings_keyboard(privacy_mode),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "toggle_room_privacy")
async def cb_toggle_room_privacy(callback: CallbackQuery) -> None:
    ok, error = await _require_group_and_admin(callback, is_callback=True)
    if not ok:
        await callback.answer(error, show_alert=True)
        return

    async with get_session() as session:
        from bot.utils.context import current_room

        room = await get_room(session, current_room())
        if room is None:
            await callback.answer("این گروه هنوز تو دیتابیس ثبت نشده (یه دستور دیگه رو اول امتحان کن).", show_alert=True)
            return

        room.privacy_mode = not room.privacy_mode
        new_state = room.privacy_mode
        title = room.title
        await session.commit()

    try:
        await callback.message.edit_text(
            room_settings_text(title, new_state),
            reply_markup=room_settings_keyboard(new_state),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            room_settings_text(title, new_state),
            reply_markup=room_settings_keyboard(new_state),
            parse_mode="HTML",
        )
    await callback.answer("✅ تنظیم عوض شد.")
