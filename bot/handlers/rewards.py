from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User
from bot.utils.rewards import (
    can_claim_daily_chest,
    can_claim_online_gift,
    can_spin_wheel,
    claim_daily_chest,
    claim_online_gift,
    spin_wheel,
    time_until_daily_chest,
    time_until_online_gift,
    time_until_wheel_spin,
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
            [InlineKeyboardButton(text="🎁 صندوق روزانه", callback_data="open_daily_chest")],
            [InlineKeyboardButton(text="🕊️ هدیه آنلاین", callback_data="claim_online_gift")],
            [InlineKeyboardButton(text="🎡 گردونه شانس", callback_data="spin_wheel")],
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
# صندوق روزانه
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "open_daily_chest")
async def cb_open_daily_chest(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        if not can_claim_daily_chest(user):
            remaining = time_until_daily_chest(user)
            await callback.answer(f"صندوق امروز رو باز کردی! {fmt_remaining(remaining)} صبر کن.", show_alert=True)
            return

        reward = claim_daily_chest(user)
        await session.commit()

    msg = f"🎁 صندوق باز شد!\n💰 +{reward['gold']} طلا\n⭐ +{reward['xp']} XP"
    if reward["leveled_up"]:
        msg += f"\n\n🎊 لول‌آپ کردی! سطح جدید: {reward['leveled_up'][-1]}"
    await callback.answer(msg, show_alert=True)


# ---------------------------------------------------------------------------
# هدیه آنلاین
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

    await callback.answer(f"🕊️ هدیه گرفتی!\n💰 +{reward['gold']} طلا\n⚡ +{reward['energy']} انرژی", show_alert=True)


# ---------------------------------------------------------------------------
# گردونه شانس
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "spin_wheel")
async def cb_spin_wheel(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        if not can_spin_wheel(user):
            remaining = time_until_wheel_spin(user)
            await callback.answer(f"گردونه امروز رو چرخوندی! {fmt_remaining(remaining)} صبر کن.", show_alert=True)
            return

        prize = spin_wheel(user)
        await session.commit()

    await callback.answer(f"🎡 گردونه چرخید...\n\n{prize['label']}", show_alert=True)
