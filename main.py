import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.database.db import init_db
from bot.handlers import (
    achievements,
    admin,
    alliance,
    battle,
    buildings,
    giftcode,
    inventory,
    market,
    messages,
    military,
    missions,
    profile,
    resources,
    rewards,
    room_settings,
    settings as settings_handler,
    shop,
    start,
    statements,
    support,
)
from bot.middlewares.ban_check import BanCheckMiddleware
from bot.middlewares.room_context import RoomContextMiddleware

logging.basicConfig(level=logging.INFO)


PLAYER_COMMANDS = [
    BotCommand(command="start", description="🎮 ثبت‌نام یا شروع مجدد"),
    BotCommand(command="profile", description="👤 پروفایل من"),
    BotCommand(command="resources", description="📦 منابع من"),
    BotCommand(command="buildings", description="🏗️ ساختمان‌ها"),
    BotCommand(command="army", description="⚔️ ارتش من"),
    BotCommand(command="research", description="🔬 تحقیق و توسعه"),
    BotCommand(command="attack", description="🗡️ حمله (بات یا PvP)"),
    BotCommand(command="reports", description="📜 گزارش نبردهای اخیر"),
    BotCommand(command="pvpseason", description="📅 رتبه‌بندی هفتگی PvP"),
    BotCommand(command="missions", description="🎯 ماموریت‌های روزانه و هفتگی"),
    BotCommand(command="rewards", description="🎁 صندوق روزانه، هدیه، گردونه شانس"),
    BotCommand(command="alliance", description="🏛️ مدیریت اتحاد"),
    BotCommand(command="asay", description="💬 پیام در چت اتحاد"),
    BotCommand(command="statement", description="📜 بیانیه ملی"),
    BotCommand(command="inventory", description="🎒 اینونتوری و مصرف آیتم"),
    BotCommand(command="market", description="🏪 بازار، صرافی و حراج"),
    BotCommand(command="leaderboard", description="🏆 جدول رتبه‌بندی"),
    BotCommand(command="achievements", description="🏅 دستاوردها"),
    BotCommand(command="shop", description="🛍️ فروشگاه (تلگرام استارز)"),
    BotCommand(command="pm", description="✉️ پیام خصوصی به بازیکن دیگه"),
    BotCommand(command="inbox", description="📬 صندوق پیام‌های خصوصی"),
    BotCommand(command="settings", description="⚙️ تنظیمات اعلان"),
    BotCommand(command="redeem", description="🎁 فعال‌سازی کد هدیه"),
    BotCommand(command="roomsettings", description="🔒 تنظیمات این گروه (ادمین گروه)"),
    BotCommand(command="support", description="🆘 ثبت درخواست پشتیبانی"),
    BotCommand(command="mytickets", description="🎫 تیکت‌های پشتیبانی من"),
]


async def set_bot_commands(bot: Bot) -> None:
    """
    لیست دستورها رو تو منوی «/» تلگرام (همون آیکون کنار کیبورد) ثبت می‌کنه.
    فقط دستورهای مخصوص بازیکن؛ دستورهای ادمین (/ban, /setprice, ...) عمداً
    اینجا نیستن تا برای کاربر عادی لو نرن - اونا فقط با تایپ مستقیم کار می‌کنن.
    """
    await bot.set_my_commands(PLAYER_COMMANDS)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await set_bot_commands(bot)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RoomContextMiddleware())
    dp.callback_query.middleware(RoomContextMiddleware())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(buildings.router)
    dp.include_router(resources.router)
    dp.include_router(military.router)
    dp.include_router(battle.router)
    dp.include_router(missions.router)
    dp.include_router(rewards.router)
    dp.include_router(alliance.router)
    dp.include_router(statements.router)
    dp.include_router(inventory.router)
    dp.include_router(market.router)
    dp.include_router(achievements.router)
    dp.include_router(shop.router)
    dp.include_router(messages.router)
    dp.include_router(settings_handler.router)
    dp.include_router(support.router)
    dp.include_router(giftcode.router)
    dp.include_router(room_settings.router)
    dp.include_router(admin.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
