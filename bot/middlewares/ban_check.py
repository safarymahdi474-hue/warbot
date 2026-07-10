from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from bot.database.db import get_session
from bot.database.models import BannedTelegramUser


class BanCheckMiddleware(BaseMiddleware):
    """
    قبل از اجرای هر هندلر، چک می‌کنه کاربر (بر اساس telegram_id واقعیش، نه یه
    پروفایل خاص توی یه روم) بن نشده باشه. /start همیشه اجازه داره (تا کاربر
    پیام بن رو ببینه)، همه‌چیز دیگه برای کاربر بن‌شده مسدود میشه.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id = None
        if isinstance(event, Message):
            telegram_id = event.from_user.id if event.from_user else None
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id if event.from_user else None

        if telegram_id is not None:
            async with get_session() as session:
                result = await session.execute(
                    select(BannedTelegramUser).where(BannedTelegramUser.telegram_id == telegram_id)
                )
                banned = result.scalar_one_or_none()

            if banned is not None:
                if isinstance(event, Message):
                    await event.answer("⛔️ حساب تو بن شده و نمی‌تونی از ربات استفاده کنی.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ حساب تو بن شده.", show_alert=True)
                return None

        return await handler(event, data)
