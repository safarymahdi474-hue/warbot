from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import current_room, user_scope
from bot.database.models import User, UserBuilding
from bot.utils.global_events import get_active_events, get_oil_production_multiplier
from bot.utils.resources import collect_production, finish_ready_upgrades, recalculate_storage_caps

router = Router(name="resources")


def bar(current: int, maximum: int, length: int = 10) -> str:
    if maximum <= 0:
        maximum = 1
    filled = round(length * min(current, maximum) / maximum)
    return "🟦" * filled + "⬜️" * (length - filled)


def resources_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_resources")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


def build_resources_text(user: User, gained: dict[str, int], active_event_labels: list[str]) -> str:
    lines = ["📦 <b>منابع تو</b>\n"]
    lines.append(f"💰 طلا: {user.gold}")
    lines.append(f"🌾 غذا: {user.food}/{user.max_food}\n{bar(user.food, user.max_food)}")
    lines.append(f"⛏️ آهن: {user.iron}/{user.max_iron}\n{bar(user.iron, user.max_iron)}")
    lines.append(f"🛢️ نفت: {user.oil}/{user.max_oil}\n{bar(user.oil, user.max_oil)}")

    if any(gained.values()):
        gained_parts = []
        if gained.get("food"):
            gained_parts.append(f"🌾+{gained['food']}")
        if gained.get("iron"):
            gained_parts.append(f"⛏️+{gained['iron']}")
        if gained.get("oil"):
            gained_parts.append(f"🛢️+{gained['oil']}")
        lines.append("\n✨ از آخرین بازدید: " + " | ".join(gained_parts))

    if active_event_labels:
        lines.append("\n" + " | ".join(active_event_labels))

    return "\n\n".join(lines)


async def _get_resources_text(telegram_id: int) -> str:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

        result = await session.execute(
            select(UserBuilding)
            .options(selectinload(UserBuilding.building_type))
            .where(UserBuilding.user_id == user.id)
        )
        user_buildings = list(result.scalars().all())

        oil_multiplier = await get_oil_production_multiplier(session, current_room())
        active_events = await get_active_events(session, current_room())
        event_labels = []
        if any(e.event_type == "sandstorm" for e in active_events):
            event_labels.append("🌪️ توفان شن فعاله (تولید نفت کمتره)")
        if any(e.event_type == "war_season" for e in active_events):
            event_labels.append("⚔️ فصل جنگه (XP نبرد دوبرابره)")

        finish_ready_upgrades(user_buildings)
        recalculate_storage_caps(user, user_buildings)
        gained = collect_production(user, user_buildings, oil_multiplier)
        await session.commit()

        return build_resources_text(user, gained, event_labels)


@router.message(Command("resources"))
async def cmd_resources(message: Message) -> None:
    text = await _get_resources_text(message.from_user.id)
    await message.answer(text, reply_markup=resources_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "show_resources")
async def cb_resources(callback: CallbackQuery) -> None:
    text = await _get_resources_text(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=resources_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=resources_keyboard(), parse_mode="HTML")
    await callback.answer()
