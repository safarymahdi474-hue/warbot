"""
سیستم عضویت اجباری - کاملاً از پنل ادمین مدیریت میشه، بدون هیچ وابستگی به
فایل .env. هر کانال یه ردیف تو جدول force_join_channels داره؛ می‌تونه دائمی
باشه یا بعد از N ساعت خودکار حذف بشه.

طراحی برای جلوگیری از باگ‌های قبلی:
- عنوان کانال موقع افزودن مستقیم از ادمین گرفته میشه (نه با صدا زدن API
  تلگرام که ممکنه بی‌دلیل fail کنه یا کند باشه).
- لینک دعوت همیشه نرمال‌سازی میشه، هرجور که تایپ بشه (@user, t.me/user,
  یوزرنیم خام، یا لینک کامل) - هیچ‌وقت به خاطر فرمت لینک رد نمیشه.
- چک عضویت با try/except جدا برای هر کانال انجام میشه؛ اگه یه کانال ارور
  بده، بقیه‌ی کانال‌ها همچنان درست چک میشن.
"""

from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import ForceJoinChannel

FORCE_JOIN_TEXT = (
    "📢 <b>عضویت اجباری</b>\n\n"
    "قبل از شروع بازی، اول باید توی کانال‌های زیر عضو بشی.\n"
    "بعد از عضویت، دکمه‌ی «✅ عضو شدم، بررسی کن» رو بزن:"
)


def normalize_invite_url(raw: str) -> str:
    """
    هرچی ادمین تایپ کنه رو به یه لینک قابل‌کلیک تبدیل می‌کنه:
    - لینک کامل (http/https) → دست‌نخورده می‌مونه.
    - t.me/... یا telegram.me/... → فقط https:// جلوش اضافه میشه.
    - @یوزرنیم یا یوزرنیم خام → https://t.me/یوزرنیم
    """
    raw = raw.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("t.me/") or raw.startswith("telegram.me/"):
        return f"https://{raw}"
    return f"https://t.me/{raw.lstrip('@')}"


async def _delete_expired(session: AsyncSession) -> None:
    now = datetime.utcnow()
    result = await session.execute(
        select(ForceJoinChannel).where(
            ForceJoinChannel.expires_at.isnot(None), ForceJoinChannel.expires_at <= now
        )
    )
    for row in result.scalars().all():
        await session.delete(row)
    await session.commit()


async def get_active_channels(session: AsyncSession) -> list[ForceJoinChannel]:
    """کانال‌های فعال فعلی (منقضی‌شده‌ها همین‌جا پاک‌سازی میشن، چون کرون‌جاب نداریم)."""
    await _delete_expired(session)
    result = await session.execute(select(ForceJoinChannel).order_by(ForceJoinChannel.created_at.asc()))
    return list(result.scalars().all())


async def has_active_channels(session: AsyncSession) -> bool:
    channels = await get_active_channels(session)
    return len(channels) > 0


async def get_unjoined_channels(
    bot: Bot, session: AsyncSession, user_id: int
) -> list[ForceJoinChannel]:
    """کانال‌های فعالی که این کاربر هنوز عضوشون نیست."""
    channels = await get_active_channels(session)
    unjoined: list[ForceJoinChannel] = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel.chat_id, user_id=user_id)
            is_member = member.status not in ("left", "kicked")
        except Exception:
            # اگه نتونستیم چک کنیم (ربات ادمین اون کانال نیست، آیدی اشتباهه و ...)
            # برای امنیت فرض می‌کنیم عضو نشده تا کاربر بدون عضویت رد نشه.
            is_member = False
        if not is_member:
            unjoined.append(channel)
    return unjoined


def build_force_join_keyboard(unjoined: list[ForceJoinChannel]) -> InlineKeyboardMarkup:
    rows = []
    for channel in unjoined:
        try:
            rows.append([InlineKeyboardButton(text=f"📢 عضویت در {channel.title}", url=channel.invite_url)])
        except Exception:
            continue  # اگه یه لینک به هر دلیلی نامعتبر بود، کل پیام خراب نشه
    rows.append(
        [InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_force_join")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# مدیریت کانال‌ها (فقط از پنل ادمین)
# ---------------------------------------------------------------------------

async def add_channel(
    session: AsyncSession,
    admin_telegram_id: int,
    chat_id: str,
    invite_url: str,
    title: str,
    hours: int | None,
) -> ForceJoinChannel | str:
    """hours=None یا ۰ یعنی دائمی. خروجی: ForceJoinChannel در صورت موفقیت، وگرنه پیام خطا."""
    chat_id = chat_id.strip()
    invite_url = normalize_invite_url(invite_url)
    title = title.strip()

    if not chat_id:
        return "آیدی کانال نمی‌تونه خالی باشه."
    if not title:
        return "اسم کانال نمی‌تونه خالی باشه."

    expires_at = datetime.utcnow() + timedelta(hours=hours) if hours and hours > 0 else None

    channel = ForceJoinChannel(
        chat_id=chat_id,
        invite_url=invite_url,
        title=title[:128],
        added_by_telegram_id=admin_telegram_id,
        expires_at=expires_at,
    )
    session.add(channel)
    await session.flush()
    return channel


async def remove_channel(session: AsyncSession, channel_id: int) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا."""
    channel = await session.get(ForceJoinChannel, channel_id)
    if channel is None:
        return "این کانال دیگه پیدا نشد."
    await session.delete(channel)
    return None


async def list_channels(session: AsyncSession) -> list[ForceJoinChannel]:
    return await get_active_channels(session)
