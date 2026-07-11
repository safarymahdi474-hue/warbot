from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Country, UserBuilding

# چون الان ۲۰۰ کشور/گروهک داریم، همه‌شون توی یه پیام جا نمیشن -> صفحه‌بندی
COUNTRIES_PER_PAGE = 8


def countries_keyboard(
    countries: list[Country], taken_country_ids: set[int], page: int = 0
) -> InlineKeyboardMarkup:
    """
    کیبورد صفحه‌بندی‌شده‌ی انتخاب کشور/گروهک.
    - کشورهایی که از قبل توسط یکی دیگه (توی همین روم) گرفته شدن با ✅ نشون داده میشن
      و قابل انتخاب نیستن (به‌جای pick_country به taken_country وصل میشن).
    - کشورهای آزاد عادی نمایش داده میشن و با pick_country:<id> قابل انتخابن.
    """
    total = len(countries)
    total_pages = max(1, (total + COUNTRIES_PER_PAGE - 1) // COUNTRIES_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * COUNTRIES_PER_PAGE
    page_items = countries[start : start + COUNTRIES_PER_PAGE]

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, c in enumerate(page_items, start=1):
        is_taken = c.id in taken_country_ids
        if is_taken:
            label = f"✅ {c.flag_emoji} {c.name_fa}"
            callback = "taken_country"
        else:
            label = f"{c.flag_emoji} {c.name_fa}"
            callback = f"pick_country:{c.id}"
        row.append(InlineKeyboardButton(text=label, callback_data=callback))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"country_page:{page - 1}"))
    nav_row.append(
        InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="country_page_noop")
    )
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"country_page:{page + 1}"))
    rows.append(nav_row)

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
