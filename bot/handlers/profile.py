from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import current_room, user_scope
from bot.database.models import User
from bot.utils.achievements import check_referral_milestone
from bot.utils.admin import ensure_admin_flag
from bot.utils.progression import regen_energy, xp_required_for_level
from bot.utils.referral import count_referrals, get_referred_users
from bot.utils.room_settings import deliver_sensitive_content

router = Router(name="profile")


def make_bar(current: int, maximum: int, length: int = 10) -> str:
    if maximum <= 0:
        maximum = 1
    filled = round(length * min(current, maximum) / maximum)
    return "🟩" * filled + "⬜️" * (length - filled)


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 رفرال‌های من", callback_data="show_referrals")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


def build_profile_text(user: User) -> str:
    xp_needed = xp_required_for_level(user.level)
    country_name = f"{user.country.flag_emoji} {user.country.name_fa}" if user.country else "بدون کشور"
    room_line = (
        f"🏠 فضای بازی: {user.room.title}\n" if user.room_id is not None else "🏠 فضای بازی: پروفایل اصلی\n"
    )
    return (
        room_line +
        f"👤 <b>{user.nickname}</b>\n"
        f"🌍 کشور: {country_name}\n"
        f"⭐ سطح: {user.level}\n\n"
        f"XP: {user.xp}/{xp_needed}\n{make_bar(user.xp, xp_needed)}\n\n"
        f"❤️ جان: {user.hp}/{user.max_hp}\n{make_bar(user.hp, user.max_hp)}\n\n"
        f"⚡ انرژی: {user.energy}/{user.max_energy}\n{make_bar(user.energy, user.max_energy)}\n\n"
        f"💰 طلا: {user.gold}\n"
        f"🪙 سکه: {user.coins}\n\n"
        f"🔗 کد معرف تو: <code>{user.referral_code}</code>"
    )


async def _get_user_with_regen(telegram_id: int) -> User | None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        regen_energy(user)
        await check_referral_milestone(session, user)
        await ensure_admin_flag(session, user)
        await session.commit()
        await session.refresh(user, attribute_names=["country", "room"])
        return user


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    user = await _get_user_with_regen(message.from_user.id)
    if user is None:
        await message.answer("هنوز ثبت‌نام نکردی! دستور /start رو بزن.")
        return

    text = build_profile_text(user)
    sent_privately, group_note = await deliver_sensitive_content(
        message.bot, current_room(), message.chat.type, message.from_user.id, text, profile_keyboard()
    )
    if sent_privately:
        await message.answer(group_note)
        return
    await message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "show_profile")
async def cb_profile(callback: CallbackQuery) -> None:
    user = await _get_user_with_regen(callback.from_user.id)
    if user is None:
        await callback.answer("هنوز ثبت‌نام نکردی! /start رو بزن.", show_alert=True)
        return

    text = build_profile_text(user)
    sent_privately, group_note = await deliver_sensitive_content(
        callback.bot, current_room(), callback.message.chat.type, callback.from_user.id, text, profile_keyboard()
    )
    if sent_privately:
        await callback.answer(group_note, show_alert=True)
        return
    await callback.message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# رفرال‌های من
# ---------------------------------------------------------------------------

def referrals_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_referrals")],
            [InlineKeyboardButton(text="🔙 بازگشت به پروفایل", callback_data="show_profile")],
        ]
    )


async def _build_referrals_text(telegram_id: int, bot_username: str | None) -> str:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

        total = await count_referrals(session, user.id)
        referred_users = await get_referred_users(session, user.id)

    lines = ["🔗 <b>سیستم رفرال</b>\n"]
    lines.append(f"کد معرف تو: <code>{user.referral_code}</code>")
    if bot_username:
        lines.append(f"لینک دعوت: <code>https://t.me/{bot_username}?start={user.referral_code}</code>")
    lines.append(f"\n👥 تعداد کسایی که با کد تو ثبت‌نام کردن: <b>{total}</b>")
    lines.append(
        "🎁 هروقت یکی از زیرمجموعه‌هات برای اولین‌بار به سطح مشخصی برسه، "
        "یه‌بار پاداش طلا می‌گیری (برای هر نفر جدا)."
    )

    if referred_users:
        lines.append("\n📋 <b>آخرین رفرال‌ها:</b>")
        for u in referred_users:
            milestone_icon = "✅" if u.referral_milestone_paid else "⏳"
            lines.append(f"  {milestone_icon} {u.nickname} — سطح {u.level}")
    else:
        lines.append("\nهنوز کسی با کد تو ثبت‌نام نکرده. کدت رو با دوستات به اشتراک بذار!")

    return "\n".join(lines)


@router.callback_query(F.data == "show_referrals")
async def cb_show_referrals(callback: CallbackQuery) -> None:
    bot_username = None
    try:
        me = await callback.bot.get_me()
        bot_username = me.username
    except Exception:
        pass

    text = await _build_referrals_text(callback.from_user.id, bot_username)
    try:
        await callback.message.edit_text(text, reply_markup=referrals_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=referrals_keyboard(), parse_mode="HTML")
    await callback.answer()
