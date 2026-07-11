from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.config import settings
from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import Country, CountryStatement, User
from bot.utils.statements import (
    approve_statement,
    build_review_text,
    can_submit_statement,
    create_statement,
    reject_statement,
)

router = Router(name="statements")


class StatementSubmission(StatesGroup):
    waiting_for_text = State()


class RejectStatement(StatesGroup):
    waiting_for_reason = State()


STATUS_LABELS = {
    "pending": "🟡 در انتظار بررسی",
    "approved": "✅ تایید و منتشر شد",
    "rejected": "❌ رد شد",
}

MENU_TEXT = (
    "📜 <b>بیانیه ملی</b>\n\n"
    "هر کاربری که یک کشور انتخاب کرده باشه می‌تونه به نمایندگی از اون کشور بیانیه رسمی بده.\n"
    "بیانیه اول برای بررسی به ادمین‌ها فرستاده میشه و بعد از تایید، توی کانال بیانیه‌ها منتشر میشه."
)


def fmt_remaining(td) -> str:
    if td is None:
        return ""
    total_minutes = max(1, int(td.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours} ساعت و {minutes} دقیقه دیگه"
    return f"{minutes} دقیقه دیگه"


def statement_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ ثبت بیانیه جدید", callback_data="new_statement_start")],
            [InlineKeyboardButton(text="📜 بیانیه‌های من", callback_data="my_statements")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="show_main_menu")],
        ]
    )


def review_keyboard(statement_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید و انتشار", callback_data=f"stmt_approve:{statement_id}"),
                InlineKeyboardButton(text="❌ رد کردن", callback_data=f"stmt_reject:{statement_id}"),
            ]
        ]
    )


@router.message(Command("statement"))
async def cmd_statement(message: Message) -> None:
    await message.answer(MENU_TEXT, reply_markup=statement_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "show_statement_menu")
