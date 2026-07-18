import asyncio

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import room_condition, user_scope
from bot.config import settings
from bot.database.models import AdminLog, Alliance, AllianceWar, BannedTelegramUser, BattleReport, Room, User
from bot.utils.admin import (
    ban_user,
    get_all_user_telegram_ids,
    get_recent_logs,
    get_server_stats,
    log_action,
    unban_user,
)
from bot.utils.game_settings import are_wars_enabled, set_wars_enabled
from bot.utils.giftcode import create_gift_code, deactivate_gift_code, get_recent_gift_codes
from bot.utils.referral import get_referral_leaderboard

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


def admin_panel_keyboard(wars_enabled: bool) -> InlineKeyboardMarkup:
    wars_label = "⏸️ توقف کامل جنگ‌ها" if wars_enabled else "▶️ باز کردن جنگ‌ها"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=wars_label, callback_data="toggle_wars")],
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_admin_panel")],
        ]
    )


def admin_panel_text(wars_enabled: bool) -> str:
    wars_status = "✅ فعال (اتحادها می‌تونن اعلام جنگ کنن)" if wars_enabled else "⛔️ متوقف‌شده توسط مدیریت"
    return (
        "🛠️ <b>پنل مدیریت</b>\n\n"
        "/ban نیک‌نیم دلیل — بن کردن کاربر\n"
        "/unban نیک‌نیم — آن‌بن کردن کاربر\n"
        "/broadcast متن — پیام همگانی به همه کاربران\n"
        "/serverstats — آمار کامل سرور\n"
        "/adminlogs — لاگ اقدامات اخیر\n"
        "/pendingstatements — بیانیه‌های در انتظار تایید\n"
        "/referrals — رتبه‌بندی بیشترین رفرال‌گیرها\n"
        "/creategift سکه تعداد_استفاده [کد_دلخواه] — ساخت کد هدیه\n"
        "/giftcodes — لیست کدهای هدیه اخیر\n"
        "/deactivategift کد — غیرفعال کردن یه کد هدیه\n\n"
        f"⚔️ وضعیت جنگ اتحادها: {wars_status}"
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return  # کاربر عادی - سکوت (پیام خطا نمیدیم که وجود پنل رو لو نده)

    async with get_session() as session:
        wars_enabled = await are_wars_enabled(session)

    await message.answer(
        admin_panel_text(wars_enabled),
        reply_markup=admin_panel_keyboard(wars_enabled),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "show_admin_panel")
async def cb_show_admin_panel(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return

    async with get_session() as session:
        wars_enabled = await are_wars_enabled(session)

    try:
        await callback.message.edit_text(
            admin_panel_text(wars_enabled),
            reply_markup=admin_panel_keyboard(wars_enabled),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            admin_panel_text(wars_enabled),
            reply_markup=admin_panel_keyboard(wars_enabled),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "toggle_wars")
async def cb_toggle_wars(callback: CallbackQuery) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("فقط ادمین بهش دسترسی داره.", show_alert=True)
        return

    async with get_session() as session:
        currently_enabled = await are_wars_enabled(session)
        new_state = not currently_enabled
        cancelled_count = await set_wars_enabled(session, new_state)
        await log_action(
            session,
            "toggle_wars",
            callback.from_user.id,
            None,
            f"جنگ‌ها {'فعال' if new_state else 'متوقف'} شد. {cancelled_count} جنگ فعال لغو شد."
            if not new_state
            else "جنگ‌ها دوباره فعال شد.",
        )
        await session.commit()

    if new_state:
        alert = "✅ اعلام جنگ دوباره فعال شد."
    else:
        alert = f"⏸️ همه‌ی جنگ‌ها متوقف شدن. {cancelled_count} جنگ فعال لغو شد. اعلام جنگ جدید هم بسته شد."
    await callback.answer(alert, show_alert=True)

    await cb_show_admin_panel(callback)


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
        "toggle_wars": "⚔️ تغییر وضعیت جنگ",
        "create_gift_code": "🎁 ساخت کد هدیه",
        "deactivate_gift_code": "🚫 غیرفعال‌سازی کد هدیه",
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


@router.message(Command("referrals"))
async def cmd_referrals(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    async with get_session() as session:
        leaderboard = await get_referral_leaderboard(session, limit=20)

    if not leaderboard:
        await message.answer("هنوز هیچ‌کس با کد معرف کسی ثبت‌نام نکرده.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["👥 <b>رتبه‌بندی رفرال‌گیرها</b> (کل ربات، همه‌ی روم‌ها)\n"]
    for i, (referrer, count) in enumerate(leaderboard):
        rank_icon = medals[i] if i < 3 else f"{i + 1}."
        room_note = "" if referrer.room_id is None else " (گروه)"
        lines.append(f"{rank_icon} {referrer.nickname}{room_note} — {count} رفرال")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("creategift"))
async def cmd_create_gift(message: Message, command: CommandObject) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    args = (command.args or "").strip().split()
    if len(args) < 2:
        await message.answer(
            "فرمت درست: <code>/creategift تعداد_سکه تعداد_دفعات_استفاده [کد_دلخواه]</code>\n"
            "مثال: <code>/creategift 500 100</code>\n"
            "اگه کد دلخواه ندی، خودکار یه کد تصادفی ساخته میشه.",
            parse_mode="HTML",
        )
        return

    try:
        coins_reward = int(args[0])
        max_uses = int(args[1])
    except ValueError:
        await message.answer("تعداد سکه و تعداد دفعات استفاده باید عدد باشن.")
        return

    custom_code = args[2] if len(args) >= 3 else None

    async with get_session() as session:
        gift_code = await create_gift_code(session, message.from_user.id, coins_reward, max_uses, custom_code)
        if isinstance(gift_code, str):
            await message.answer(f"❌ {gift_code}")
            return

        await log_action(
            session,
            "create_gift_code",
            message.from_user.id,
            None,
            f"کد {gift_code.code} — {coins_reward} سکه — قابل استفاده توسط {max_uses} نفر",
        )
        await session.commit()
        code_text = gift_code.code

    await message.answer(
        f"✅ کد هدیه ساخته شد!\n\n"
        f"🎁 کد: <code>{code_text}</code>\n"
        f"🪙 پاداش هر نفر: {coins_reward} سکه\n"
        f"👥 ظرفیت: {max_uses} نفر\n\n"
        f"کاربرا با <code>/redeem {code_text}</code> فعالش می‌کنن.",
        parse_mode="HTML",
    )


@router.message(Command("giftcodes"))
async def cmd_list_gift_codes(message: Message) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    async with get_session() as session:
        codes = await get_recent_gift_codes(session)

    if not codes:
        await message.answer("هنوز هیچ کد هدیه‌ای ساخته نشده.")
        return

    lines = ["🎁 <b>کدهای هدیه اخیر</b>\n"]
    for c in codes:
        is_exhausted = c.uses_count >= c.max_uses
        status = "⛔️ غیرفعال" if not c.active else ("🔴 تموم‌شده" if is_exhausted else "✅ فعال")
        lines.append(
            f"<code>{c.code}</code> — 🪙{c.coins_reward} — "
            f"{c.uses_count}/{c.max_uses} استفاده — {status}"
        )

    await message.answer("\n\n".join(lines), parse_mode="HTML")


@router.message(Command("deactivategift"))
async def cmd_deactivate_gift(message: Message, command: CommandObject) -> None:
    _, is_admin = await _require_admin(message.from_user.id)
    if not is_admin:
        return

    code = (command.args or "").strip()
    if not code:
        await message.answer("فرمت درست: <code>/deactivategift کد</code>", parse_mode="HTML")
        return

    async with get_session() as session:
        error = await deactivate_gift_code(session, code)
        if error:
            await message.answer(f"❌ {error}")
            return

        await log_action(session, "deactivate_gift_code", message.from_user.id, None, code.upper())
        await session.commit()

    await message.answer(f"✅ کد <code>{code.upper()}</code> غیرفعال شد.", parse_mode="HTML")
