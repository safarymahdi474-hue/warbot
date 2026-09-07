from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models import ForceJoinChannel

FORCE_JOIN_TEXT = (
    "📢 <b>عضویت اجباری</b>\n\n"
    "قبل از شروع بازی، اول باید توی کانال‌های زیر عضو بشی.\n"
    "بعد از عضویت، دکمه‌ی «✅ عضو شدم، بررسی کن» رو بزن:"
)


async def _cleanup_expired(session: AsyncSession) -> None:
    now = datetime.utcnow()
    result = await session.execute(
        select(ForceJoinChannel).where(
            ForceJoinChannel.expires_at.isnot(None), ForceJoinChannel.expires_at <= now
        )
    )
    for row in result.scalars().all():
        await session.delete(row)
    await session.commit()


async def get_active_force_join_channels(session: AsyncSession) -> list[tuple[str, str]]:
    """
    خروجی: لیست (chat_id, invite_url) از کانال‌های ثابت (.env) + کانال‌های
    داخل دیتابیس که هنوز منقضی نشدن (منقضی‌شده‌ها همین‌جا پاک‌سازی میشن،
    چون کرون‌جاب نداریم).
    """
    await _cleanup_expired(session)

    channels: list[tuple[str, str]] = list(settings.force_join_channels)
    result = await session.execute(select(ForceJoinChannel))
    for row in result.scalars().all():
        channels.append((row.chat_id, row.invite_url))
    return channels


async def has_any_force_join_channels(session: AsyncSession) -> bool:
    channels = await get_active_force_join_channels(session)
    return len(channels) > 0


async def get_unjoined_channels(bot: Bot, session: AsyncSession, user_id: int) -> list[tuple[str, str]]:
    """
    چک می‌کنه کاربر عضو کدوم کانال‌های اجباری (ثابت + دیتابیسی) نیست.
    خروجی: لیست (chat_id, invite_url) از کانال‌هایی که هنوز عضو نشده.
    """
    channels = await get_active_force_join_channels(session)
    unjoined: list[tuple[str, str]] = []
    for chat_id, url in channels:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ("left", "kicked"):
                unjoined.append((chat_id, url))
        except Exception:
            # اگه نتونستیم چک کنیم (ربات ادمین اون کانال نیست، آیدی اشتباهه و ...)
            # برای امنیت فرض می‌کنیم عضو نشده تا کاربر بدون عضویت رد نشه.
            unjoined.append((chat_id, url))
    return unjoined


async def build_force_join_keyboard(bot: Bot, unjoined: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for i, (chat_id, url) in enumerate(unjoined, start=1):
        title = None
        try:
            chat = await bot.get_chat(chat_id)
            title = chat.title
        except Exception:
            pass
        label = f"📢 عضویت در {title}" if title else f"📢 عضویت در کانال {i}"
        try:
            rows.append([InlineKeyboardButton(text=label, url=url)])
        except Exception:
            # اگه لینک بازم به هر دلیلی نامعتبر بود، حداقل کل پیام خراب نشه
            continue
    rows.append(
        [InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_force_join")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# مدیریت کانال‌ها از پنل ادمین
# ---------------------------------------------------------------------------

def _normalize_invite_url(raw: str) -> str:
    """
    هرچی ادمین تایپ کنه رو به یه لینک قابل‌استفاده تبدیل می‌کنه:
    - اگه از قبل http/https داشت، همون‌جوری می‌مونه.
    - اگه با t.me/ یا telegram.me/ شروع بشه، فقط https:// جلوش اضافه میشه.
    - اگه با @ شروع بشه یا فقط یوزرنیم باشه، به https://t.me/<یوزرنیم> تبدیل میشه.
    """
    raw = raw.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("t.me/") or raw.startswith("telegram.me/"):
        return f"https://{raw}"
    username = raw.lstrip("@")
    return f"https://t.me/{username}"


async def add_force_join_channel(
    session: AsyncSession, admin_telegram_id: int, chat_id: str, invite_url: str, hours: int | None
) -> ForceJoinChannel | str:
    """hours=None یا ۰ یعنی دائمی. خروجی: ForceJoinChannel در صورت موفقیت، وگرنه پیام خطا."""
    chat_id = chat_id.strip()
    invite_url = invite_url.strip()
    if not chat_id or not invite_url:
        return "آیدی کانال و لینک دعوت نمی‌تونن خالی باشن."

    invite_url = _normalize_invite_url(invite_url)

    expires_at = None
    if hours and hours > 0:
        expires_at = datetime.utcnow() + timedelta(hours=hours)

    channel = ForceJoinChannel(
        chat_id=chat_id,
        invite_url=invite_url,
        title=None,
        added_by_telegram_id=admin_telegram_id,
        expires_at=expires_at,
    )
    session.add(channel)
    await session.flush()
    return channel


async def remove_force_join_channel(session: AsyncSession, chat_id: str) -> str | None:
    """None یعنی موفق، وگرنه پیام خطا."""
    result = await session.execute(select(ForceJoinChannel).where(ForceJoinChannel.chat_id == chat_id.strip()))
    rows = list(result.scalars().all())
    if not rows:
        return "کانالی با این آیدی تو لیست پیدا نشد."
    for row in rows:
        await session.delete(row)
    return None


async def list_force_join_channels(session: AsyncSession) -> list[ForceJoinChannel]:
    await _cleanup_expired(session)
    result = await session.execute(select(ForceJoinChannel).order_by(ForceJoinChannel.created_at.desc()))
    return list(result.scalars().all())
