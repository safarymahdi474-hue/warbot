from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import current_room, user_scope
from bot.database.models import BuildingType, User, UserBuilding, UserResearch
from bot.keyboards.menus import buildings_keyboard
from bot.utils.global_events import get_oil_production_multiplier
from bot.utils.military import get_bonus_percent
from bot.utils.missions import record_progress
from bot.utils.resources import (
    collect_production,
    finish_ready_upgrades,
    recalculate_storage_caps,
    start_upgrade,
    upgrade_duration,
)
from bot.utils.room_settings import deliver_sensitive_content

NOT_REGISTERED_MSG = "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

router = Router(name="buildings")


async def _get_build_time_bonus(session, user_id: int) -> float:
    result = await session.execute(
        select(UserResearch)
        .options(selectinload(UserResearch.research_type))
        .where(UserResearch.user_id == user_id)
    )
    researches = list(result.scalars().all())
    return get_bonus_percent(researches, "build_time_reduction_percent")


async def _load_user_and_buildings(session, telegram_id: int):
    result = await session.execute(select(User).where(*user_scope(telegram_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None, []

    result = await session.execute(
        select(UserBuilding)
        .options(selectinload(UserBuilding.building_type))
        .where(UserBuilding.user_id == user.id)
    )
    user_buildings = list(result.scalars().all())
    return user, user_buildings


async def _sync(session, user: User, user_buildings: list[UserBuilding]) -> None:
    """ارتقاهای تموم‌شده رو اعمال، سقف انبار رو حساب و تولید منابع رو جمع می‌کنه."""
    oil_multiplier = await get_oil_production_multiplier(session, current_room())
    finish_ready_upgrades(user_buildings)
    recalculate_storage_caps(user, user_buildings)
    collect_production(user, user_buildings, oil_multiplier)
    await session.commit()


def build_buildings_text(user_buildings: list[UserBuilding]) -> str:
    lines = ["🏗️ <b>ساختمان‌های تو</b>\n"]
    for ub in sorted(user_buildings, key=lambda x: x.building_type.id):
        bt = ub.building_type
        if ub.level == 0:
            status = "هنوز ساخته نشده"
        elif bt.produces:
            status = f"لول {ub.level} — تولید: {bt.base_production_per_hour * ub.level}/ساعت"
        else:
            status = f"لول {ub.level} — سقف ذخیره +{bt.storage_bonus_per_level * ub.level}"

        if ub.upgrade_finish_at is not None:
            status += " (⏳ در حال ساخت)"

        lines.append(f"{bt.icon} <b>{bt.name_fa}</b>: {status}")
    return "\n".join(lines)


async def _show_buildings(user_id_telegram: int) -> tuple[str, "InlineKeyboardMarkup | None"]:
    async with get_session() as session:
        user, user_buildings = await _load_user_and_buildings(session, user_id_telegram)
        if user is None:
            return NOT_REGISTERED_MSG, None
        await _sync(session, user, user_buildings)
        text = build_buildings_text(user_buildings)
        keyboard = buildings_keyboard(user_buildings)
        return text, keyboard


@router.message(Command("buildings"))
async def cmd_buildings(message: Message) -> None:
    text, keyboard = await _show_buildings(message.from_user.id)
    if text == NOT_REGISTERED_MSG:
        await message.answer(text)
        return

    sent_privately, group_note = await deliver_sensitive_content(
        message.bot, current_room(), message.chat.type, message.from_user.id, text, keyboard
    )
    if sent_privately:
        await message.answer(group_note)
        return
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_buildings")
async def cb_show_buildings(callback: CallbackQuery) -> None:
    text, keyboard = await _show_buildings(callback.from_user.id)
    if text == NOT_REGISTERED_MSG:
        await callback.answer(text, show_alert=True)
        return

    sent_privately, group_note = await deliver_sensitive_content(
        callback.bot, current_room(), callback.message.chat.type, callback.from_user.id, text, keyboard
    )
    if sent_privately:
        await callback.answer(group_note, show_alert=True)
        return

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("build_upgrade:"))
async def cb_upgrade_building(callback: CallbackQuery) -> None:
    building_type_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        user, user_buildings = await _load_user_and_buildings(session, callback.from_user.id)
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        await _sync(session, user, user_buildings)

        target = next((ub for ub in user_buildings if ub.building_type_id == building_type_id), None)
        if target is None:
            await callback.answer("ساختمان پیدا نشد.", show_alert=True)
            return

        time_bonus = await _get_build_time_bonus(session, user.id)
        error = start_upgrade(user, target, target.building_type, time_bonus)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await record_progress(session, user, "upgrade_building", 1)
        user.buildings_upgraded_total += 1
        await session.commit()

        # start_upgrade فقط upgrade_finish_at رو ست می‌کنه، level هنوز عوض نشده
        duration = upgrade_duration(target.building_type, target.level, time_bonus)
        await callback.answer(
            f"✅ شروع شد! تا {int(duration.total_seconds() // 60)} دقیقه دیگه آماده‌ست.",
            show_alert=True,
        )

    text, keyboard = await _show_buildings(callback.from_user.id)
    sent_privately, group_note = await deliver_sensitive_content(
        callback.bot, current_room(), callback.message.chat.type, callback.from_user.id, text, keyboard
    )
    if sent_privately:
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.in_({"building_busy", "building_max"}))
async def cb_building_noop(callback: CallbackQuery) -> None:
    if callback.data == "building_busy":
        await callback.answer("این ساختمان الان در حال ساخت/ارتقاست، صبر کن.", show_alert=True)
    else:
        await callback.answer("این ساختمان به حداکثر سطح رسیده.", show_alert=True)
