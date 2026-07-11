from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.utils.context import room_condition


async def get_taken_country_ids(session: AsyncSession) -> set[int]:
    """
    آی‌دی همه‌ی کشور/گروهک‌هایی که در همین روم (فضای بازی فعلی، بر اساس
    current_room_id.get()) از قبل توسط یک کاربر انتخاب شدن. هر روم/پروفایل
    اصلی مستقله، پس همون کشور می‌تونه توی روم‌های مختلف توسط افراد متفاوتی
    انتخاب بشه - فقط داخل یک روم منحصربه‌فرده.
    """
    result = await session.execute(
        select(User.country_id).where(
            room_condition(User.room_id),
            User.country_id.isnot(None),
        )
    )
    return {row[0] for row in result.all()}


async def is_country_taken(session: AsyncSession, country_id: int) -> bool:
    taken_ids = await get_taken_country_ids(session)
    return country_id in taken_ids
