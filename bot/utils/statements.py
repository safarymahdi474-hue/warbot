from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import Country, CountryStatement, User


async def get_last_statement(session: AsyncSession, user_id: int) -> CountryStatement | None:
    result = await session.execute(
        select(CountryStatement)
        .where(CountryStatement.user_id == user_id)
        .order_by(CountryStatement.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def can_submit_statement(session: AsyncSession, user_id: int) -> tuple[bool, timedelta | None]:
    """خروجی: (آیا میتونه بیانیه جدید ثبت کنه, چقدر باید صبر کنه اگه نمیتونه)."""
    last = await get_last_statement(session, user_id)
    if last is None:
        return True, None

    elapsed = datetime.utcnow() - last.created_at
    cooldown = timedelta(hours=settings.STATEMENT_COOLDOWN_HOURS)
    if elapsed >= cooldown:
        return True, None
    return False, cooldown - elapsed


def create_statement(user: User, text: str) -> CountryStatement | str:
    """فقط رکورد رو می‌سازه (باید session.add بشه)؛ خروجی رشته یعنی خطا."""
    text = text.strip()
    if len(text) < settings.STATEMENT_MIN_LENGTH:
        return f"بیانیه خیلی کوتاهه (حداقل {settings.STATEMENT_MIN_LENGTH} حرف)."
    if len(text) > settings.STATEMENT_MAX_LENGTH:
        return f"بیانیه خیلی بلنده (حداکثر {settings.STATEMENT_MAX_LENGTH} حرف)."
    if user.country_id is None:
        return "تو هنوز کشوری انتخاب نکردی."

    return CountryStatement(
        user_id=user.id,
        country_id=user.country_id,
        room_id=user.room_id,
        text=text,
        status="pending",
    )


def build_review_text(statement: CountryStatement, country: Country, submitter: User) -> str:
    room_note = "🏠 پروفایل اصلی (چت خصوصی)" if statement.room_id is None else "🏠 داخل یک گروه"
    return (
        "📜 <b>بیانیه جدید در انتظار تایید</b>\n\n"
        f"{country.flag_emoji} <b>{country.name_fa}</b>\n"
        f"👤 ثبت‌کننده: {submitter.nickname}\n"
        f"{room_note}\n\n"
        f"📝 متن:\n{statement.text}"
    )


def build_channel_text(statement: CountryStatement, country: Country) -> str:
    return f"📜 <b>بیانیه رسمی {country.flag_emoji} {country.name_fa}</b>\n\n{statement.text}"


async def approve_statement(
    bot: Bot, session: AsyncSession, statement: CountryStatement, admin_telegram_id: int
) -> str | None:
    """خروجی: None یعنی موفق، وگرنه پیام خطا برای نمایش به ادمین."""
    if statement.status != "pending":
        return "این بیانیه قبلاً بررسی شده."
    if not settings.STATEMENT_CHANNEL_ID:
        return "کانال بیانیه‌ها هنوز تنظیم نشده (STATEMENT_CHANNEL_ID رو در .env ست کن)."

    country = await session.get(Country, statement.country_id)
    sent = await bot.send_message(
        chat_id=settings.STATEMENT_CHANNEL_ID,
        text=build_channel_text(statement, country),
        parse_mode="HTML",
    )

    statement.status = "approved"
    statement.reviewed_by_telegram_id = admin_telegram_id
    statement.reviewed_at = datetime.utcnow()
    statement.channel_message_id = sent.message_id
    return None


def reject_statement(statement: CountryStatement, admin_telegram_id: int, reason: str) -> str | None:
    """خروجی: None یعنی موفق، وگرنه پیام خطا."""
    if statement.status != "pending":
        return "این بیانیه قبلاً بررسی شده."

    statement.status = "rejected"
    statement.reviewed_by_telegram_id = admin_telegram_id
    statement.reviewed_at = datetime.utcnow()
    reason = (reason or "").strip()
    statement.reject_reason = reason[:256] if reason and reason != "-" else None
    return None
