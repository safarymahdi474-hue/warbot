from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import User
from bot.utils.giftcode import redeem_gift_code

router = Router(name="giftcode")


@router.message(Command("redeem"))
async def cmd_redeem(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip()
    if not code:
        await message.answer(
            "فرمت درست: <code>/redeem کد_هدیه</code>\nمثال: <code>/redeem ABCD1234</code>",
            parse_mode="HTML",
        )
        return

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        if user is None:
            await message.answer("هنوز ثبت‌نام نکردی! دستور /start رو بزن.")
            return

        gold, error = await redeem_gift_code(session, user, code)
        if error:
            await message.answer(f"❌ {error}")
            return

        await session.commit()

    await message.answer(f"🎁 کد هدیه فعال شد!\n💰 +{gold} طلا به حسابت اضافه شد.")
