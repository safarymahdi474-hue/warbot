from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.db import get_session
from bot.utils.context import room_condition, user_scope
from bot.database.models import PrivateMessage, User

router = Router(name="messages")

MAX_PM_LENGTH = 500


@router.callback_query(lambda c: c.data == "noop_inbox")
async def cb_inbox_hint(callback: CallbackQuery) -> None:
    await callback.answer("برای دیدن پیام‌هات دستور /inbox رو بزن، برای ارسال: /pm نیک‌نیم پیام", show_alert=True)


@router.message(Command("pm"))
async def cmd_pm(message: Message, command: CommandObject) -> None:
    args = (command.args or "").strip()
    if not args or " " not in args:
        await message.answer("فرمت درست: <code>/pm نیک‌نیم پیامت</code>", parse_mode="HTML")
        return

    nickname, text = args.split(" ", 1)
    text = text.strip()[:MAX_PM_LENGTH]
    if not text:
        await message.answer("پیامت خالیه.")
        return

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        sender = result.scalar_one_or_none()
        if sender is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        result = await session.execute(
            select(User).where(User.nickname == nickname, room_condition(User.room_id))
        )
        receiver = result.scalar_one_or_none()
        if receiver is None:
            await message.answer("کاربری با این نیک‌نیم توی همین روم/چت پیدا نشد.")
            return
        if receiver.id == sender.id:
            await message.answer("نمی‌تونی به خودت پیام بدی!")
            return

        pm = PrivateMessage(sender_id=sender.id, receiver_id=receiver.id, message=text)
        session.add(pm)
        await session.commit()

        should_notify = receiver.notifications_enabled
        receiver_telegram_id = receiver.telegram_id

    await message.answer("✅ پیام ارسال شد.")

    if should_notify:
        try:
            await message.bot.send_message(
                receiver_telegram_id,
                f"✉️ <b>پیام جدید از {sender.nickname}:</b>\n{text}\n\n"
                f"برای پاسخ: <code>/pm {sender.nickname} پیامت</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.message(Command("inbox"))
async def cmd_inbox(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        result = await session.execute(
            select(PrivateMessage)
            .options(selectinload(PrivateMessage.sender))
            .where(PrivateMessage.receiver_id == user.id)
            .order_by(PrivateMessage.created_at.desc())
            .limit(10)
        )
        messages = list(result.scalars().all())

        for m in messages:
            m.is_read = True
        await session.commit()

    if not messages:
        await message.answer("📭 صندوق پیامت خالیه.")
        return

    lines = ["📬 <b>۱۰ پیام اخیر</b>\n"]
    for m in messages:
        lines.append(f"<b>{m.sender.nickname}:</b> {m.message}")
    await message.answer("\n\n".join(lines), parse_mode="HTML")
