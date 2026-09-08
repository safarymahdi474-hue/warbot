from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User
from bot.utils.rewards import (
    can_claim_online_gift,
    claim_online_gift,
    time_until_online_gift,
)

router = Router(name="rewards")


def fmt_remaining(td) -> str:
    if td is None:
        return ""
    total_minutes = max(1, int(td.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours} ساعت و {minutes} دقیقه دیگه"
    return f"{minutes} دقیقه دیگه"


def rewards_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕊️ هدیه آنلاین", callback_data="claim_online_gift")],
            [InlineKeyboardButton(text="🎯 ماموریت‌ها", callback_data="show_missions")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


@router.message(Command("rewards"))
async def cmd_rewards(message: Message) -> None:
    await message.answer("🎁 مرکز جوایز:", reply_markup=rewards_menu_keyboard())


@router.callback_query(F.data == "show_rewards_menu")
async def cb_rewards_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🎁 مرکز جوایز:", reply_markup=rewards_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# هدیه آنلاین (با بونوس روزهای پشت‌سرهم)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "claim_online_gift")
async def cb_claim_online_gift(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        if not can_claim_online_gift(user):
            remaining = time_until_online_gift(user)
            await callback.answer(f"هنوز وقتش نشده! {fmt_remaining(remaining)} صبر کن.", show_alert=True)
            return

        reward = claim_online_gift(user)
        await session.commit()

    msg = f"🕊️ هدیه گرفتی!\n💰 +{reward['gold']} طلا\n⚡ +{reward['energy']} انرژی"
    if reward["streak"] > 1:
        msg += (
            f"\n\n🔥 {reward['streak']} روز پشت‌سرهمه!"
            f"\n(پایه: {reward['base_gold']} + بونوس پشت‌سرهم: {reward['streak_bonus']})"
        )
    await callback.answer(msg, show_alert=True)
