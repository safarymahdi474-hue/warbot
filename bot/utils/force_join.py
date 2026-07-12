from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import settings

FORCE_JOIN_TEXT = (
    "📢 <b>عضویت اجباری</b>\n\n"
    "قبل از شروع بازی، اول باید توی کانال‌های زیر عضو بشی.\n"
    "بعد از عضویت، دکمه‌ی «✅ عضو شدم، بررسی کن» رو بزن:"
)


async def get_unjoined_channels(bot: Bot, user_id: int) -> list[tuple[str, str]]:
    """
    چک می‌کنه کاربر عضو کدوم کانال‌های اجباری (از FORCE_JOIN_CHANNELS در .env) نیست.
    خروجی: لیست (chat_id, invite_url) از کانال‌هایی که هنوز عضو نشده.
    اگه FORCE_JOIN_CHANNELS خالی باشه، این تابع همیشه لیست خالی برمی‌گردونه
    (یعنی فیچر به‌صورت پیش‌فرض غیرفعاله).
    """
    unjoined: list[tuple[str, str]] = []
    for chat_id, url in settings.force_join_channels:
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
        rows.append([InlineKeyboardButton(text=label, url=url)])
    rows.append(
        [InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_force_join")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
