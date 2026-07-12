from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.db import get_session
from bot.utils.context import current_room, room_condition, user_scope
from bot.database.models import BannedTelegramUser, BattleReport, User
from bot.utils.alliance import add_war_score, get_active_war_between
from bot.utils.battle import BOT_DIFFICULTIES, can_attack, resolve_bot_battle, resolve_pvp_battle
from bot.utils.missions import record_progress
from bot.utils.progression import regen_energy
from bot.utils.battle import ATTACK_STRATEGIES, BOT_DIFFICULTIES, can_attack, resolve_bot_battle, resolve_pvp_battle

router = Router(name="battle")

# لول لازم برای باز شدن سختی‌های بالاتر نبرد با ربات
BOT_DIFFICULTY_MIN_LEVEL = {"elite": 10, "boss": 18}


# ---------------------------------------------------------------------------
# منوی اصلی حمله
# ---------------------------------------------------------------------------

def attack_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 نبرد با ربات (NPC)", callback_data="attack_bot_menu")],
            [InlineKeyboardButton(text="👥 نبرد PvP", callback_data="attack_pvp_menu")],
            [InlineKeyboardButton(text="📜 گزارش‌های اخیر", callback_data="show_reports")],
        ]
    )


@router.message(Command("attack"))
async def cmd_attack(message: Message) -> None:
    await message.answer(
        "⚔️ می‌خوای با کی بجنگی؟",
        reply_markup=attack_menu_keyboard(),
    )


@router.callback_query(F.data == "show_attack_menu")
async def cb_attack_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⚔️ می‌خوای با کی بجنگی؟", reply_markup=attack_menu_keyboard())
    await callback.answer()


# ---------------------------------------------------------------------------
# نبرد با ربات (NPC)
# ---------------------------------------------------------------------------
def strategy_keyboard(next_prefix: str) -> InlineKeyboardMarkup:
    """next_prefix مثلا 'attack_bot_strategy' یا 'attack_pvp_strategy'."""
    rows = [
        [InlineKeyboardButton(text=s["label"], callback_data=f"{next_prefix}:{key}")]
        for key, s in ATTACK_STRATEGIES.items()
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_attack_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def strategy_intro_text() -> str:
    lines = ["🎯 <b>استراتژی حمله رو انتخاب کن:</b>\n"]
    for s in ATTACK_STRATEGIES.values():
        lines.append(f"{s['label']}\n   {s['desc']}")
    return "\n\n".join(lines)
    
def bot_difficulty_keyboard(strategy_key: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=d["label"], callback_data=f"attack_bot:{key}:{strategy_key}")]
        for key, d in BOT_DIFFICULTIES.items()
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="attack_bot_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data == "attack_bot_menu")
async def cb_attack_bot_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        strategy_intro_text(), reply_markup=strategy_keyboard("attack_bot_strategy"), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("attack_bot_strategy:"))
async def cb_attack_bot_strategy(callback: CallbackQuery) -> None:
    strategy_key = callback.data.split(":")[1]
    await callback.message.edit_text(
        "🤖 سختی نبرد رو انتخاب کن:", reply_markup=bot_difficulty_keyboard(strategy_key)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("attack_bot:"))
async def cb_attack_bot(callback: CallbackQuery) -> None:
    _, difficulty, strategy_key = callback.data.split(":")

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        attacker = result.scalar_one_or_none()
        if attacker is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        regen_energy(attacker)
        error = can_attack(attacker)
        if error:
            await callback.answer(error, show_alert=True)
            await session.commit()
            return

        report = await resolve_bot_battle(session, attacker, difficulty, strategy_key)
        leveled_up = getattr(report, "_leveled_up", [])
        await record_progress(session, attacker, "bot_battle", 1)
        if report.winner == "attacker":
            await record_progress(session, attacker, "battle_win", 1)
        await session.commit()

        text = build_bot_report_text(report, leveled_up)

    await callback.message.edit_text(
        text, reply_markup=bot_difficulty_keyboard(strategy_key), parse_mode="HTML"
    )
    await callback.answer()

