from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.db import get_session
from bot.utils.context import current_room_id, resolve_room_id
from bot.utils.global_events import build_announcement, maybe_trigger_global_event


class RoomContextMiddleware(BaseMiddleware):
    """
    قبل از هر هندلر، تشخیص میده پیام/کال‌بک از یه چت خصوصیه یا یه گروه، و
    room_id مربوطه رو توی یه ContextVar ست می‌کنه تا کل کد (بدون نیاز به پاس
    دادن دستی) بدونه داره برای کدوم «فضای بازی» کوئری می‌زنه.

    همچنین چون کرون‌جاب نداریم، همین‌جا (که هر پیام/کال‌بک صداش می‌زنه) یه
    شانس کم برای شروع یه رویداد سراسری جدید (توفان شن/فصل جنگ) هم چک میشه.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        async with get_session() as session:
            room_id = await resolve_room_id(session, chat)
            new_event = await maybe_trigger_global_event(session, room_id)
            await session.commit()

        if new_event is not None and chat is not None:
            bot = data.get("bot")
            if bot is not None:
                try:
                    await bot.send_message(chat.id, build_announcement(new_event), parse_mode="HTML")
                except Exception:
                    pass

        token = current_room_id.set(room_id)
        try:
            return await handler(event, data)
        finally:
            current_room_id.reset(token)
