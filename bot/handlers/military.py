from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import current_room, user_scope
from bot.database.models import (
    ResearchType,
    TrainingOrder,
    UnitType,
    User,
    UserResearch,
    UserUnit,
)
from bot.utils.military import (
    effective_attack,
    effective_defense,
    finish_ready_research,
    finish_ready_training,
    finish_ready_unit_upgrades,
    get_bonus_percent,
    research_cost,
    research_duration,
    start_research,
    start_training,
    start_unit_upgrade,
    training_cost,
    training_duration,
    unit_upgrade_cost,
    unit_upgrade_duration,
)
from bot.utils.missions import record_progress
from bot.utils.room_settings import deliver_sensitive_content

NOT_REGISTERED_MSG = "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

router = Router(name="military")

BUY_QUANTITIES = [1, 10, 50]


# ---------------------------------------------------------------------------
# بارگذاری و همگام‌سازی
# ---------------------------------------------------------------------------

async def _backfill_missing_rows(session, user: User) -> None:
    """
    اگه بعد از ثبت‌نام کاربر، نوع نیرو یا تحقیق جدیدی به کاتالوگ اضافه شده باشه
    (مثلاً بمب‌افکن یا یه تحقیق جدید)، این تابع ردیف‌های ازقلم‌افتاده رو
    می‌سازه. بدون این، کاربرهای قدیمی هیچ‌وقت آیتم‌های جدید رو نمی‌بینن.
    """
    result = await session.execute(select(UnitType))
    all_unit_types = list(result.scalars().all())
    result = await session.execute(select(UserUnit).where(UserUnit.user_id == user.id))
    existing_unit_type_ids = {uu.unit_type_id for uu in result.scalars().all()}
    for ut in all_unit_types:
        if ut.id not in existing_unit_type_ids:
            session.add(UserUnit(user_id=user.id, unit_type_id=ut.id, quantity=0, level=1))

    result = await session.execute(select(ResearchType))
    all_research_types = list(result.scalars().all())
    result = await session.execute(select(UserResearch).where(UserResearch.user_id == user.id))
    existing_research_type_ids = {ur.research_type_id for ur in result.scalars().all()}
    for rt in all_research_types:
        if rt.id not in existing_research_type_ids:
            session.add(UserResearch(user_id=user.id, research_type_id=rt.id, level=0))


