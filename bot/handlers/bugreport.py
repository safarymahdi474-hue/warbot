from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import settings
from bot.database.db import get_session
from bot.database.models import BugReport, User
from bot.utils.context import user_scope

router = Router(name="bugreport")

MAX_BUG_LENGTH = 1000

STATUS_LABELS = {
    "pending": "🟡 در انتظار بررسی",
    "rewarded": "🎁 جایزه گرفت",
    "rejected": "❌ رد شد",
}


class RewardBug(StatesGroup):
    waiting_for_amount = State()


class RejectBug(StatesGroup):
    waiting_for_reason = State()


def review_keyboard(bug_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎁 جایزه بده", callback_data=f"bug_reward:{bug_id}"),
                InlineKeyboardButton(text="❌ رد کن", callback_data=f"bug_reject:{bug_id}"),
            ]
        ]
    )


def build_review_text(bug: BugReport, reporter: User) -> str:
    return (
        "🐞 <b>گزارش باگ جدید</b>\n\n"
        f"👤 گزارش‌دهنده: {reporter.nickname}\n\n"
        f"📝 متن:\n{bug.message}"
    )


# ---------------------------------------------------------------------------
# ثبت گزارش باگ (بازیکن)
# ---------------------------------------------------------------------------

@router.message(Command("reportbug"))
async def cmd_report_bug(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer(
            "برای گزارش باگ بنویس:\n<code>/reportbug توضیح باگی که دیدی</code>\n\n"
            "برای دیدن گزارش‌های قبلیت: /mybugreports",
            parse_mode="HTML",
        )
        return
    text = text[:MAX_BUG_LENGTH]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی! دستور /start رو بزن.")
            return

        bug = BugReport(user_id=user.id, message=text, status="pending")
        session.add(bug)
        await session.flush()
        review_text = build_review_text(bug, user)
        bug_id = bug.id
        await session.commit()

    await message.answer("✅ گزارش باگت ثبت شد و برای بررسی ادمین ارسال شد. ممنون که کمک می‌کنی بازی بهتر بشه! 🙏")

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id, review_text, reply_markup=review_keyboard(bug_id), parse_mode="HTML"
            )
        except Exception:
            pass  # ادمین شاید هنوز چت خصوصی با ربات رو باز نکرده


