from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.config import settings
from bot.database.db import get_session
from bot.database.models import User
from bot.utils.context import room_condition, user_scope

router = Router(name="territory")


def territory_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 برترین‌های خاک", callback_data="territory_leaderboard")],
            [InlineKeyboardButton(text="🗡️ حمله برای تصرف خاک", callback_data="show_attack_menu")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


def build_territory_text(user: User) -> str:
    lines = [
        "🗺️ <b>خاک‌های من</b>\n",
        f"📍 خاک فعلی: <b>{user.territory_count}</b> واحد",
        f"\nℹ️ با بردن نبرد PvP، حدود {settings.TERRITORY_CAPTURE_PERCENT}٪ از خاک حریف رو تصرف می‌کنی.",
        f"اگه ببازی، ممکنه حریف بخشی از خاک تو رو تصرف کنه (حداقل {settings.MIN_TERRITORY_KEPT} واحد همیشه برات می‌مونه).",
    ]
    return "\n".join(lines)


async def _territory_view(telegram_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None
        return build_territory_text(user), territory_keyboard()


@router.message(Command("territory"))
async def cmd_territory(message: Message) -> None:
    text, keyboard = await _territory_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_territory")
async def cb_territory(callback: CallbackQuery) -> None:
    text, keyboard = await _territory_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "territory_leaderboard")
async def cb_territory_leaderboard(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(User)
            .where(room_condition(User.room_id))
            .order_by(User.territory_count.desc())
            .limit(10)
        )
        users = list(result.scalars().all())

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>برترین‌های خاک</b>\n"]
    if not users:
        lines.append("هنوز کسی ثبت‌نام نکرده.")
    for i, u in enumerate(users):
        rank_icon = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{rank_icon} <b>{u.nickname}</b> — {u.territory_count} واحد خاک")

    try:
        await callback.message.edit_text(
            "\n".join(lines), reply_markup=territory_keyboard(), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer("\n".join(lines), reply_markup=territory_keyboard(), parse_mode="HTML")
    await callback.answer()
