import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import room_condition, user_scope
from bot.config import settings
from bot.database.models import User
from bot.utils.admin import (
    ban_user,
    get_all_user_telegram_ids,
    get_recent_logs,
    get_server_stats,
    log_action,
    unban_user,
)

router = Router(name="admin")


async def _require_admin(telegram_id: int) -> tuple[User | None, bool]:
    """
    مجوز ادمین بر اساس ADMIN_TELEGRAM_IDS در config چک میشه (نه فیلد is_admin
    توی یه پروفایل خاص)، چون یه ادمین ممکنه توی چند روم مختلف پروفایل جدا داشته باشه.
    """
    is_admin = telegram_id in settings.admin_ids
    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(telegram_id)))
        user = result.scalar_one_or_none()
    return user, is_admin


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return  # کاربر عادی - سکوت (پیام خطا نمیدیم که وجود پنل رو لو نده)

    await message.answer(
        "🛠️ <b>پنل مدیریت</b>\n\n"
        "/ban نیک‌نیم دلیل — بن کردن کاربر\n"
        "/unban نیک‌نیم — آن‌بن کردن کاربر\n"
        "/broadcast متن — پیام همگانی به همه کاربران\n"
        "/serverstats — آمار کامل سرور\n"
        "/adminlogs — لاگ اقدامات اخیر",
        parse_mode="HTML",
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject) -> None:
    admin, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    args = (command.args or "").strip()
    if not args or " " not in args:
        await message.answer("فرمت درست: <code>/ban نیک‌نیم دلیل</code>", parse_mode="HTML")
        return
    nickname, reason = args.split(" ", 1)

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.nickname == nickname, room_condition(User.room_id))
        )
        target = result.scalar_one_or_none()
        if target is None:
            await message.answer("کاربر پیدا نشد (فقط توی همین روم/چت جستجو میشه).")
            return
        if target.telegram_id in settings.admin_ids:
            await message.answer("نمی‌تونی ادمین رو بن کنی.")
            return

        await ban_user(session, message.from_user.id, target, reason)
        await session.commit()

    await message.answer(f"⛔️ {nickname} بن شد (سراسری، روی کل ربات). دلیل: {reason}")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject) -> None:
    admin, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    nickname = (command.args or "").strip()
    if not nickname:
        await message.answer("فرمت درست: <code>/unban نیک‌نیم</code>", parse_mode="HTML")
        return

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.nickname == nickname, room_condition(User.room_id))
        )
        target = result.scalar_one_or_none()
        if target is None:
            await message.answer("کاربر پیدا نشد (فقط توی همین روم/چت جستجو میشه).")
            return

        await unban_user(session, message.from_user.id, target)
        await session.commit()

    await message.answer(f"✅ {nickname} آن‌بن شد.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject) -> None:
    admin, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    text = (command.args or "").strip()
    if not text:
        await message.answer("فرمت درست: <code>/broadcast متن پیام</code>", parse_mode="HTML")
        return

    async with get_session() as session:
        telegram_ids = await get_all_user_telegram_ids(session)
        await log_action(session, "broadcast", message.from_user.id, None, text[:200])
        await session.commit()

    await message.answer(f"📣 در حال ارسال به {len(telegram_ids)} کاربر...")

    sent, failed = 0, 0
    broadcast_text = f"📢 <b>پیام همگانی</b>\n\n{text}"
    for tg_id in telegram_ids:
        try:
            await message.bot.send_message(tg_id, broadcast_text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        # جلوگیری از رسیدن به ریت‌لیمیت تلگرام (~۳۰ پیام در ثانیه)
        await asyncio.sleep(0.05)

    await message.answer(f"✅ ارسال تموم شد. موفق: {sent} | ناموفق: {failed}")


@router.message(Command("serverstats"))
async def cmd_server_stats(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    async with get_session() as session:
        stats = await get_server_stats(session)

    await message.answer(
        "📊 <b>آمار سرور</b>\n\n"
        f"👥 کل کاربران: {stats['total_users']}\n"
        f"⛔️ کاربران بن‌شده: {stats['banned_users']}\n"
        f"🏛️ کل اتحادها: {stats['total_alliances']}\n"
        f"⚔️ کل نبردها: {stats['total_battles']}\n"
        f"🔥 جنگ‌های فعال اتحاد: {stats['active_wars']}\n"
        f"⭐ بالاترین سطح: {stats['top_level']}",
        parse_mode="HTML",
    )


@router.message(Command("adminlogs"))
async def cmd_admin_logs(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    async with get_session() as session:
        logs = await get_recent_logs(session)

    if not logs:
        await message.answer("لاگی ثبت نشده.")
        return

    action_labels = {
        "ban": "⛔️ بن",
        "unban": "✅ آن‌بن",
        "broadcast": "📣 پیام همگانی",
        "promote_admin": "👑 ارتقای ادمین",
    }
    lines = ["📜 <b>لاگ اقدامات اخیر</b>\n"]
    for log in logs:
        label = action_labels.get(log.action_type, log.action_type)
        line = f"{label} — عامل: {log.actor_telegram_id}"
        if log.target_telegram_id:
            line += f" | هدف: {log.target_telegram_id}"
        if log.details:
            line += f"\n   {log.details}"
        line += f"\n   {log.created_at.strftime('%Y-%m-%d %H:%M')}"
        lines.append(line)

    await message.answer("\n\n".join(lines), parse_mode="HTML")
