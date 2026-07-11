from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.db import get_session
from bot.utils.context import room_condition, user_scope
from bot.database.models import User
from bot.utils.achievements import claim_achievement, load_achievements_with_progress

router = Router(name="achievements")


def build_achievement_line(at, progress, is_ready) -> str:
    if progress.claimed:
        status = "✅ گرفته‌شده"
    elif is_ready:
        status = "🎁 آماده‌ی دریافت"
    else:
        status = "🔒 هنوز کامل نشده"
    reward_parts = []
    if at.reward_gold:
        reward_parts.append(f"💰{at.reward_gold}")
    if at.reward_xp:
        reward_parts.append(f"⭐{at.reward_xp}")
    return f"{at.icon} <b>{at.name_fa}</b>\n{at.description}\n{status} — پاداش: {' '.join(reward_parts)}"


def achievements_keyboard(pairs) -> InlineKeyboardMarkup:
    rows = []
    for at, progress, is_ready in pairs:
        if is_ready and not progress.claimed:
            rows.append(
                [InlineKeyboardButton(text=f"🎁 دریافت «{at.name_fa}»", callback_data=f"claim_achievement:{at.id}")]
            )
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_achievements")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _achievements_view(telegram_id: int):
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None
        pairs = await load_achievements_with_progress(session, user)

    lines = ["🏅 <b>دستاوردها</b>\n"]
    lines += [build_achievement_line(at, pr, ready) for at, pr, ready in pairs]
    return "\n\n".join(lines), achievements_keyboard(pairs)


@router.message(Command("achievements"))
async def cmd_achievements(message: Message) -> None:
    text, keyboard = await _achievements_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_achievements")
async def cb_achievements(callback: CallbackQuery) -> None:
    text, keyboard = await _achievements_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("claim_achievement:"))
async def cb_claim_achievement(callback: CallbackQuery) -> None:
    achievement_type_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        achievement_type, error = await claim_achievement(session, user, achievement_type_id)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer(f"✅ دستاورد «{achievement_type.name_fa}» گرفته شد!", show_alert=True)

    text, keyboard = await _achievements_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# ---------------------------------------------------------------------------
# جدول رتبه‌بندی
# ---------------------------------------------------------------------------

def leaderboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_leaderboard")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message) -> None:
    text = await _leaderboard_text()
    await message.answer(text, reply_markup=leaderboard_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "show_leaderboard")
async def cb_leaderboard(callback: CallbackQuery) -> None:
    text = await _leaderboard_text()
    await callback.message.edit_text(
        text,
        reply_markup=leaderboard_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


async def _leaderboard_text() -> str:
    async with get_session() as session:
        result = await session.execute(
            select(User)
            .options(selectinload(User.country))
            .where(room_condition(User.room_id))
            .order_by(User.level.desc(), User.xp.desc())
            .limit(settings.LEADERBOARD_SIZE)
        )
        users = list(result.scalars().all())

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>جدول رتبه‌بندی برتر</b>\n"]
    for i, u in enumerate(users):
        rank_icon = medals[i] if i < 3 else f"{i + 1}."
        country_flag = u.country.flag_emoji if u.country else "🏳️"
        lines.append(f"{rank_icon} {country_flag} <b>{u.nickname}</b> — لول {u.level}")
    if not users:
        lines.append("هنوز کسی ثبت‌نام نکرده.")
    return "\n".join(lines)
