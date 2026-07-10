from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User

router = Router(name="settings")


def settings_keyboard(user: User) -> InlineKeyboardMarkup:
    notif_label = "🔕 خاموش کردن اعلان‌ها" if user.notifications_enabled else "🔔 روشن کردن اعلان‌ها"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=notif_label, callback_data="toggle_notifications")],
            [InlineKeyboardButton(text="🆘 پشتیبانی", callback_data="show_support")],
        ]
    )


def build_settings_text(user: User) -> str:
    status = "روشن ✅" if user.notifications_enabled else "خاموش ❌"
    return (
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"👤 نیک‌نیم: {user.nickname}\n"
        f"🔔 اعلان‌ها (پیام خصوصی، چت اتحاد): {status}\n"
        f"🔗 کد معرف: <code>{user.referral_code}</code>"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی! دستور /start رو بزن.")
            return
        text, keyboard = build_settings_text(user), settings_keyboard(user)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_settings")
async def cb_show_settings(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return
        text, keyboard = build_settings_text(user), settings_keyboard(user)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "toggle_notifications")
async def cb_toggle_notifications(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        user.notifications_enabled = not user.notifications_enabled
        await session.commit()
        text, keyboard = build_settings_text(user), settings_keyboard(user)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer("✅ تنظیمات بروزرسانی شد.")
