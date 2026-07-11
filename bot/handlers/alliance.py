from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.config import settings
from bot.database.db import get_session
from bot.utils.context import room_condition, user_scope
from bot.database.models import Alliance, AllianceChatMessage, AllianceWar, User
from bot.utils.alliance import (
    create_alliance,
    declare_war,
    finish_expired_wars,
    join_alliance,
    kick_member,
    leave_alliance,
)

router = Router(name="alliance")


class AllianceCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_tag = State()


# ---------------------------------------------------------------------------
# منوی اصلی اتحاد
# ---------------------------------------------------------------------------

def alliance_menu_keyboard(in_alliance: bool, is_leader: bool) -> InlineKeyboardMarkup:
    rows = []
    if in_alliance:
        rows.append([InlineKeyboardButton(text="🏛️ اتحاد من", callback_data="show_my_alliance")])
        rows.append([InlineKeyboardButton(text="💬 چت اتحاد (۲۰ پیام اخیر)", callback_data="show_alliance_chat")])
        if is_leader:
            rows.append([InlineKeyboardButton(text="⚔️ اعلام جنگ", callback_data="declare_war_menu")])
            rows.append([InlineKeyboardButton(text="👢 اخراج عضو", callback_data="kick_menu")])
        rows.append([InlineKeyboardButton(text="🚪 ترک اتحاد", callback_data="leave_alliance")])
    else:
        rows.append([InlineKeyboardButton(text="🆕 ساخت اتحاد", callback_data="create_alliance_start")])
        rows.append([InlineKeyboardButton(text="🔍 لیست اتحادها", callback_data="list_alliances")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _menu_view(telegram_id: int) -> tuple[str, InlineKeyboardMarkup]:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None

        in_alliance = user.alliance_id is not None
        is_leader = user.alliance_role == "leader"

    text = "🏛️ <b>اتحاد</b>\n\n" + (
        "تو عضو یک اتحادی. از دکمه‌های زیر استفاده کن:" if in_alliance
        else f"هنوز عضو هیچ اتحادی نیستی.\nساخت اتحاد {settings.ALLIANCE_CREATE_COST_GOLD} طلا هزینه داره."
    )
    return text, alliance_menu_keyboard(in_alliance, is_leader)


@router.message(Command("alliance"))
async def cmd_alliance(message: Message) -> None:
    text, keyboard = await _menu_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_alliance_menu")
async def cb_alliance_menu(callback: CallbackQuery) -> None:
    text, keyboard = await _menu_view(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# ساخت اتحاد (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "create_alliance_start")
async def cb_create_alliance_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("اسم اتحادت رو بفرست (۳ تا ۶۴ حرف):")
    await state.set_state(AllianceCreation.waiting_for_name)
    await callback.answer()


@router.message(AllianceCreation.waiting_for_name)
async def process_alliance_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not (3 <= len(name) <= 64):
        await message.answer("اسم باید بین ۳ تا ۶۴ حرف باشه. دوباره امتحان کن:")
        return
    await state.update_data(name=name)
    await message.answer("عالی! حالا یه تگ کوتاه بفرست (۲ تا ۸ حرف، مثلا IRN):")
    await state.set_state(AllianceCreation.waiting_for_tag)


@router.message(AllianceCreation.waiting_for_tag)
async def process_alliance_tag(message: Message, state: FSMContext) -> None:
    tag = (message.text or "").strip().upper()
    if not (2 <= len(tag) <= 8):
        await message.answer("تگ باید بین ۲ تا ۸ حرف باشه. دوباره امتحان کن:")
        return

    data = await state.get_data()
    name = data["name"]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            await state.clear()
            return

        alliance = await create_alliance(session, user, name, tag)
        if isinstance(alliance, str):
            await message.answer(f"❌ {alliance}")
            return

        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ اتحاد «{name}» [{tag}] ساخته شد و تو رهبرشی!",
        reply_markup=alliance_menu_keyboard(True, True),
    )


# ---------------------------------------------------------------------------
# لیست اتحادها / عضویت
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "list_alliances")
async def cb_list_alliances(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(Alliance)
            .where(room_condition(Alliance.room_id))
            .order_by(Alliance.created_at.desc())
            .limit(10)
        )
        alliances = list(result.scalars().all())

        rows = []
        for a in alliances:
            result2 = await session.execute(select(User).where(User.alliance_id == a.id))
            member_count = len(result2.scalars().all())
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"[{a.tag}] {a.name} ({member_count}/{a.member_limit})",
                        callback_data=f"join_alliance:{a.id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_alliance_menu")])

    if not alliances:
        await callback.message.edit_text(
            "هنوز هیچ اتحادی ساخته نشده. اولین نفر باش!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    else:
        await callback.message.edit_text(
            "🔍 یکی از اتحادها رو برای عضویت انتخاب کن:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("join_alliance:"))
async def cb_join_alliance(callback: CallbackQuery) -> None:
    alliance_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        alliance = await session.get(Alliance, alliance_id)
        if alliance is None:
            await callback.answer("این اتحاد دیگه پیدا نشد.", show_alert=True)
            return

        error = await join_alliance(session, user, alliance)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer(f"✅ به «{alliance.name}» پیوستی!", show_alert=True)

    text, keyboard = await _menu_view(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ---------------------------------------------------------------------------
# نمایش اتحاد من
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "show_my_alliance")
async def cb_my_alliance(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None or user.alliance_id is None:
            await callback.answer("تو عضو هیچ اتحادی نیستی.", show_alert=True)
            return

        alliance = await session.get(Alliance, user.alliance_id)
        result = await session.execute(
            select(User).where(User.alliance_id == alliance.id).order_by(User.level.desc())
        )
        members = list(result.scalars().all())

        await finish_expired_wars(session)
        result = await session.execute(
            select(AllianceWar).where(
                AllianceWar.status == "active",
                (AllianceWar.alliance_a_id == alliance.id) | (AllianceWar.alliance_b_id == alliance.id),
            )
        )
        active_wars = list(result.scalars().all())
        await session.commit()

        role_icon = {"leader": "👑", "officer": "⭐", "member": "👤"}
        lines = [f"🏛️ <b>[{alliance.tag}] {alliance.name}</b>", f"{alliance.description or 'بدون توضیحات'}\n"]
        lines.append(f"👥 اعضا ({len(members)}/{alliance.member_limit}):")
        for m in members:
            icon = role_icon.get(m.alliance_role, "👤")
            lines.append(f"  {icon} {m.nickname} (لول {m.level})")

        if active_wars:
            lines.append("\n⚔️ <b>جنگ‌های فعال:</b>")
            for w in active_wars:
                other_id = w.alliance_b_id if w.alliance_a_id == alliance.id else w.alliance_a_id
                other = await session.get(Alliance, other_id)
                my_score = w.score_a if w.alliance_a_id == alliance.id else w.score_b
                their_score = w.score_b if w.alliance_a_id == alliance.id else w.score_a
                lines.append(f"  🆚 {other.name if other else 'نامشخص'}: {my_score} - {their_score}")

        text = "\n".join(lines)

    await callback.message.edit_text(
        text, reply_markup=alliance_menu_keyboard(True, user.alliance_role == "leader"), parse_mode="HTML"
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# ترک اتحاد
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "leave_alliance")
async def cb_leave_alliance(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        error = await leave_alliance(session, user)
        if error:
            await callback.answer(error, show_alert=True)
            return
        await session.commit()
        await callback.answer("✅ از اتحاد خارج شدی.", show_alert=True)

    text, keyboard = await _menu_view(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ---------------------------------------------------------------------------
# اخراج عضو (فقط رهبر/افسر)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "kick_menu")
async def cb_kick_menu(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        leader = result.scalar_one_or_none()
        if leader is None or leader.alliance_role not in ("leader", "officer"):
            await callback.answer("فقط رهبر یا افسر می‌تونه اعضا رو مدیریت کنه.", show_alert=True)
            return

        result = await session.execute(
            select(User).where(User.alliance_id == leader.alliance_id, User.id != leader.id)
        )
        members = list(result.scalars().all())

    rows = [
        [InlineKeyboardButton(text=f"👢 {m.nickname}", callback_data=f"do_kick:{m.id}")] for m in members
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_my_alliance")])

    if not members:
        await callback.message.edit_text(
            "به‌جز خودت عضو دیگه‌ای نیست.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    else:
        await callback.message.edit_text(
            "کی رو می‌خوای اخراج کنی؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("do_kick:"))
async def cb_do_kick(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        leader = result.scalar_one_or_none()
        target = await session.get(User, target_id)
        if leader is None or target is None:
            await callback.answer("کاربر پیدا نشد.", show_alert=True)
            return

        error = await kick_member(session, leader, target)
        if error:
            await callback.answer(error, show_alert=True)
            return
        await session.commit()
        await callback.answer(f"✅ {target.nickname} اخراج شد.", show_alert=True)

    await cb_kick_menu(callback)


# ---------------------------------------------------------------------------
# چت اتحاد
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "show_alliance_chat")
async def cb_alliance_chat(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None or user.alliance_id is None:
            await callback.answer("تو عضو هیچ اتحادی نیستی.", show_alert=True)
            return

        result = await session.execute(
            select(AllianceChatMessage)
            .where(AllianceChatMessage.alliance_id == user.alliance_id)
            .order_by(AllianceChatMessage.created_at.desc())
            .limit(settings.ALLIANCE_CHAT_HISTORY_LIMIT)
        )
        messages = list(result.scalars().all())[::-1]

        lines = ["💬 <b>چت اتحاد</b> (۲۰ پیام اخیر)\n"]
        for m in messages:
            sender = await session.get(User, m.user_id)
            name = sender.nickname if sender else "؟"
            lines.append(f"<b>{name}:</b> {m.message}")
        lines.append("\n✏️ برای ارسال پیام بنویس: <code>/asay پیامت</code>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=alliance_menu_keyboard(True, user.alliance_role == "leader"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("asay"))
async def cmd_asay(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer("بعد از دستور، پیامت رو بنویس. مثال: /asay سلام به همه!")
        return
    if len(text) > 500:
        text = text[:500]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None or user.alliance_id is None:
            await message.answer("تو عضو هیچ اتحادی نیستی.")
            return

        chat_message = AllianceChatMessage(alliance_id=user.alliance_id, user_id=user.id, message=text)
        session.add(chat_message)

        result = await session.execute(
            select(User).where(User.alliance_id == user.alliance_id, User.id != user.id)
        )
        other_members = list(result.scalars().all())
        await session.commit()

    broadcast_text = f"💬 <b>[اتحاد] {user.nickname}:</b> {text}"
    for member in other_members:
        if not member.notifications_enabled:
            continue
        try:
            await message.bot.send_message(member.telegram_id, broadcast_text, parse_mode="HTML")
        except Exception:
            pass  # کاربر شاید ربات رو بلاک کرده - نادیده می‌گیریم

    await message.answer("✅ پیام به اتحاد ارسال شد.")


# ---------------------------------------------------------------------------
# اعلام جنگ
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "declare_war_menu")
async def cb_declare_war_menu(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        leader = result.scalar_one_or_none()
        if leader is None or leader.alliance_role != "leader":
            await callback.answer("فقط رهبر می‌تونه اعلام جنگ کنه.", show_alert=True)
            return

        result = await session.execute(
            select(Alliance)
            .where(Alliance.id != leader.alliance_id, room_condition(Alliance.room_id))
            .limit(10)
        )
        targets = list(result.scalars().all())

    rows = [
        [InlineKeyboardButton(text=f"⚔️ [{a.tag}] {a.name}", callback_data=f"do_declare_war:{a.id}")]
        for a in targets
    ]
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_my_alliance")])

    if not targets:
        await callback.message.edit_text(
            "هیچ اتحاد دیگه‌ای برای جنگ وجود نداره.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    else:
        await callback.message.edit_text(
            "🎯 به کدوم اتحاد اعلام جنگ کنیم؟", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("do_declare_war:"))
async def cb_do_declare_war(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        leader = result.scalar_one_or_none()
        target_alliance = await session.get(Alliance, target_id)
        if leader is None or target_alliance is None:
            await callback.answer("اتحاد پیدا نشد.", show_alert=True)
            return

        war = await declare_war(session, leader, target_alliance)
        if isinstance(war, str):
            await callback.answer(war, show_alert=True)
            return

        await session.commit()
        await callback.answer(
            f"⚔️ جنگ با [{target_alliance.tag}] {target_alliance.name} شروع شد! "
            f"({settings.ALLIANCE_WAR_DURATION_HOURS} ساعت طول می‌کشه)",
            show_alert=True,
        )

    await cb_my_alliance(callback)
