import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

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


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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
