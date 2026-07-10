from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User
from bot.utils.achievements import check_referral_milestone
from bot.utils.admin import ensure_admin_flag
from bot.utils.progression import regen_energy, xp_required_for_level

router = Router(name="profile")


def make_bar(current: int, maximum: int, length: int = 10) -> str:
    if maximum <= 0:
        maximum = 1
    filled = round(length * min(current, maximum) / maximum)
    return "🟩" * filled + "⬜️" * (length - filled)


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
    await message.answer(build_profile_text(user), parse_mode="HTML")


@router.callback_query(F.data == "show_profile")
async def cb_profile(callback: CallbackQuery) -> None:
    user = await _get_user_with_regen(callback.from_user.id)
    if user is None:
        await callback.answer("هنوز ثبت‌نام نکردی! /start رو بزن.", show_alert=True)
        return
    await callback.message.answer(build_profile_text(user), parse_mode="HTML")
    await callback.answer()
