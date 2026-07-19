from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Room


async def get_room(session: AsyncSession, room_id: int | None) -> Room | None:
    if room_id is None:
        return None
    return await session.get(Room, room_id)


async def is_privacy_mode_on(session: AsyncSession, room_id: int | None) -> bool:
    """تو چت خصوصی (room_id=None) هیچ‌وقت لو رفتنی وجود نداره، پس همیشه False."""
    room = await get_room(session, room_id)
    return bool(room and room.privacy_mode)


async def is_group_admin(bot: Bot, chat_id: int, user_telegram_id: int) -> bool:
    """چک زنده از خود تلگرام - آیا این کاربر ادمین/سازنده‌ی همین گروهه."""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_telegram_id)
    except Exception:
        return False
    return member.status in ("administrator", "creator")


async def deliver_sensitive_content(
    bot: Bot,
    room_id: int | None,
    chat_type: str,
    user_telegram_id: int,
    text: str,
    keyboard=None,
    parse_mode: str = "HTML",
) -> tuple[bool, str | None]:
    """
    اگه لازم باشه (حالت خصوصی روشن و توی یه گروهیم)، محتوا رو پیوی می‌فرسته.
    خودش یه سشن موقت برای چک کردن تنظیمات روم می‌سازه (نیازی به پاس دادن سشن نیست).
    خروجی: (sent_privately: bool, group_note: str|None)
    - sent_privately=True یعنی محتوا پیوی رفت؛ فراخواننده نباید متن اصلی رو تو گروه بفرسته.
    - group_note: پیامی که (در صورت لزوم) باید تو گروه نشون داده بشه به‌جای متن اصلی.
    """
    if chat_type == "private":
        return False, None

    from bot.database.db import get_session

    async with get_session() as session:
        privacy_on = await is_privacy_mode_on(session, room_id)

    if not privacy_on:
        return False, None

    try:
        await bot.send_message(user_telegram_id, text, reply_markup=keyboard, parse_mode=parse_mode)
        return True, "📬 این گروه حالت خصوصی داره؛ اطلاعاتت رو پیوی برات فرستادم تا لو نره."
    except Exception:
        return True, (
            "❌ نتونستم پیوی بفرستم (اول باید یه‌بار /start رو تو پیوی خود ربات بزنی)."
            " چون این گروه حالت خصوصیه، از نمایش اطلاعات تو گروه صرف‌نظر کردم."
        )