async def cb_statement_menu(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(MENU_TEXT, reply_markup=statement_menu_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(MENU_TEXT, reply_markup=statement_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# ثبت بیانیه جدید (FSM)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "new_statement_start")
async def cb_new_statement_start(callback: CallbackQuery, state: FSMContext) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return
        if user.country_id is None:
            await callback.answer("تو هنوز کشوری انتخاب نکردی.", show_alert=True)
            return

        can_submit, remaining = await can_submit_statement(session, user.id)
        if not can_submit:
            await callback.answer(
                f"هنوز نمی‌تونی بیانیه جدید بدی. {fmt_remaining(remaining)} صبر کن.", show_alert=True
            )
            return

    await callback.message.answer(
        f"متن بیانیه‌ات رو بنویس ({settings.STATEMENT_MIN_LENGTH} تا {settings.STATEMENT_MAX_LENGTH} حرف).\n"
        "بعد از ثبت، برای بررسی به ادمین‌ها ارسال میشه."
    )
    await state.set_state(StatementSubmission.waiting_for_text)
    await callback.answer()


@router.message(StatementSubmission.waiting_for_text)
async def process_statement_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    await state.clear()

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        statement = create_statement(user, text)
        if isinstance(statement, str):
            await message.answer(f"❌ {statement}", reply_markup=statement_menu_keyboard())
            return

        session.add(statement)
        await session.flush()

        country = await session.get(Country, user.country_id)
        review_text = build_review_text(statement, country, user)
        statement_id = statement.id
        await session.commit()

    await message.answer(
        "✅ بیانیه‌ات ثبت شد و برای بررسی به ادمین‌ها ارسال شد.\nنتیجه بهت اطلاع داده میشه.",
        reply_markup=statement_menu_keyboard(),
    )

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id, review_text, reply_markup=review_keyboard(statement_id), parse_mode="HTML"
            )
        except Exception:
            pass  # ادمین شاید هنوز چت خصوصی با ربات رو باز نکرده


# ---------------------------------------------------------------------------
# بیانیه‌های من
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "my_statements")
async def cb_my_statements(callback: CallbackQuery) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(callback.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("هنوز ثبت‌نام نکردی!", show_alert=True)
            return

        result = await session.execute(
            select(CountryStatement)
            .where(CountryStatement.user_id == user.id)
            .order_by(CountryStatement.created_at.desc())
            .limit(10)
        )
        statements = list(result.scalars().all())

    if not statements:
        text = "📜 هنوز هیچ بیانیه‌ای ثبت نکردی."
    else:
        lines = ["📜 <b>۱۰ بیانیه اخیر تو</b>\n"]
        for s in statements:
            status = STATUS_LABELS.get(s.status, s.status)
            line = f"{status}\n📝 {s.text}"
            if s.status == "rejected" and s.reject_reason:
                line += f"\n💬 دلیل رد: {s.reject_reason}"
            lines.append(line)
        text = "\n\n".join(lines)

    try:
        await callback.message.edit_text(text, reply_markup=statement_menu_keyboard(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=statement_menu_keyboard(), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------------------
# تایید بیانیه (فقط ادمین)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("stmt_approve:"))
async def cb_stmt_approve(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه بیانیه رو تایید کنه.", show_alert=True)
        return

    statement_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        statement = await session.get(CountryStatement, statement_id)
        if statement is None:
            await callback.answer("این بیانیه پیدا نشد.", show_alert=True)
            return

        error = await approve_statement(callback.bot, session, statement, callback.from_user.id)
        if error:
            await callback.answer(error, show_alert=True)
            return

        submitter = await session.get(User, statement.user_id)
        submitter_telegram_id = submitter.telegram_id if submitter else None
        await session.commit()

    original_text = callback.message.html_text or callback.message.text or ""
    try:
        await callback.message.edit_text(original_text + "\n\n✅ <b>تایید و منتشر شد.</b>", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("✅ بیانیه تایید و در کانال منتشر شد.", show_alert=True)

    if submitter_telegram_id is not None:
        try:
            await callback.bot.send_message(
                submitter_telegram_id, "🎉 بیانیه‌ات توسط ادمین تایید شد و در کانال منتشر شد!"
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# رد بیانیه با دلیل (فقط ادمین)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("stmt_reject:"))
async def cb_stmt_reject(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه بیانیه رو رد کنه.", show_alert=True)
        return

    statement_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        statement = await session.get(CountryStatement, statement_id)
        if statement is None or statement.status != "pending":
            await callback.answer("این بیانیه دیگه در انتظار بررسی نیست.", show_alert=True)
            return

    await state.update_data(
        statement_id=statement_id,
        review_chat_id=callback.message.chat.id,
        review_message_id=callback.message.message_id,
        review_text=callback.message.html_text or callback.message.text or "",
    )
    await callback.message.answer("دلیل رد این بیانیه رو بنویس (یا برای رد بدون دلیل «-» بفرست):")
    await state.set_state(RejectStatement.waiting_for_reason)
    await callback.answer()


@router.message(RejectStatement.waiting_for_reason)
async def process_reject_reason(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    reason = (message.text or "-").strip()
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        statement = await session.get(CountryStatement, data["statement_id"])
        if statement is None:
            await message.answer("این بیانیه دیگه پیدا نشد.")
            return

        error = reject_statement(statement, message.from_user.id, reason)
        if error:
            await message.answer(f"❌ {error}")
            return

        submitter = await session.get(User, statement.user_id)
        submitter_telegram_id = submitter.telegram_id if submitter else None
        await session.commit()

    try:
        await message.bot.edit_message_text(
            chat_id=data["review_chat_id"],
            message_id=data["review_message_id"],
            text=data["review_text"] + "\n\n❌ <b>رد شد.</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer("✅ رد بیانیه ثبت شد.")

    if submitter_telegram_id is not None:
        note = f"\nدلیل: {reason}" if reason and reason != "-" else ""
        try:
            await message.bot.send_message(
                submitter_telegram_id, f"❌ بیانیه‌ات توسط ادمین رد شد.{note}"
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# لیست بیانیه‌های در انتظار (برای ادمین، مثلاً اگه نوتیف اولیه از دست رفته باشه)
# ---------------------------------------------------------------------------

@router.message(Command("pendingstatements"))
async def cmd_pending_statements(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    async with get_session() as session:
        result = await session.execute(
            select(CountryStatement)
            .where(CountryStatement.status == "pending")
            .order_by(CountryStatement.created_at.asc())
        )
        pending = list(result.scalars().all())

        if not pending:
            await message.answer("📜 بیانیه‌ای در انتظار بررسی نیست.")
            return

        for statement in pending:
            country = await session.get(Country, statement.country_id)
            submitter = await session.get(User, statement.user_id)
            text = build_review_text(statement, country, submitter)
            await message.answer(text, reply_markup=review_keyboard(statement.id), parse_mode="HTML")
