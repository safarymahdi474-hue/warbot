from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User, UserInventory
from bot.utils.items import get_inventory, use_item

router = Router(name="inventory")


def inventory_keyboard(items: list[UserInventory]) -> InlineKeyboardMarkup:
    rows = []
    for ui in items:
        it = ui.item_type
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{it.icon} استفاده از {it.name_fa} (×{ui.quantity})",
                    callback_data=f"use_item:{ui.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🛒 فروش در بازار", callback_data="sell_from_inventory")])
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_inventory")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_inventory_text(items: list[UserInventory]) -> str:
    if not items:
        return "🎒 <b>اینونتوری تو</b>\n\nخالیه! از بازار یا گردونه شانس آیتم بگیر."
    lines = ["🎒 <b>اینونتوری تو</b>\n"]
    for ui in items:
        it = ui.item_type
        lines.append(f"{it.icon} <b>{it.name_fa}</b> ×{ui.quantity}\n   {it.description}")
    return "\n\n".join(lines)


async def _inventory_view(telegram_id: int):
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None
        items = await get_inventory(session, user.id)
        return build_inventory_text(items), inventory_keyboard(items)


@router.message(Command("inventory"))
async def cmd_inventory(message: Message) -> None:
    text, keyboard = await _inventory_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_inventory")
async def cb_inventory(callback: CallbackQuery) -> None:
    text, keyboard = await _inventory_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("use_item:"))
async def cb_use_item(callback: CallbackQuery) -> None:
    inventory_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        result = await session.execute(
            select(UserInventory)
            .options(selectinload(UserInventory.item_type))
            .where(UserInventory.id == inventory_id, UserInventory.user_id == user.id)
        )
        ui = result.scalar_one_or_none()
        if ui is None:
            await callback.answer("این آیتم پیدا نشد.", show_alert=True)
            return

        success_msg, error_msg = await use_item(session, user, ui)
        if error_msg:
            await callback.answer(error_msg, show_alert=True)
            return

        await session.commit()
        await callback.answer(success_msg, show_alert=True)

    text, keyboard = await _inventory_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
