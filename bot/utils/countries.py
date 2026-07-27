from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.utils.context import room_condition


async def get_taken_country_titles(session: AsyncSession) -> set[str]:
    """
    همه‌ی لقب/کشورهایی که همین الان توی همین روم (فضای بازی فعلی، بر اساس
    current_room_id.get()) توسط یه کاربر گرفته شدن. هر روم/پروفایل اصلی
    مستقله، پس یه لقب می‌تونه توی روم‌های مختلف توسط افراد متفاوتی گرفته
    بشه - فقط داخل یک روم منحصربه‌فرده.
    """
    result = await session.execute(
        select(User.country_title).where(
            room_condition(User.room_id),
            User.country_title.isnot(None),
        )
    )
    return {row[0] for row in result.all()}


async def is_title_taken(session: AsyncSession, title: str) -> bool:
    taken_titles = await get_taken_country_titles(session)
    return title.strip() in taken_titles