def build_bot_report_text(report: BattleReport, leveled_up: list[int], random_event: str | None = None) -> str:
    won = report.winner == "attacker"
    header = "🎉 <b>پیروز شدی!</b>" if won else "💥 <b>شکست خوردی!</b>"
    lines = [header]

    if random_event == "ambush":
        lines.append("🌫️ <i>کمین!</i> قدرت دشمن غافلگیر شد و ۱۵٪ افت کرد.")
    elif random_event == "critical":
        lines.append("💥 <i>ضربه بحرانی!</i> قدرت حمله‌ات ۱۵٪ اضافه شد.")

    lines += [
        f"⚔️ قدرت تو: {report.attacker_power} | 🤖 قدرت ربات: {report.defender_power}",
        f"❤️ HP از دست رفته: {report.attacker_hp_lost}",
        f"💀 نیروی از دست رفته: {report.attacker_units_lost}",
        f"💰 طلای بدست‌اومده: {report.loot_gold}",
        f"⭐ XP: +{report.xp_gained}",
    ]
    if leveled_up:
        lines.append(f"\n🎊 لول‌آپ کردی! سطح جدید: {leveled_up[-1]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# نبرد PvP
# ---------------------------------------------------------------------------

async def _find_pvp_targets(session, attacker: User) -> list[User]:
    low = attacker.level - settings.PVP_LEVEL_RANGE
    high = attacker.level + settings.PVP_LEVEL_RANGE
    banned_subquery = select(BannedTelegramUser.telegram_id)
    result = await session.execute(
        select(User)
        .where(
            User.id != attacker.id,
            room_condition(User.room_id),  # فقط هم‌گروهی‌های همین روم (یا هم‌بازی‌های پروفایل اصلی)
            User.level.between(low, high),
            User.telegram_id.not_in(banned_subquery),
        )
        .order_by(func.random())
        .limit(settings.PVP_TARGETS_SHOWN)
    )
    return list(result.scalars().all())


def pvp_targets_keyboard(targets: list[User]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"⚔️ {t.nickname} (لول {t.level})",
                callback_data=f"attack_pvp:{t.id}",
            )
        ]
        for t in targets
    ]
    rows.append([InlineKeyboardButton(text="🔄 لیست جدید", callback_data="attack_pvp_menu")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_attack_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "attack_pvp_menu")
async def cb_attack_pvp_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        strategy_intro_text(), reply_markup=strategy_keyboard("attack_pvp_strategy"), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("attack_pvp_strategy:"))
async def cb_attack_pvp_strategy(callback: CallbackQuery) -> None:
    strategy_key = callback.data.split(":")[1]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        attacker = result.scalar_one_or_none()
        if attacker is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return
        targets = await _find_pvp_targets(session, attacker)

    if not targets:
        await callback.message.edit_text(
            "فعلاً هیچ بازیکن هم‌سطحی برای حمله پیدا نشد. بعداً دوباره امتحان کن.",
            reply_markup=attack_menu_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "👥 یکی از این بازیکن‌ها رو برای حمله انتخاب کن:",
        reply_markup=pvp_targets_keyboard(targets, strategy_key),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("attack_pvp:"))
