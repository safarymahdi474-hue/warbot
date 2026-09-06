from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import MissionType, User, UserMissionProgress
from bot.utils.missions import claim_mission_reward, load_missions_with_progress

router = Router(name="missions")


def build_mission_line(mt: MissionType, progress: UserMissionProgress) -> str:
    bar_len = 10
    filled = round(bar_len * min(progress.progress, mt.target_amount) / mt.target_amount)
    bar = "🟨" * filled + "⬜️" * (bar_len - filled)

    reward_parts = []
    if mt.reward_gold:
        reward_parts.append(f"💰{mt.reward_gold}")
    if mt.reward_iron:
        reward_parts.append(f"⛏️{mt.reward_iron}")
    if mt.reward_oil:
        reward_parts.append(f"🛢️{mt.reward_oil}")
    if mt.reward_food:
        reward_parts.append(f"🌾{mt.reward_food}")
    if mt.reward_xp:
        reward_parts.append(f"⭐{mt.reward_xp}")
    reward_txt = " ".join(reward_parts)

    status = "✅ دریافت‌شده" if progress.claimed else (
        "🎁 آماده‌ی دریافت" if progress.progress >= mt.target_amount else f"{progress.progress}/{mt.target_amount}"
    )

    return f"{mt.icon} <b>{mt.name_fa}</b>\n{bar}  {status}\n🎁 پاداش: {reward_txt}"


def missions_keyboard(pairs: list[tuple[MissionType, UserMissionProgress]]) -> InlineKeyboardMarkup:
    rows = []
    for mt, progress in pairs:
        if not progress.claimed and progress.progress >= mt.target_amount:
            rows.append(
                [InlineKeyboardButton(text=f"🎁 دریافت پاداش «{mt.name_fa}»", callback_data=f"claim_mission:{mt.id}")]
            )
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_missions")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _missions_view(telegram_id: int):
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None

        pairs = await load_missions_with_progress(session, user)

    daily = [p for p in pairs if p[0].scope == "daily"]
    weekly = [p for p in pairs if p[0].scope == "weekly"]

    lines = ["🎯 <b>ماموریت‌های روزانه</b>\n"]
    lines += [build_mission_line(mt, pr) for mt, pr in daily]
    lines.append("\n📅 <b>ماموریت‌های هفتگی</b>\n")
    lines += [build_mission_line(mt, pr) for mt, pr in weekly]

    return "\n\n".join(lines), missions_keyboard(pairs)


@router.message(Command("missions"))
async def cmd_missions(message: Message) -> None:
    text, keyboard = await _missions_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_missions")
async def cb_missions(callback: CallbackQuery) -> None:
    text, keyboard = await _missions_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("claim_mission:"))
async def cb_claim_mission(callback: CallbackQuery) -> None:
    mission_type_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        mission_type, error = await claim_mission_reward(session, user, mission_type_id)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer(f"✅ پاداش «{mission_type.name_fa}» دریافت شد!", show_alert=True)

    text, keyboard = await _missions_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
