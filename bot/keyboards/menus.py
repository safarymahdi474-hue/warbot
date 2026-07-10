from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Country, UserBuilding


def countries_keyboard(countries: list[Country]) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, c in enumerate(countries, start=1):
        row.append(
            InlineKeyboardButton(
                text=f"{c.flag_emoji} {c.name_fa}",
                callback_data=f"pick_country:{c.id}",
            )
        )
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    منوی اصلی. هر فاز جدید که پیاده بشه، دکمه‌ی مربوطه (ارتش، ماموریت، اتحاد و ...) اضافه میشه.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 پروفایل من", callback_data="show_profile")],
            [
                InlineKeyboardButton(text="📦 منابع من", callback_data="show_resources"),
                InlineKeyboardButton(text="🏗️ ساختمان‌ها", callback_data="show_buildings"),
            ],
            [InlineKeyboardButton(text="⚔️ ارتش من", callback_data="show_army")],
            [InlineKeyboardButton(text="🗡️ حمله", callback_data="show_attack_menu")],
            [
                InlineKeyboardButton(text="🎯 ماموریت‌ها", callback_data="show_missions"),
                InlineKeyboardButton(text="🎁 جوایز", callback_data="show_rewards_menu"),
            ],
            [InlineKeyboardButton(text="🏛️ اتحاد", callback_data="show_alliance_menu")],
            [
                InlineKeyboardButton(text="🎒 اینونتوری", callback_data="show_inventory"),
                InlineKeyboardButton(text="🏪 بازار", callback_data="show_market_menu"),
            ],
            [
                InlineKeyboardButton(text="🏅 دستاوردها", callback_data="show_achievements"),
                InlineKeyboardButton(text="🏆 رتبه‌بندی", callback_data="show_leaderboard"),
            ],
            [InlineKeyboardButton(text="🛍️ فروشگاه", callback_data="show_shop")],
            [
                InlineKeyboardButton(text="📬 صندوق پیام", callback_data="noop_inbox"),
                InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="show_settings"),
            ],
        ]
    )


def buildings_keyboard(user_buildings: list[UserBuilding]) -> InlineKeyboardMarkup:
    rows = []
    for ub in user_buildings:
        bt = ub.building_type
        if ub.upgrade_finish_at is not None:
            label = f"{bt.icon} {bt.name_fa} ⏳ در حال ساخت..."
            rows.append([InlineKeyboardButton(text=label, callback_data="building_busy")])
        elif ub.level >= bt.max_level:
            label = f"{bt.icon} {bt.name_fa} (لول {ub.level} - MAX)"
            rows.append([InlineKeyboardButton(text=label, callback_data="building_max")])
        else:
            action = "ساخت" if ub.level == 0 else f"ارتقا به لول {ub.level + 1}"
            label = f"{bt.icon} {bt.name_fa} (لول {ub.level}) — {action}"
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"build_upgrade:{bt.id}")]
            )
    rows.append([InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="show_buildings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