async def cb_attack_pvp(callback: CallbackQuery) -> None:
    defender_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.country)).where(*user_scope(callback.from_user.id))
        )
        attacker = result.scalar_one_or_none()
        if attacker is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        regen_energy(attacker)
        error = can_attack(attacker)
        if error:
            await callback.answer(error, show_alert=True)
            await session.commit()
            return

        defender = await session.get(User, defender_id, options=[selectinload(User.country)])
        if defender is None:
            await callback.answer("این بازیکن دیگه در دسترس نیست.", show_alert=True)
            return
        if defender.room_id != current_room():
            await callback.answer("این بازیکن مال این گروه/چت نیست.", show_alert=True)
            return

        report = await resolve_pvp_battle(session, attacker, defender)
        leveled_up = getattr(report, "_leveled_up", [])
        defender_nickname = defender.nickname
        await record_progress(session, attacker, "pvp_battle", 1)
        if report.winner == "attacker":
            await record_progress(session, attacker, "battle_win", 1)

        # اگه هر دو عضو اتحادن و اتحادهاشون در جنگن، امتیاز جنگ به برنده اضافه میشه
        war_note = ""
        if attacker.alliance_id and defender.alliance_id and attacker.alliance_id != defender.alliance_id:
            war = await get_active_war_between(session, attacker.alliance_id, defender.alliance_id)
            if war is not None:
                winner_alliance_id = attacker.alliance_id if report.winner == "attacker" else defender.alliance_id
                await add_war_score(session, war, winner_alliance_id, report.attacker_power)
                war_note = "\n\n⚔️ این نبرد به امتیاز جنگ اتحادتون اضافه شد!"

        await session.commit()

        text = build_pvp_report_text(report, defender_nickname, leveled_up) + war_note

        defender_notify = defender.notifications_enabled
        defender_telegram_id = defender.telegram_id
        attacker_nickname = attacker.nickname
        defender_won = report.winner == "defender"

    if defender_notify:
        if defender_won:
            outcome_msg = f"⚔️ <b>{attacker_nickname}</b> بهت حمله کرد ولی دفعش کردی! 🛡️"
        else:
            outcome_msg = f"⚔️ <b>{attacker_nickname}</b> بهت حمله کرد و شکستت داد و غارتت کرد! 😡"
        try:
            await callback.bot.send_message(
                defender_telegram_id,
                f"{outcome_msg}\nبرای جزئیات: /reports",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.message.edit_text(text, reply_markup=attack_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


def build_pvp_report_text(report: BattleReport, defender_nickname: str, leveled_up: list[int]) -> str:
    won = report.winner == "attacker"
    header = (
        f"🎉 <b>{defender_nickname} رو شکست دادی!</b>"
        if won
        else f"💥 <b>از {defender_nickname} شکست خوردی!</b>"
    )
    lines = [
        header,
        f"⚔️ قدرت تو: {report.attacker_power} | 🛡️ قدرت طرف مقابل: {report.defender_power}",
        f"❤️ HP از دست رفته: {report.attacker_hp_lost}",
        f"💀 نیروی از دست رفته (تو): {report.attacker_units_lost} | (طرف مقابل): {report.defender_units_lost}",
    ]
    if won:
        loot_parts = []
        if report.loot_gold:
            loot_parts.append(f"💰{report.loot_gold}")
        if report.loot_iron:
            loot_parts.append(f"⛏️{report.loot_iron}")
        if report.loot_oil:
            loot_parts.append(f"🛢️{report.loot_oil}")
        if report.loot_food:
            loot_parts.append(f"🌾{report.loot_food}")
        if loot_parts:
            lines.append("🏴‍☠️ غارت: " + " ".join(loot_parts))
    lines.append(f"⭐ XP: +{report.xp_gained}")
    if leveled_up:
        lines.append(f"\n🎊 لول‌آپ کردی! سطح جدید: {leveled_up[-1]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# گزارش‌های اخیر
# ---------------------------------------------------------------------------

@router.message(Command("reports"))
async def cmd_reports(message: Message) -> None:
    text = await _build_reports_text(message.from_user.id)
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "show_reports")
async def cb_reports(callback: CallbackQuery) -> None:
    text = await _build_reports_text(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=attack_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


async def _build_reports_text(telegram_id: int) -> str:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

        result = await session.execute(
            select(BattleReport)
            .options(selectinload(BattleReport.attacker), selectinload(BattleReport.defender))
            .where(or_(BattleReport.attacker_id == user.id, BattleReport.defender_id == user.id))
            .order_by(BattleReport.created_at.desc())
            .limit(5)
        )
        reports = list(result.scalars().all())

        if not reports:
            return "📜 هنوز هیچ نبردی نداشتی."

        lines = ["📜 <b>۵ نبرد اخیر تو</b>\n"]
        for r in reports:
            is_attacker = r.attacker_id == user.id
            won = (r.winner == "attacker") == is_attacker
            icon = "✅" if won else "❌"
            role = "حمله" if is_attacker else "دفاع"
            if r.defender_id is None:
                opponent = "ربات"
            else:
                opponent = r.defender.nickname if is_attacker else r.attacker.nickname
            lines.append(
                f"{icon} {role} در برابر {opponent} — "
                f"{r.created_at.strftime('%m/%d %H:%M')}"
            )
        return "\n".join(lines)
