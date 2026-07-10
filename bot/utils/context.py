import contextvars

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Room, User

# هر آپدیت تلگرام در یک asyncio task جدا پردازش میشه، پس ContextVar برای هر
# پیام/کال‌بک مقدار جدا و ایزوله داره - نیازی به پاس دادن room_id لای همه‌ی
# امضای توابع نیست؛ هر جای کد می‌تونه current_room_id.get() رو صدا بزنه.
current_room_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_room_id", default=None
)


async def resolve_room_id(session: AsyncSession, chat) -> int | None:
    """
    چت خصوصی -> None (پروفایل اصلی). گروه/سوپرگروه -> Room مربوطه (و اگه
    برای اولین باره، ساخته میشه).
    """
    if chat is None or chat.type == "private":
        return None

    result = await session.execute(select(Room).where(Room.telegram_chat_id == chat.id))
    room = result.scalar_one_or_none()
    if room is None:
        room = Room(telegram_chat_id=chat.id, title=(chat.title or "گروه")[:128])
        session.add(room)
        await session.flush()
    return room.id


def user_scope(telegram_id: int):
    """
    شرط‌های where برای پیدا کردن پروفایل درستِ یک کاربر تلگرامی، متناسب با
    روم فعلی (از current_room_id.get()). همه‌جا به‌جای
    `User.telegram_id == X` باید از `*user_scope(X)` استفاده بشه.
    """
    room_id = current_room_id.get()
    if room_id is None:
        return (User.telegram_id == telegram_id, User.room_id.is_(None))
    return (User.telegram_id == telegram_id, User.room_id == room_id)


def room_condition(room_id_column):
    """
    برای مدل‌های دیگه‌ای که room_id دارن (Alliance، MarketListing، AuctionListing، ...)
    یا برای فیلتر User.room_id در کوئری‌های غیر-telegram_id (مثل جستجوی نیک‌نیم).
    مثال: .where(room_condition(Alliance.room_id))
    """
    room_id = current_room_id.get()
    return room_id_column.is_(None) if room_id is None else room_id_column == room_id


def current_room() -> int | None:
    return current_room_id.get()
