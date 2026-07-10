from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import SupportTicket, User

router = Router(name="support")

MAX_TICKET_LENGTH = 1000


@router.message(Command("support"))
async def cmd_support(message: Message, command: CommandObject) -> None:
    text = (command.args or "").strip()
    if not text:
        await message.answer(
            "برای ثبت درخواست پشتیبانی بنویس:\n<code>/support متن مشکلت</code>\n\n"
            "برای دیدن تیکت‌های قبلی: /mytickets",
            parse_mode="HTML",
        )
        return
    text = text[:MAX_TICKET_LENGTH]

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        ticket = SupportTicket(user_id=user.id, message=text, status="open")
        session.add(ticket)
        await session.commit()

    await message.answer("✅ تیکتت ثبت شد. تیم پشتیبانی به زودی بررسی می‌کنه.")


@router.callback_query(F.data == "show_support")
async def cb_show_support(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "🆘 برای ثبت درخواست پشتیبانی بنویس:\n<code>/support متن مشکلت</code>", parse_mode="HTML"
    )
    await callback.answer()


@router.message(Command("mytickets"))
async def cmd_my_tickets(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی!")
            return

        result = await session.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id)
            .order_by(SupportTicket.created_at.desc())
            .limit(5)
        )
        tickets = list(result.scalars().all())

    if not tickets:
        await message.answer("هیچ تیکتی ثبت نکردی.")
        return

    lines = ["🎫 <b>تیکت‌های اخیر تو</b>\n"]
    for t in tickets:
        status_icon = "🟢 پاسخ داده‌شده" if t.status == "closed" else "🟡 در انتظار بررسی"
        lines.append(f"{status_icon}\n📝 {t.message}")
        if t.admin_reply:
            lines.append(f"💬 <b>پاسخ پشتیبانی:</b> {t.admin_reply}")
    await message.answer("\n\n".join(lines), parse_mode="HTML")
