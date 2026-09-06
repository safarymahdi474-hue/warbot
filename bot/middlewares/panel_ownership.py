"""
قفل پنل مخصوص هر کاربر در گروه‌ها.

وقتی کسی تو یه گروه یه پنل (مثل /army یا /profile) باز می‌کنه، فقط خودش
باید بتونه دکمه‌های اون پیام رو بزنه؛ بقیه‌ی اعضای گروه اگه روی دکمه‌های
همون پیام بزنن، به‌جای اجرا شدن، یه هشدار می‌گیرن (ولی اکشن‌های خودشون -
یعنی وقتی خودشون /army رو باز کنن - عادی و مستقل کار می‌کنه).

معماری:
- PanelOwnershipRequestMiddleware: رو bot.session ثبت میشه و بعد از هر
  sendMessage/editMessageText/editMessageReplyMarkup موفق، مالکیت اون
  پیام (chat_id, message_id) رو تو حافظه ثبت می‌کنه.
- current_owner_id: مشخص می‌کنه این درخواست API داره بابت کدوم کاربر
  ارسال میشه (توسط دوتا میدلور پایین ست میشه).
- PanelOwnershipMessageMiddleware / PanelOwnershipCallbackMiddleware:
  قبل از هر Message/CallbackQuery صدا زده میشن؛ برای کال‌بک‌ها، اگه پیام
  مال کس دیگه‌ای باشه (فقط تو گروه، نه پیوی)، جلوی اجرای هندلر رو می‌گیرن.

محدودیت شناخته‌شده: مالکیت‌ها فقط تو حافظه (RAM) نگه داشته میشن، پس با
ری‌استارت ربات پاک میشن - تاثیرش فقط اینه که بعد از ری‌استارت، پیام‌های
قدیمی دوباره برای همه آزاد میشن تا صاحبشون دوباره باهاشون تعامل کنه.
"""

import contextvars

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Message, TelegramObject
from typing import Any, Awaitable, Callable

current_owner_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_owner_id", default=None
)

# (chat_id, message_id) -> owner_telegram_id -  فقط تو حافظه (کافیه، نیازی به دیتابیس نیست)
_panel_owners: dict[tuple[int, int], int] = {}


def get_panel_owner(chat_id: int, message_id: int) -> int | None:
    return _panel_owners.get((chat_id, message_id))


def _set_owner(chat_id: int, message_id: int, user_id: int, overwrite: bool) -> None:
    key = (chat_id, message_id)
    if overwrite or key not in _panel_owners:
        _panel_owners[key] = user_id


class PanelOwnershipRequestMiddleware(BaseRequestMiddleware):
    """رو bot.session.middleware(...) ثبت میشه - همه‌ی درخواست‌های API رو می‌بینه."""

    async def __call__(
        self,
        make_request: Callable[[Any, TelegramMethod], Awaitable[Any]],
        bot: Any,
        method: TelegramMethod,
    ) -> Any:
        result = await make_request(bot, method)

        owner = current_owner_id.get()
        if owner is None:
            return result

        try:
            if isinstance(method, SendMessage) and result is not None:
                chat_id = result.chat.id
                message_id = result.message_id
                _set_owner(chat_id, message_id, owner, overwrite=True)
            elif isinstance(method, (EditMessageText, EditMessageReplyMarkup)):
                chat_id = getattr(method, "chat_id", None)
                message_id = getattr(method, "message_id", None)
                if chat_id is not None and message_id is not None:
                    _set_owner(chat_id, message_id, owner, overwrite=False)
        except Exception:
            pass  # ثبت مالکیت هیچ‌وقت نباید جلوی جواب دادن به کاربر رو بگیره

        return result


class PanelOwnershipMessageMiddleware(BaseMiddleware):
    """current_owner_id رو برای پیام‌های معمولی (تایپ‌شده) ست می‌کنه."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else None
        token = current_owner_id.set(user_id)
        try:
            return await handler(event, data)
        finally:
            current_owner_id.reset(token)


class PanelOwnershipCallbackMiddleware(BaseMiddleware):
    """
    قبل از اجرای هر کال‌بک: اگه پیام مال یه گروهه و قبلاً مالک ثبت‌شده‌ای
    داره که با فرستنده‌ی این کلیک یکی نیست، اجرای هندلر رو متوقف می‌کنه.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        message = event.message
        if message is not None and message.chat.type != "private":
            owner = get_panel_owner(message.chat.id, message.message_id)
            if owner is not None and owner != event.from_user.id:
                await event.answer(
                    "⛔️ این پنل مال تو نیست! برای باز کردن پنل خودت، دستور مربوطه رو خودت بزن.",
                    show_alert=True,
                )
                return None

        token = current_owner_id.set(event.from_user.id)
        try:
            return await handler(event, data)
        finally:
            current_owner_id.reset(token)
