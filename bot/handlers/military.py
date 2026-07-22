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
    get_bonus_percent,
    research_cost,
    research_duration,
    start_research,
    start_training,
    training_cost,
    training_duration,
)
from bot.utils.missions import record_progress
from bot.utils.room_settings import deliver_sensitive_content

NOT_REGISTERED_MSG = "هنوز ثبت‌نام نکردی! دستور /start رو بزن."

router = Router(name="military")

BUY_QUANTITIES = [1, 10, 50]

# ترتیب نمایش دسته‌های اصلی و زیردسته‌ها تو منوی ارتش
CATEGORY_GROUP_LABELS = {"ground": "🪖 نیروی زمینی", "air": "✈️ نیروی هوایی", "navy": "🚢 نیروی دریایی"}
SUBCATEGORY_LABELS = {
    "infantry": "🪖 پیاده‌نظام",
    "tank": "🛡️ تانک",
    "artillery": "💥 توپخانه",
    "missile": "🚀 موشک",
    "air_defense": "🛰️ پدافند هوایی",
    "fighter": "🛩️ جنگنده",
    "drone": "🛸 پهپاد",
    "bomber": "💣 بمب‌افکن",
    "navy": "🚢 دریایی",
}
SUBCATEGORY_ORDER = list(SUBCATEGORY_LABELS.keys())


# ---------------------------------------------------------------------------
# بارگذاری و همگام‌سازی
# ---------------------------------------------------------------------------

async def _backfill_missing_rows(session, user: User) -> None:
    """اگه بعد از ثبت‌نام کاربر، نوع نیرو یا تحقیق جدیدی به کاتالوگ اضافه شده باشه، می‌سازتش."""
    result = await session.execute(select(UnitType))
    all_unit_types = list(result.scalars().all())
    result = await session.execute(select(UserUnit).where(UserUnit.user_id == user.id))
    existing_unit_type_ids = {uu.unit_type_id for uu in result.scalars().all()}
    for ut in all_unit_types:
        if ut.id not in existing_unit_type_ids:
            session.add(UserUnit(user_id=user.id, unit_type_id=ut.id, quantity=0))

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

    result = await session.execute(select(TrainingOrder).where(TrainingOrder.user_id == user.id))
    orders = list(result.scalars().all())

    result = await session.execute(
        select(UserResearch)
        .options(selectinload(UserResearch.research_type))
        .where(UserResearch.user_id == user.id)
    )
    user_researches = list(result.scalars().all())

    units_by_type = {uu.unit_type_id: uu for uu in user_units}
    finished_orders = finish_ready_training(orders, units_by_type)
    for order in finished_orders:
        await session.delete(order)
        orders.remove(order)

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
# نمایش لیست ارتش (دسته‌بندی‌شده، با قفل نیروهای سطح‌نرسیده)
# ---------------------------------------------------------------------------

def build_army_text(
    user: User, user_units: list[UserUnit], orders: list[TrainingOrder], atk_bonus: float, def_bonus: float
) -> str:
    lines = ["⚔️ <b>ارتش تو</b>\n"]
    pending_by_type: dict[int, int] = {}
    for o in orders:
        pending_by_type[o.unit_type_id] = pending_by_type.get(o.unit_type_id, 0) + o.quantity

    units_by_subcategory: dict[str, list[UserUnit]] = {}
    for uu in user_units:
        units_by_subcategory.setdefault(uu.unit_type.subcategory, []).append(uu)

    total_attack = total_defense = 0
    for subcat in SUBCATEGORY_ORDER:
        rows = units_by_subcategory.get(subcat)
        if not rows:
            continue
        rows.sort(key=lambda uu: uu.unit_type.tier)
        lines.append(f"\n<b>{SUBCATEGORY_LABELS[subcat]}</b>")
        for uu in rows:
            ut = uu.unit_type
            atk = effective_attack(ut, atk_bonus)
            dfn = effective_defense(ut, def_bonus)
            total_attack += atk * uu.quantity
            total_defense += dfn * uu.quantity

            if user.level < ut.min_player_level:
                lines.append(f"  🔒 {ut.icon} {ut.name_fa} — نیاز به سطح {ut.min_player_level}")
                continue

            pending = pending_by_type.get(ut.id, 0)
            pending_txt = f" (⏳ +{pending})" if pending else ""
            lines.append(f"  {ut.icon} <b>{ut.name_fa}</b>: {uu.quantity} عدد{pending_txt}")

    lines.append(f"\n📊 مجموع قدرت — ⚔️ حمله: {total_attack} | 🛡️ دفاع: {total_defense}")
    return "\n".join(lines)


def army_keyboard(user: User, user_units: list[UserUnit]) -> InlineKeyboardMarkup:
    rows = []
    units_by_subcategory: dict[str, list[UserUnit]] = {}
    for uu in user_units:
        units_by_subcategory.setdefault(uu.unit_type.subcategory, []).append(uu)

    for subcat in SUBCATEGORY_ORDER:
        unlocked = [uu for uu in units_by_subcategory.get(subcat, []) if user.level >= uu.unit_type.min_player_level]
        if not unlocked:
            continue
        unlocked.sort(key=lambda uu: uu.unit_type.tier)
        row = []
        for uu in unlocked:
            ut = uu.unit_type
            row.append(InlineKeyboardButton(text=f"{ut.icon} {ut.name_fa}", callback_data=f"unit_menu:{ut.id}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

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
        text = build_army_text(user, user_units, orders, atk_bonus, def_bonus)
        return text, army_keyboard(user, user_units)


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
# جزئیات + خرید یک نوع نیرو (بدون ارتقای سطحی - هر نیرو خودش یه ردیف ثابته)
# ---------------------------------------------------------------------------

def unit_detail_keyboard(unit_type_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=f"🛒 خرید {q}", callback_data=f"buy_unit:{unit_type_id}:{q}")
            for q in BUY_QUANTITIES
        ],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="show_army")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_unit_detail_text(uu: UserUnit, speed_bonus: float, atk_bonus: float, def_bonus: float) -> str:
    ut = uu.unit_type
    atk = effective_attack(ut, atk_bonus)
    dfn = effective_defense(ut, def_bonus)

    lines = [
        f"{ut.icon} <b>{ut.name_fa}</b>",
        f"تعداد فعلی: {uu.quantity}",
        f"⚔️ حمله (هر واحد): {atk}  🛡️ دفاع (هر واحد): {dfn}\n",
        "💰 هزینه هر واحد:",
        f"  {ut.cost_gold} طلا"
        + (f" + {ut.cost_iron} آهن" if ut.cost_iron else "")
        + (f" + {ut.cost_oil} نفت" if ut.cost_oil else "")
        + (f" + {ut.cost_uranium} اورانیوم" if ut.cost_uranium else ""),
    ]

    for q in BUY_QUANTITIES:
        cost = training_cost(ut, q)
        duration = training_duration(ut, q, speed_bonus)
        minutes = max(1, int(duration.total_seconds() // 60))
        lines.append(f"  خرید {q} عدد → {minutes} دقیقه زمان آموزش")

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
        if user.level < uu.unit_type.min_player_level:
            await callback.answer(f"این نیرو نیاز به سطح {uu.unit_type.min_player_level} داره.", show_alert=True)
            return

        text = build_unit_detail_text(
            uu, _training_speed_bonus(user_researches), _attack_bonus(user_researches), _defense_bonus(user_researches)
        )

    try:
        await callback.message.edit_text(text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=unit_detail_keyboard(unit_type_id), parse_mode="HTML")
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
            return NOT_REGISTERED_MSG, None
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