async def _load_state(session, telegram_id: int):
    """کاربر + نیروها + سفارش‌های آموزش + تحقیقات رو با هم برمی‌گردونه و سینک می‌کنه."""
    result = await session.execute(select(User).where(*user_scope(telegram_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None, [], [], []

    await _backfill_missing_rows(session, user)
    await session.flush()

    result = await session.execute(
        select(UserUnit).options(selectinload(UserUnit.unit_type)).where(UserUnit.user_id == user.id)
    )
    user_units = list(result.scalars().all())

    result = await session.execute(
        select(TrainingOrder).where(TrainingOrder.user_id == user.id)
    )
    orders = list(result.scalars().all())

    result = await session.execute(
        select(UserResearch)
        .options(selectinload(UserResearch.research_type))
        .where(UserResearch.user_id == user.id)
    )
    user_researches = list(result.scalars().all())

    # اتمام آموزش‌های تموم‌شده
    units_by_type = {uu.unit_type_id: uu for uu in user_units}
    finished_orders = finish_ready_training(orders, units_by_type)
    for order in finished_orders:
        await session.delete(order)
        orders.remove(order)

    # اتمام ارتقای نیروهای تموم‌شده
    finish_ready_unit_upgrades(user_units)

    # اتمام تحقیقات تموم‌شده
    finish_ready_research(user_researches)

    await session.commit()
    return user, user_units, orders, user_researches


def _training_speed_bonus(user_researches: list[UserResearch]) -> float:
    return get_bonus_percent(user_researches, "training_speed_percent")


def _attack_bonus(user_researches: list[UserResearch]) -> float:
    return get_bonus_percent(user_researches, "attack_percent")


def _defense_bonus(user_researches: list[UserResearch]) -> float:
    return get_bonus_percent(user_researches, "defense_percent")


# ---------------------------------------------------------------------------
# نمایش لیست ارتش
# ---------------------------------------------------------------------------

def build_army_text(user_units: list[UserUnit], orders: list[TrainingOrder], atk_bonus: float, def_bonus: float) -> str:
    lines = ["⚔️ <b>ارتش تو</b>\n"]
    pending_by_type: dict[int, int] = {}
    for o in orders:
        pending_by_type[o.unit_type_id] = pending_by_type.get(o.unit_type_id, 0) + o.quantity

    total_attack = total_defense = 0
    for uu in sorted(user_units, key=lambda x: x.unit_type.id):
        ut = uu.unit_type
        atk = effective_attack(ut, uu, atk_bonus)
        dfn = effective_defense(ut, uu, def_bonus)
        total_attack += atk * uu.quantity
        total_defense += dfn * uu.quantity

        pending = pending_by_type.get(ut.id, 0)
        pending_txt = f" (⏳ +{pending} در حال آموزش)" if pending else ""
        upgrading_txt = " (⏳ در حال ارتقا)" if uu.upgrade_finish_at else ""

        lines.append(
            f"{ut.icon} <b>{ut.name_fa}</b>: {uu.quantity} عدد | لول {uu.level}{upgrading_txt}\n"
            f"   ⚔️حمله:{atk} 🛡️دفاع:{dfn}{pending_txt}"
        )

    lines.append(f"\n📊 مجموع قدرت — ⚔️ حمله: {total_attack} | 🛡️ دفاع: {total_defense}")
    return "\n".join(lines)


def army_keyboard(user_units: list[UserUnit]) -> InlineKeyboardMarkup:
    rows = []
    for uu in sorted(user_units, key=lambda x: x.unit_type.id):
        ut = uu.unit_type
        rows.append(
            [InlineKeyboardButton(text=f"{ut.icon} {ut.name_fa}", callback_data=f"unit_menu:{ut.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔬 تحقیق و توسعه", callback_data="show_research")])
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_army")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _army_view(telegram_id: int):
    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, telegram_id)
        if user is None:
            return NOT_REGISTERED_MSG, None
        atk_bonus = _attack_bonus(user_researches)
        def_bonus = _defense_bonus(user_researches)
        text = build_army_text(user_units, orders, atk_bonus, def_bonus)
        return text, army_keyboard(user_units)


@router.message(Command("army"))
async def cmd_army(message: Message) -> None:
    text, keyboard = await _army_view(message.from_user.id)
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


@router.callback_query(F.data == "show_army")
async def cb_army(callback: CallbackQuery) -> None:
    text, keyboard = await _army_view(callback.from_user.id)
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


# ---------------------------------------------------------------------------
# جزئیات + خرید + ارتقای یک نوع نیرو
# ---------------------------------------------------------------------------

def unit_detail_keyboard(unit_type_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=f"🛒 خرید {q}", callback_data=f"buy_unit:{unit_type_id}:{q}")
            for q in BUY_QUANTITIES
        ],
        [InlineKeyboardButton(text="⬆️ ارتقای این نیرو", callback_data=f"upgrade_unit:{unit_type_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_army")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_unit_detail_text(uu: UserUnit, speed_bonus: float, atk_bonus: float, def_bonus: float) -> str:
    ut = uu.unit_type
    atk = effective_attack(ut, uu, atk_bonus)
    dfn = effective_defense(ut, uu, def_bonus)

    lines = [
        f"{ut.icon} <b>{ut.name_fa}</b>",
        f"تعداد فعلی: {uu.quantity} | لول: {uu.level}/{ut.max_level}",
        f"⚔️ حمله (هر واحد): {atk}  🛡️ دفاع (هر واحد): {dfn}\n",
        "💰 هزینه هر واحد:",
        f"  {ut.cost_gold} طلا"
        + (f" + {ut.cost_iron} آهن" if ut.cost_iron else "")
        + (f" + {ut.cost_oil} نفت" if ut.cost_oil else ""),
    ]

    for q in BUY_QUANTITIES:
        cost = training_cost(ut, q)
        duration = training_duration(ut, q, speed_bonus)
        minutes = max(1, int(duration.total_seconds() // 60))
        lines.append(f"  خرید {q} عدد → {minutes} دقیقه زمان آموزش")

    if uu.level < ut.max_level:
        up_cost = unit_upgrade_cost(ut, uu.level)
        up_duration = unit_upgrade_duration(uu.level)
        up_minutes = max(1, int(up_duration.total_seconds() // 60))
        parts = [f"{up_cost['gold']} طلا"]
        if up_cost["iron"]:
            parts.append(f"{up_cost['iron']} آهن")
        if up_cost["oil"]:
            parts.append(f"{up_cost['oil']} نفت")
        lines.append(
            f"\n⬆️ ارتقا به لول {uu.level + 1}: {' + '.join(parts)} — {up_minutes} دقیقه"
            f" (هر لول {int(100 * 0.10)}٪ به حمله/دفاع اضافه می‌کنه)"
        )
    else:
        lines.append("\n⬆️ این نیرو به حداکثر سطح رسیده.")

    if uu.upgrade_finish_at is not None:
        lines.append("\n⏳ همین الان در حال ارتقاست.")

    return "\n".join(lines)


@router.callback_query(F.data.startswith("unit_menu:"))
async def cb_unit_menu(callback: CallbackQuery) -> None:
    unit_type_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, callback.from_user.id)
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return
        uu = next((u for u in user_units if u.unit_type_id == unit_type_id), None)
        if uu is None:
            await callback.answer("این نیرو پیدا نشد.", show_alert=True)
            return

        text = build_unit_detail_text(
            uu, _training_speed_bonus(user_researches), _attack_bonus(user_researches), _defense_bonus(user_researches)
        )

    try:
        await callback.message.edit_text(
            text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_unit:"))
async def cb_buy_unit(callback: CallbackQuery) -> None:
    _, unit_type_id_str, qty_str = callback.data.split(":")
    unit_type_id, qty = int(unit_type_id_str), int(qty_str)

    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, callback.from_user.id)
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        result = await session.execute(select(UnitType).where(UnitType.id == unit_type_id))
        unit_type = result.scalar_one_or_none()
        if unit_type is None:
            await callback.answer("این نیرو پیدا نشد.", show_alert=True)
            return

        speed_bonus = _training_speed_bonus(user_researches)
        result = start_training(user, unit_type, qty, speed_bonus)

        if isinstance(result, str):
            await callback.answer(result, show_alert=True)
            return

        session.add(result)
        await record_progress(session, user, "train_units", qty)
        await session.commit()

        await callback.answer(f"✅ آموزش {qty} {unit_type.name_fa} شروع شد!", show_alert=True)

    text, keyboard = await _army_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("upgrade_unit:"))
async def cb_upgrade_unit(callback: CallbackQuery) -> None:
    unit_type_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, callback.from_user.id)
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        uu = next((u for u in user_units if u.unit_type_id == unit_type_id), None)
        if uu is None:
            await callback.answer("این نیرو پیدا نشد.", show_alert=True)
            return

        error = start_unit_upgrade(user, uu, uu.unit_type)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await session.commit()
        await callback.answer("✅ ارتقا شروع شد!", show_alert=True)

    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, callback.from_user.id)
        uu = next((u for u in user_units if u.unit_type_id == unit_type_id), None)
        text = build_unit_detail_text(
            uu, _training_speed_bonus(user_researches), _attack_bonus(user_researches), _defense_bonus(user_researches)
        )
    try:
        await callback.message.edit_text(
            text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML"
        )


# ---------------------------------------------------------------------------
# تحقیق و توسعه
# ---------------------------------------------------------------------------

def research_keyboard(user_researches: list[UserResearch]) -> InlineKeyboardMarkup:
    rows = []
    for ur in sorted(user_researches, key=lambda x: x.research_type.id):
        rt = ur.research_type
        if ur.upgrade_finish_at is not None:
            label = f"{rt.icon} {rt.name_fa} ⏳ در حال تحقیق..."
            rows.append([InlineKeyboardButton(text=label, callback_data="research_busy")])
        elif ur.level >= rt.max_level:
            label = f"{rt.icon} {rt.name_fa} (لول {ur.level} - MAX)"
            rows.append([InlineKeyboardButton(text=label, callback_data="research_max")])
        else:
            label = f"{rt.icon} {rt.name_fa} (لول {ur.level} → {ur.level + 1})"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"do_research:{rt.id}")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به ارتش", callback_data="show_army")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_research_text(user_researches: list[UserResearch]) -> str:
    lines = ["🔬 <b>تحقیق و توسعه</b>\n(بونوس‌ها روی کل ارتش اثر می‌ذارن)\n"]
    for ur in sorted(user_researches, key=lambda x: x.research_type.id):
        rt = ur.research_type
        current_bonus = rt.effect_per_level * ur.level
        status = f"لول {ur.level}/{rt.max_level} — بونوس فعلی: +{current_bonus:.0f}٪"
        if ur.upgrade_finish_at is not None:
            status += " (⏳ در حال تحقیق)"
        elif ur.level < rt.max_level:
            cost = research_cost(rt, ur.level)
            duration = research_duration(rt, ur.level)
            minutes = max(1, int(duration.total_seconds() // 60))
            parts = [f"{cost['gold']} طلا"]
            if cost["iron"]:
                parts.append(f"{cost['iron']} آهن")
            if cost["oil"]:
                parts.append(f"{cost['oil']} نفت")
            status += f"\n   ارتقای بعدی: {' + '.join(parts)} — {minutes} دقیقه"
        lines.append(f"{rt.icon} <b>{rt.name_fa}</b>: {status}")
    return "\n\n".join(lines)


async def _research_view(telegram_id: int):
    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, telegram_id)
        if user is None:
            return "هنوز ثبت‌نام نکردی! دستور /start رو بزن.", None
        return build_research_text(user_researches), research_keyboard(user_researches)


@router.message(Command("research"))
async def cmd_research(message: Message) -> None:
    text, keyboard = await _research_view(message.from_user.id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "show_research")
async def cb_research(callback: CallbackQuery) -> None:
    text, keyboard = await _research_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("do_research:"))
async def cb_do_research(callback: CallbackQuery) -> None:
    research_type_id = int(callback.data.split(":")[1])

    async with get_session() as session:
        user, user_units, orders, user_researches = await _load_state(session, callback.from_user.id)
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        ur = next((r for r in user_researches if r.research_type_id == research_type_id), None)
        if ur is None:
            await callback.answer("این تحقیق پیدا نشد.", show_alert=True)
            return

        error = start_research(user, ur, ur.research_type)
        if error:
            await callback.answer(error, show_alert=True)
            return

        await record_progress(session, user, "research_upgrade", 1)
        await session.commit()
        await callback.answer("✅ تحقیق شروع شد!", show_alert=True)

    text, keyboard = await _research_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.in_({"research_busy", "research_max"}))
async def cb_research_noop(callback: CallbackQuery) -> None:
    if callback.data == "research_busy":
        await callback.answer("این تحقیق الان در حال انجامه، صبر کن.", show_alert=True)
    else:
        await callback.answer("این تحقیق به حداکثر سطح رسیده.", show_alert=True)