@router.message(Command("mybugreports"))
async def cmd_my_bug_reports(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        result = await session.execute(
            select(BugReport)
            .where(BugReport.user_id == user.id)
            .order_by(BugReport.created_at.desc())
            .limit(10)
        )
        bugs = list(result.scalars().all())

    if not bugs:
        await message.answer("هنوز هیچ گزارش باگی نفرستادی.")
        return

    lines = ["🐞 <b>۱۰ گزارش اخیر تو</b>\n"]
    for b in bugs:
        status = STATUS_LABELS.get(b.status, b.status)
        line = f"{status}\n📝 {b.message}"
        if b.status == "rewarded" and b.reward_gold:
            line += f"\n💰 جایزه: {b.reward_gold} طلا"
        if b.status == "rejected" and b.admin_reply:
            line += f"\n💬 دلیل رد: {b.admin_reply}"
        lines.append(line)
    await message.answer("\n\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# بررسی گزارش (فقط ادمین) - جایزه یا رد
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bug_reward:"))
async def cb_bug_reward_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه این کارو بکنه.", show_alert=True)
        return

    bug_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        bug = await session.get(BugReport, bug_id)
        if bug is None or bug.status != "pending":
            await callback.answer("این گزارش دیگه در انتظار بررسی نیست.", show_alert=True)
            return

    await state.update_data(
        bug_id=bug_id,
        review_chat_id=callback.message.chat.id,
        review_message_id=callback.message.message_id,
        review_text=callback.message.html_text or callback.message.text or "",
    )
    await callback.message.answer("چقدر طلا به‌عنوان جایزه بدیم؟ (فقط عدد بفرست)")
    await state.set_state(RewardBug.waiting_for_amount)
    await callback.answer()


@router.message(RewardBug.waiting_for_amount)
async def process_bug_reward_amount(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    try:
        amount = int((message.text or "").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("یه عدد مثبت بفرست.")
        return

    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        bug = await session.get(BugReport, data["bug_id"])
        if bug is None or bug.status != "pending":
            await message.answer("این گزارش دیگه در انتظار بررسی نیست.")
            return

        reporter = await session.get(User, bug.user_id)
        if reporter is None:
            await message.answer("گزارش‌دهنده دیگه پیدا نشد.")
            return

        reporter.gold += amount
        bug.status = "rewarded"
        bug.reward_gold = amount
        bug.reviewed_by_telegram_id = message.from_user.id
        from datetime import datetime

        bug.reviewed_at = datetime.utcnow()

        reporter_telegram_id = reporter.telegram_id
        await session.commit()

    try:
        await message.bot.edit_message_text(
            chat_id=data["review_chat_id"],
            message_id=data["review_message_id"],
            text=data["review_text"] + f"\n\n🎁 <b>تایید و {amount} طلا جایزه داده شد.</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer("✅ جایزه داده شد.")

    try:
        await message.bot.send_message(
            reporter_telegram_id,
            f"🎉 باگی که گزارش داده بودی تایید شد!\n💰 +{amount} طلا به‌عنوان جایزه گرفتی. ممنون از کمکت! 🙏",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("bug_reject:"))
async def cb_bug_reject_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین می‌تونه این کارو بکنه.", show_alert=True)
        return

    bug_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        bug = await session.get(BugReport, bug_id)
        if bug is None or bug.status != "pending":
            await callback.answer("این گزارش دیگه در انتظار بررسی نیست.", show_alert=True)
            return

    await state.update_data(
        bug_id=bug_id,
        review_chat_id=callback.message.chat.id,
        review_message_id=callback.message.message_id,
        review_text=callback.message.html_text or callback.message.text or "",
    )
    await callback.message.answer("دلیل رد این گزارش رو بنویس (یا برای رد بدون دلیل «-» بفرست):")
    await state.set_state(RejectBug.waiting_for_reason)
    await callback.answer()


@router.message(RejectBug.waiting_for_reason)
async def process_bug_reject_reason(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    reason = (message.text or "-").strip()
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        bug = await session.get(BugReport, data["bug_id"])
        if bug is None or bug.status != "pending":
            await message.answer("این گزارش دیگه پیدا نشد یا قبلاً بررسی شده.")
            return

        reporter = await session.get(User, bug.user_id)
        reporter_telegram_id = reporter.telegram_id if reporter else None

        bug.status = "rejected"
        bug.admin_reply = reason[:256] if reason and reason != "-" else None
        bug.reviewed_by_telegram_id = message.from_user.id
        from datetime import datetime

        bug.reviewed_at = datetime.utcnow()
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

    await message.answer("✅ رد گزارش ثبت شد.")

    if reporter_telegram_id is not None:
        note = f"\nدلیل: {reason}" if reason and reason != "-" else ""
        try:
            await message.bot.send_message(reporter_telegram_id, f"❌ گزارش باگت بررسی شد ولی رد شد.{note}")
        except Exception:
            pass


@router.message(Command("pendingbugs"))
async def cmd_pending_bugs(message: Message) -> None:
    if message.from_user.id not in settings.admin_ids:
        return

    async with get_session() as session:
        result = await session.execute(
            select(BugReport)
            .options(selectinload(BugReport.user))
            .where(BugReport.status == "pending")
            .order_by(BugReport.created_at.asc())
        )
        pending = list(result.scalars().all())

        if not pending:
            await message.answer("🐞 گزارش باگی در انتظار بررسی نیست.")
            return

        for bug in pending:
            text = build_review_text(bug, bug.user)
            await message.answer(text, reply_markup=review_keyboard(bug.id), parse_mode="HTML")
