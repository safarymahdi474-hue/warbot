from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from bot.config import settings
from bot.database.models import (
    AchievementType,
    AllianceResearchType,
    Base,
    BuildingType,
    Country,
    ItemType,
    MissionType,
    ResearchType,
    ShopItem,
    UnitType,
)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# لیست کشورها/جناح‌ها - حدود ۱۵۰ کشور واقعی + چندتا جناح تخیلی/تاریخی
DEFAULT_COUNTRIES = [
    # --- خاورمیانه و آسیای غربی ---
    {"name_fa": "ایران", "flag_emoji": "🇮🇷", "resource_bonus_percent": 5, "military_bonus_percent": 6},
    {"name_fa": "عراق", "flag_emoji": "🇮🇶", "resource_bonus_percent": 6, "military_bonus_percent": 4},
    {"name_fa": "عربستان سعودی", "flag_emoji": "🇸🇦", "resource_bonus_percent": 10, "military_bonus_percent": 6},
    {"name_fa": "امارات متحده عربی", "flag_emoji": "🇦🇪", "resource_bonus_percent": 9, "military_bonus_percent": 4},
    {"name_fa": "قطر", "flag_emoji": "🇶🇦", "resource_bonus_percent": 11, "military_bonus_percent": 2},
    {"name_fa": "کویت", "flag_emoji": "🇰🇼", "resource_bonus_percent": 10, "military_bonus_percent": 2},
    {"name_fa": "بحرین", "flag_emoji": "🇧🇭", "resource_bonus_percent": 6, "military_bonus_percent": 2},
    {"name_fa": "عمان", "flag_emoji": "🇴🇲", "resource_bonus_percent": 7, "military_bonus_percent": 3},
    {"name_fa": "یمن", "flag_emoji": "🇾🇪", "resource_bonus_percent": 3, "military_bonus_percent": 3},
    {"name_fa": "اردن", "flag_emoji": "🇯🇴", "resource_bonus_percent": 3, "military_bonus_percent": 4},
    {"name_fa": "لبنان", "flag_emoji": "🇱🇧", "resource_bonus_percent": 3, "military_bonus_percent": 2},
    {"name_fa": "سوریه", "flag_emoji": "🇸🇾", "resource_bonus_percent": 3, "military_bonus_percent": 3},
    {"name_fa": "فلسطین", "flag_emoji": "🇵🇸", "resource_bonus_percent": 2, "military_bonus_percent": 2},
    {"name_fa": "اسرائیل", "flag_emoji": "🇮🇱", "resource_bonus_percent": 4, "military_bonus_percent": 10},
    {"name_fa": "ترکیه", "flag_emoji": "🇹🇷", "resource_bonus_percent": 5, "military_bonus_percent": 5},
    {"name_fa": "قبرس", "flag_emoji": "🇨🇾", "resource_bonus_percent": 3, "military_bonus_percent": 2},

    # --- آسیای جنوبی ---
    {"name_fa": "افغانستان", "flag_emoji": "🇦🇫", "resource_bonus_percent": 4, "military_bonus_percent": 3},
    {"name_fa": "پاکستان", "flag_emoji": "🇵🇰", "resource_bonus_percent": 5, "military_bonus_percent": 7},
    {"name_fa": "هند", "flag_emoji": "🇮🇳", "resource_bonus_percent": 8, "military_bonus_percent": 4},
    {"name_fa": "بنگلادش", "flag_emoji": "🇧🇩", "resource_bonus_percent": 6, "military_bonus_percent": 2},
    {"name_fa": "سریلانکا", "flag_emoji": "🇱🇰", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "نپال", "flag_emoji": "🇳🇵", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "بوتان", "flag_emoji": "🇧🇹", "resource_bonus_percent": 3, "military_bonus_percent": 1},
    {"name_fa": "مالدیو", "flag_emoji": "🇲🇻", "resource_bonus_percent": 2, "military_bonus_percent": 1},

    # --- شرق آسیا ---
    {"name_fa": "چین", "flag_emoji": "🇨🇳", "resource_bonus_percent": 10, "military_bonus_percent": 0},
    {"name_fa": "ژاپن", "flag_emoji": "🇯🇵", "resource_bonus_percent": 5, "military_bonus_percent": 7},
    {"name_fa": "کره جنوبی", "flag_emoji": "🇰🇷", "resource_bonus_percent": 3, "military_bonus_percent": 9},
    {"name_fa": "کره شمالی", "flag_emoji": "🇰🇵", "resource_bonus_percent": 2, "military_bonus_percent": 9},
    {"name_fa": "مغولستان", "flag_emoji": "🇲🇳", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "تایوان", "flag_emoji": "🇹🇼", "resource_bonus_percent": 4, "military_bonus_percent": 6},

    # --- جنوب شرق آسیا ---
    {"name_fa": "ویتنام", "flag_emoji": "🇻🇳", "resource_bonus_percent": 6, "military_bonus_percent": 5},
    {"name_fa": "لائوس", "flag_emoji": "🇱🇦", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "کامبوج", "flag_emoji": "🇰🇭", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "تایلند", "flag_emoji": "🇹🇭", "resource_bonus_percent": 6, "military_bonus_percent": 4},
    {"name_fa": "میانمار", "flag_emoji": "🇲🇲", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "مالزی", "flag_emoji": "🇲🇾", "resource_bonus_percent": 7, "military_bonus_percent": 3},
    {"name_fa": "سنگاپور", "flag_emoji": "🇸🇬", "resource_bonus_percent": 8, "military_bonus_percent": 4},
    {"name_fa": "اندونزی", "flag_emoji": "🇮🇩", "resource_bonus_percent": 8, "military_bonus_percent": 4},
    {"name_fa": "فیلیپین", "flag_emoji": "🇵🇭", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "برونئی", "flag_emoji": "🇧🇳", "resource_bonus_percent": 9, "military_bonus_percent": 1},
    {"name_fa": "تیمور شرقی", "flag_emoji": "🇹🇱", "resource_bonus_percent": 3, "military_bonus_percent": 1},

    # --- آسیای مرکزی و قفقاز ---
    {"name_fa": "قزاقستان", "flag_emoji": "🇰🇿", "resource_bonus_percent": 9, "military_bonus_percent": 3},
    {"name_fa": "ازبکستان", "flag_emoji": "🇺🇿", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "ترکمنستان", "flag_emoji": "🇹🇲", "resource_bonus_percent": 8, "military_bonus_percent": 2},
    {"name_fa": "تاجیکستان", "flag_emoji": "🇹🇯", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "قرقیزستان", "flag_emoji": "🇰🇬", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "آذربایجان", "flag_emoji": "🇦🇿", "resource_bonus_percent": 7, "military_bonus_percent": 4},
    {"name_fa": "ارمنستان", "flag_emoji": "🇦🇲", "resource_bonus_percent": 3, "military_bonus_percent": 3},
    {"name_fa": "گرجستان", "flag_emoji": "🇬🇪", "resource_bonus_percent": 4, "military_bonus_percent": 2},

    # --- اروپای شرقی و روسیه ---
    {"name_fa": "روسیه", "flag_emoji": "🇷🇺", "resource_bonus_percent": 0, "military_bonus_percent": 10},
    {"name_fa": "اوکراین", "flag_emoji": "🇺🇦", "resource_bonus_percent": 7, "military_bonus_percent": 5},
    {"name_fa": "بلاروس", "flag_emoji": "🇧🇾", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "مولداوی", "flag_emoji": "🇲🇩", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "لهستان", "flag_emoji": "🇵🇱", "resource_bonus_percent": 5, "military_bonus_percent": 6},

    # --- اروپای غربی ---
    {"name_fa": "آلمان", "flag_emoji": "🇩🇪", "resource_bonus_percent": 5, "military_bonus_percent": 5},
    {"name_fa": "فرانسه", "flag_emoji": "🇫🇷", "resource_bonus_percent": 4, "military_bonus_percent": 8},
    {"name_fa": "بریتانیا", "flag_emoji": "🇬🇧", "resource_bonus_percent": 3, "military_bonus_percent": 8},
    {"name_fa": "ایرلند", "flag_emoji": "🇮🇪", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "هلند", "flag_emoji": "🇳🇱", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "بلژیک", "flag_emoji": "🇧🇪", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "لوکزامبورگ", "flag_emoji": "🇱🇺", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "سوئیس", "flag_emoji": "🇨🇭", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "اتریش", "flag_emoji": "🇦🇹", "resource_bonus_percent": 4, "military_bonus_percent": 2},

    # --- اروپای جنوبی ---
    {"name_fa": "ایتالیا", "flag_emoji": "🇮🇹", "resource_bonus_percent": 4, "military_bonus_percent": 5},
    {"name_fa": "اسپانیا", "flag_emoji": "🇪🇸", "resource_bonus_percent": 5, "military_bonus_percent": 4},
    {"name_fa": "پرتغال", "flag_emoji": "🇵🇹", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "یونان", "flag_emoji": "🇬🇷", "resource_bonus_percent": 4, "military_bonus_percent": 4},
    {"name_fa": "مالت", "flag_emoji": "🇲🇹", "resource_bonus_percent": 3, "military_bonus_percent": 1},

    # --- اسکاندیناوی و بالتیک ---
    {"name_fa": "سوئد", "flag_emoji": "🇸🇪", "resource_bonus_percent": 5, "military_bonus_percent": 4},
    {"name_fa": "نروژ", "flag_emoji": "🇳🇴", "resource_bonus_percent": 8, "military_bonus_percent": 3},
    {"name_fa": "دانمارک", "flag_emoji": "🇩🇰", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "فنلاند", "flag_emoji": "🇫🇮", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "ایسلند", "flag_emoji": "🇮🇸", "resource_bonus_percent": 4, "military_bonus_percent": 0},
    {"name_fa": "استونی", "flag_emoji": "🇪🇪", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "لتونی", "flag_emoji": "🇱🇻", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "لیتوانی", "flag_emoji": "🇱🇹", "resource_bonus_percent": 4, "military_bonus_percent": 2},

    # --- اروپای مرکزی و بالکان ---
    {"name_fa": "چک", "flag_emoji": "🇨🇿", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "اسلواکی", "flag_emoji": "🇸🇰", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "مجارستان", "flag_emoji": "🇭🇺", "resource_bonus_percent": 5, "military_bonus_percent": 3},
    {"name_fa": "رومانی", "flag_emoji": "🇷🇴", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "بلغارستان", "flag_emoji": "🇧🇬", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "صربستان", "flag_emoji": "🇷🇸", "resource_bonus_percent": 5, "military_bonus_percent": 4},
    {"name_fa": "کرواسی", "flag_emoji": "🇭🇷", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "اسلوونی", "flag_emoji": "🇸🇮", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "بوسنی و هرزگوین", "flag_emoji": "🇧🇦", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "مونته‌نگرو", "flag_emoji": "🇲🇪", "resource_bonus_percent": 3, "military_bonus_percent": 1},
    {"name_fa": "مقدونیه شمالی", "flag_emoji": "🇲🇰", "resource_bonus_percent": 3, "military_bonus_percent": 1},
    {"name_fa": "آلبانی", "flag_emoji": "🇦🇱", "resource_bonus_percent": 3, "military_bonus_percent": 1},
    {"name_fa": "کوزوو", "flag_emoji": "🇽🇰", "resource_bonus_percent": 2, "military_bonus_percent": 1},

    # --- آفریقای شمالی ---
    {"name_fa": "مصر", "flag_emoji": "🇪🇬", "resource_bonus_percent": 6, "military_bonus_percent": 5},
    {"name_fa": "لیبی", "flag_emoji": "🇱🇾", "resource_bonus_percent": 8, "military_bonus_percent": 2},
    {"name_fa": "تونس", "flag_emoji": "🇹🇳", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "الجزایر", "flag_emoji": "🇩🇿", "resource_bonus_percent": 9, "military_bonus_percent": 5},
    {"name_fa": "مراکش", "flag_emoji": "🇲🇦", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "سودان", "flag_emoji": "🇸🇩", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "سودان جنوبی", "flag_emoji": "🇸🇸", "resource_bonus_percent": 5, "military_bonus_percent": 2},

    # --- شاخ آفریقا و شرق آفریقا ---
    {"name_fa": "اتیوپی", "flag_emoji": "🇪🇹", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "اریتره", "flag_emoji": "🇪🇷", "resource_bonus_percent": 3, "military_bonus_percent": 2},
    {"name_fa": "جیبوتی", "flag_emoji": "🇩🇯", "resource_bonus_percent": 3, "military_bonus_percent": 1},
    {"name_fa": "سومالی", "flag_emoji": "🇸🇴", "resource_bonus_percent": 3, "military_bonus_percent": 2},
    {"name_fa": "کنیا", "flag_emoji": "🇰🇪", "resource_bonus_percent": 6, "military_bonus_percent": 2},
    {"name_fa": "اوگاندا", "flag_emoji": "🇺🇬", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "تانزانیا", "flag_emoji": "🇹🇿", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "رواندا", "flag_emoji": "🇷🇼", "resource_bonus_percent": 4, "military_bonus_percent": 2},
    {"name_fa": "بروندی", "flag_emoji": "🇧🇮", "resource_bonus_percent": 3, "military_bonus_percent": 1},

    # --- غرب آفریقا ---
    {"name_fa": "نیجریه", "flag_emoji": "🇳🇬", "resource_bonus_percent": 8, "military_bonus_percent": 4},
    {"name_fa": "غنا", "flag_emoji": "🇬🇭", "resource_bonus_percent": 6, "military_bonus_percent": 2},
    {"name_fa": "سنگال", "flag_emoji": "🇸🇳", "resource_bonus_percent": 5, "military_bonus_percent": 1},
    {"name_fa": "مالی", "flag_emoji": "🇲🇱", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "نیجر", "flag_emoji": "🇳🇪", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "چاد", "flag_emoji": "🇹🇩", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "کامرون", "flag_emoji": "🇨🇲", "resource_bonus_percent": 6, "military_bonus_percent": 2},

    # --- جنوب و مرکز آفریقا ---
    {"name_fa": "آفریقای جنوبی", "flag_emoji": "🇿🇦", "resource_bonus_percent": 8, "military_bonus_percent": 5},
    {"name_fa": "زیمبابوه", "flag_emoji": "🇿🇼", "resource_bonus_percent": 5, "military_bonus_percent": 2},
    {"name_fa": "زامبیا", "flag_emoji": "🇿🇲", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "بوتسوانا", "flag_emoji": "🇧🇼", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "نامیبیا", "flag_emoji": "🇳🇦", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "آنگولا", "flag_emoji": "🇦🇴", "resource_bonus_percent": 8, "military_bonus_percent": 3},
    {"name_fa": "موزامبیک", "flag_emoji": "🇲🇿", "resource_bonus_percent": 5, "military_bonus_percent": 1},
    {"name_fa": "کنگو", "flag_emoji": "🇨🇩", "resource_bonus_percent": 9, "military_bonus_percent": 2},
    {"name_fa": "گابن", "flag_emoji": "🇬🇦", "resource_bonus_percent": 7, "military_bonus_percent": 1},

    # --- آمریکای شمالی ---
    {"name_fa": "آمریکا", "flag_emoji": "🇺🇸", "resource_bonus_percent": 0, "military_bonus_percent": 10},
    {"name_fa": "کانادا", "flag_emoji": "🇨🇦", "resource_bonus_percent": 9, "military_bonus_percent": 4},
    {"name_fa": "مکزیک", "flag_emoji": "🇲🇽", "resource_bonus_percent": 6, "military_bonus_percent": 3},
    {"name_fa": "گواتمالا", "flag_emoji": "🇬🇹", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "هندوراس", "flag_emoji": "🇭🇳", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "کوبا", "flag_emoji": "🇨🇺", "resource_bonus_percent": 4, "military_bonus_percent": 3},
    {"name_fa": "هائیتی", "flag_emoji": "🇭🇹", "resource_bonus_percent": 2, "military_bonus_percent": 1},
    {"name_fa": "جامائیکا", "flag_emoji": "🇯🇲", "resource_bonus_percent": 3, "military_bonus_percent": 1},

    # --- آمریکای جنوبی ---
    {"name_fa": "برزیل", "flag_emoji": "🇧🇷", "resource_bonus_percent": 10, "military_bonus_percent": 2},
    {"name_fa": "آرژانتین", "flag_emoji": "🇦🇷", "resource_bonus_percent": 8, "military_bonus_percent": 3},
    {"name_fa": "شیلی", "flag_emoji": "🇨🇱", "resource_bonus_percent": 7, "military_bonus_percent": 3},
    {"name_fa": "کلمبیا", "flag_emoji": "🇨🇴", "resource_bonus_percent": 7, "military_bonus_percent": 3},
    {"name_fa": "پرو", "flag_emoji": "🇵🇪", "resource_bonus_percent": 7, "military_bonus_percent": 2},
    {"name_fa": "ونزوئلا", "flag_emoji": "🇻🇪", "resource_bonus_percent": 9, "military_bonus_percent": 3},
    {"name_fa": "اکوادور", "flag_emoji": "🇪🇨", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "بولیوی", "flag_emoji": "🇧🇴", "resource_bonus_percent": 7, "military_bonus_percent": 1},
    {"name_fa": "پاراگوئه", "flag_emoji": "🇵🇾", "resource_bonus_percent": 6, "military_bonus_percent": 1},
    {"name_fa": "اروگوئه", "flag_emoji": "🇺🇾", "resource_bonus_percent": 5, "military_bonus_percent": 1},

    # --- اقیانوسیه ---
    {"name_fa": "استرالیا", "flag_emoji": "🇦🇺", "resource_bonus_percent": 8, "military_bonus_percent": 5},
    {"name_fa": "نیوزیلند", "flag_emoji": "🇳🇿", "resource_bonus_percent": 6, "military_bonus_percent": 2},
    {"name_fa": "فیجی", "flag_emoji": "🇫🇯", "resource_bonus_percent": 4, "military_bonus_percent": 1},
    {"name_fa": "پاپوآ گینه نو", "flag_emoji": "🇵🇬", "resource_bonus_percent": 5, "military_bonus_percent": 1},

    # --- جناح‌های تخیلی (بدون ارجاع به هیچ گروه واقعی) ---
    {"name_fa": "امپراتوری شمال", "flag_emoji": "🐺", "resource_bonus_percent": 2, "military_bonus_percent": 12},
    {"name_fa": "اتحادیه صحرا", "flag_emoji": "🐫", "resource_bonus_percent": 12, "military_bonus_percent": 2},
    {"name_fa": "فدراسیون یخبندان", "flag_emoji": "❄️", "resource_bonus_percent": 6, "military_bonus_percent": 6},
    {"name_fa": "کنفدراسیون جزایر آزاد", "flag_emoji": "🏝️", "resource_bonus_percent": 9, "military_bonus_percent": 3},

    # --- امپراتوری‌های تاریخی ---
    {"name_fa": "هخامنشیان", "flag_emoji": "🦁", "resource_bonus_percent": 7, "military_bonus_percent": 6},
    {"name_fa": "ساسانیان", "flag_emoji": "🔥", "resource_bonus_percent": 5, "military_bonus_percent": 8},
    {"name_fa": "امپراتوری عثمانی", "flag_emoji": "🌙", "resource_bonus_percent": 6, "military_bonus_percent": 7},
    {"name_fa": "امپراتوری روم", "flag_emoji": "🏛️", "resource_bonus_percent": 4, "military_bonus_percent": 10},
]

# لیست اولیه ساختمان‌های قابل ساخت - فاز ۲
DEFAULT_BUILDING_TYPES = [
    {
        "key": "farm",
        "name_fa": "مزرعه",
        "icon": "🌾",
        "produces": "food",
        "base_production_per_hour": 20,
        "storage_bonus_per_level": 0,
        "base_cost_gold": 100,
        "base_cost_iron": 0,
        "base_build_time_seconds": 60,
        "max_level": 20,
    },
    {
        "key": "iron_mine",
        "name_fa": "معدن آهن",
        "icon": "⛏️",
        "produces": "iron",
        "base_production_per_hour": 15,
        "storage_bonus_per_level": 0,
        "base_cost_gold": 150,
        "base_cost_iron": 0,
        "base_build_time_seconds": 90,
        "max_level": 20,
    },
    {
        "key": "oil_well",
        "name_fa": "چاه نفت",
        "icon": "🛢️",
        "produces": "oil",
        "base_production_per_hour": 10,
        "storage_bonus_per_level": 0,
        "base_cost_gold": 200,
        "base_cost_iron": 0,
        "base_build_time_seconds": 120,
        "max_level": 20,
    },
    {
        "key": "warehouse",
        "name_fa": "انبار",
        "icon": "📦",
        "produces": None,
        "base_production_per_hour": 0,
        "storage_bonus_per_level": 500,
        "base_cost_gold": 250,
        "base_cost_iron": 50,
        "base_build_time_seconds": 150,
        "max_level": 15,
    },
    {
        "key": "gold_mine",
        "name_fa": "معدن طلا",
        "icon": "🏦",
        "produces": "gold",
        "base_production_per_hour": 8,
        "storage_bonus_per_level": 0,
        "base_cost_gold": 300,
        "base_cost_iron": 60,
        "base_build_time_seconds": 100,
        "max_level": 20,
    },
    {
        "key": "uranium_mine",
        "name_fa": "معدن اورانیوم",
        "icon": "☢️",
        "produces": "uranium",
        "base_production_per_hour": 3,
        "storage_bonus_per_level": 0,
        "base_cost_gold": 800,
        "base_cost_iron": 200,
        "base_build_time_seconds": 240,
        "max_level": 15,
    },
]

# لیست اولیه‌ی انواع نیرو - فاز ۳
DEFAULT_UNIT_TYPES = [
    {
        "key": "soldier",
        "category": "soldier",
        "name_fa": "سرباز",
        "icon": "🪖",
        "base_attack": 5,
        "base_defense": 5,
        "cost_gold": 50,
        "cost_iron": 5,
        "cost_oil": 0,
        "train_seconds_per_unit": 20,
        "min_player_level": 1,
        "max_level": 10,
    },
    {
        "key": "tank",
        "category": "tank",
        "name_fa": "تانک",
        "icon": "🛡️",
        "base_attack": 40,
        "base_defense": 30,
        "cost_gold": 400,
        "cost_iron": 80,
        "cost_oil": 20,
        "train_seconds_per_unit": 90,
        "min_player_level": 3,
        "max_level": 10,
    },
    {
        "key": "plane",
        "category": "plane",
        "name_fa": "هواپیما",
        "icon": "✈️",
        "base_attack": 90,
        "base_defense": 40,
        "cost_gold": 900,
        "cost_iron": 120,
        "cost_oil": 80,
        "train_seconds_per_unit": 180,
        "min_player_level": 6,
        "max_level": 10,
    },
    {
        "key": "ship",
        "category": "ship",
        "name_fa": "کشتی",
        "icon": "🚢",
        "base_attack": 150,
        "base_defense": 100,
        "cost_gold": 1800,
        "cost_iron": 300,
        "cost_oil": 150,
        "train_seconds_per_unit": 300,
        "min_player_level": 10,
        "max_level": 10,
    },
    {
        "key": "bomber",
        "category": "plane",
        "name_fa": "بمب‌افکن",
        "icon": "💣",
        "base_attack": 260,
        "base_defense": 60,
        "cost_gold": 3200,
        "cost_iron": 450,
        "cost_oil": 300,
        "cost_uranium": 40,
        "train_seconds_per_unit": 420,
        "min_player_level": 14,
        "max_level": 10,
    },
    {
        "key": "special_forces",
        "category": "soldier",
        "name_fa": "نیروی ویژه",
        "icon": "🏹",
        "base_attack": 35,
        "base_defense": 15,
        "cost_gold": 250,
        "cost_iron": 40,
        "cost_oil": 10,
        "train_seconds_per_unit": 60,
        "min_player_level": 8,
        "max_level": 10,
    },
    {
        "key": "artillery",
        "category": "tank",
        "name_fa": "توپخانه",
        "icon": "🎯",
        "base_attack": 130,
        "base_defense": 50,
        "cost_gold": 1100,
        "cost_iron": 220,
        "cost_oil": 60,
        "train_seconds_per_unit": 200,
        "min_player_level": 9,
        "max_level": 10,
    },
    {
        "key": "helicopter",
        "category": "plane",
        "name_fa": "هلیکوپتر",
        "icon": "🚁",
        "base_attack": 120,
        "base_defense": 70,
        "cost_gold": 1300,
        "cost_iron": 180,
        "cost_oil": 130,
        "train_seconds_per_unit": 220,
        "min_player_level": 9,
        "max_level": 10,
    },
    {
        "key": "corvette",
        "category": "ship",
        "name_fa": "ناوچه",
        "icon": "🛥️",
        "base_attack": 100,
        "base_defense": 70,
        "cost_gold": 1200,
        "cost_iron": 200,
        "cost_oil": 100,
        "train_seconds_per_unit": 220,
        "min_player_level": 7,
        "max_level": 10,
    },
    {
        "key": "missile_launcher",
        "category": "tank",
        "name_fa": "موشک‌انداز",
        "icon": "🚀",
        "base_attack": 340,
        "base_defense": 90,
        "cost_gold": 4200,
        "cost_iron": 700,
        "cost_oil": 350,
        "cost_uranium": 90,
        "train_seconds_per_unit": 480,
        "min_player_level": 15,
        "max_level": 10,
    },
    {
        "key": "aircraft_carrier",
        "category": "ship",
        "name_fa": "ناو هواپیمابر",
        "icon": "🚢",
        "base_attack": 500,
        "base_defense": 350,
        "cost_gold": 8000,
        "cost_iron": 1400,
        "cost_oil": 900,
        "cost_uranium": 180,
        "train_seconds_per_unit": 700,
        "min_player_level": 18,
        "max_level": 10,
    },
]

# لیست اولیه‌ی تحقیقات - فاز ۳ + توسعه‌ی تکنولوژی (فاز جدید)
DEFAULT_RESEARCH_TYPES = [
    {
        "key": "advanced_weapons",
        "name_fa": "تسلیحات پیشرفته",
        "icon": "🗡️",
        "effect_type": "attack_percent",
        "effect_per_level": 3.0,
        "cost_gold": 500,
        "cost_iron": 100,
        "cost_oil": 0,
        "base_research_seconds": 300,
        "max_level": 10,
    },
    {
        "key": "advanced_armor",
        "name_fa": "زره پیشرفته",
        "icon": "🛡️",
        "effect_type": "defense_percent",
        "effect_per_level": 3.0,
        "cost_gold": 500,
        "cost_iron": 100,
        "cost_oil": 0,
        "base_research_seconds": 300,
        "max_level": 10,
    },
    {
        "key": "fast_training",
        "name_fa": "آموزش سریع",
        "icon": "⏱️",
        "effect_type": "training_speed_percent",
        "effect_per_level": 5.0,
        "cost_gold": 400,
        "cost_iron": 60,
        "cost_oil": 40,
        "base_research_seconds": 240,
        "max_level": 10,
    },
    # --- تحقیقات جدید (توسعه‌ی تکنولوژی) ---
    {
        "key": "fortifications",
        "name_fa": "استحکامات",
        "icon": "🧱",
        # کاهش درصد تلفات نیرو وقتی مدافعی (نه مهاجم) - در battle.py مصرف میشه
        "effect_type": "defense_unit_loss_reduction_percent",
        "effect_per_level": 4.0,
        "cost_gold": 550,
        "cost_iron": 120,
        "cost_oil": 0,
        "base_research_seconds": 320,
        "max_level": 10,
    },
    {
        "key": "military_medicine",
        "name_fa": "پزشکی نظامی",
        "icon": "🩹",
        # کاهش HP از دست‌رفته بعد از نبرد (چه برنده چه بازنده)
        "effect_type": "hp_loss_reduction_percent",
        "effect_per_level": 4.0,
        "cost_gold": 450,
        "cost_iron": 80,
        "cost_oil": 20,
        "base_research_seconds": 280,
        "max_level": 10,
    },
    {
        "key": "counter_espionage",
        "name_fa": "ضدجاسوسی",
        "icon": "🕶️",
        # کاهش شانس لو رفتن وقتی کسی ازت جاسوسی می‌کنه
        "effect_type": "spy_detection_reduction_percent",
        "effect_per_level": 6.0,
        "cost_gold": 400,
        "cost_iron": 50,
        "cost_oil": 30,
        "base_research_seconds": 260,
        "max_level": 10,
    },
    {
        "key": "loot_tactics",
        "name_fa": "تاکتیک غارت",
        "icon": "💰",
        # +درصد به درصد غارت PvP (وقتی مهاجمی و می‌بری)
        "effect_type": "loot_bonus_percent",
        "effect_per_level": 5.0,
        "cost_gold": 500,
        "cost_iron": 60,
        "cost_oil": 40,
        "base_research_seconds": 260,
        "max_level": 10,
    },
    {
        "key": "war_morale",
        "name_fa": "روحیه‌ی جنگی",
        "icon": "🎖️",
        # کاهش شدت اثر منفی رویداد «کمین» وقتی مهاجمی
        "effect_type": "ambush_resist_percent",
        "effect_per_level": 8.0,
        "cost_gold": 480,
        "cost_iron": 70,
        "cost_oil": 20,
        "base_research_seconds": 260,
        "max_level": 10,
    },
    {
        "key": "air_defense",
        "name_fa": "پدافند هوایی",
        "icon": "🛰️",
        # فقط سهم قدرت حمله‌ای که از هواپیمای حریف میاد رو کم می‌کنه
        "effect_type": "air_defense_percent",
        "effect_per_level": 8.0,
        "cost_gold": 600,
        "cost_iron": 100,
        "cost_oil": 60,
        "base_research_seconds": 340,
        "max_level": 10,
    },
    {
        "key": "combat_engineering",
        "name_fa": "مهندسی رزمی",
        "icon": "🔧",
        # کاهش زمان ساخت/ارتقای ساختمان‌ها
        "effect_type": "build_time_reduction_percent",
        "effect_per_level": 4.0,
        "cost_gold": 450,
        "cost_iron": 90,
        "cost_oil": 0,
        "base_research_seconds": 280,
        "max_level": 10,
    },
    {
        "key": "artillery_precision",
        "name_fa": "دقت توپخانه",
        "icon": "🎯",
        # شدت رویداد «ضربه‌ی بحرانی» رو (وقتی مهاجمی) بیشتر می‌کنه
        "effect_type": "critical_hit_boost_percent",
        "effect_per_level": 6.0,
        "cost_gold": 500,
        "cost_iron": 80,
        "cost_oil": 40,
        "base_research_seconds": 280,
        "max_level": 10,
    },
    {
        "key": "military_intelligence",
        "name_fa": "اطلاعات نظامی",
        "icon": "🕵️",
        # دقیق‌تر شدن تخمین قدرت هدف وقتی خودت جاسوسی می‌کنی (بازه‌ی خطا کمتر)
        "effect_type": "spy_accuracy_percent",
        "effect_per_level": 6.0,
        "cost_gold": 420,
        "cost_iron": 40,
        "cost_oil": 40,
        "base_research_seconds": 260,
        "max_level": 10,
    },
]

# لیست اولیه‌ی ماموریت‌ها - فاز ۵
DEFAULT_MISSION_TYPES = [
    # --- روزانه ---
    {
        "key": "daily_bot_battles",
        "scope": "daily",
        "name_fa": "۳ نبرد با ربات انجام بده",
        "icon": "🤖",
        "event_type": "bot_battle",
        "target_amount": 3,
        "reward_gold": 150,
        "reward_xp": 30,
    },
    {
        "key": "daily_pvp_battle",
        "scope": "daily",
        "name_fa": "۱ نبرد PvP انجام بده",
        "icon": "⚔️",
        "event_type": "pvp_battle",
        "target_amount": 1,
        "reward_gold": 200,
        "reward_xp": 40,
    },
    {
        "key": "daily_train_units",
        "scope": "daily",
        "name_fa": "۱۰ نیرو آموزش بده",
        "icon": "🪖",
        "event_type": "train_units",
        "target_amount": 10,
        "reward_gold": 120,
        "reward_iron": 30,
    },
    {
        "key": "daily_upgrade_building",
        "scope": "daily",
        "name_fa": "یک ساختمان بساز/ارتقا بده",
        "icon": "🏗️",
        "event_type": "upgrade_building",
        "target_amount": 1,
        "reward_gold": 100,
        "reward_food": 50,
    },
    # --- هفتگی ---
    {
        "key": "weekly_win_battles",
        "scope": "weekly",
        "name_fa": "۱۰ نبرد رو ببر",
        "icon": "🏆",
        "event_type": "battle_win",
        "target_amount": 10,
        "reward_gold": 1200,
        "reward_xp": 250,
    },
    {
        "key": "weekly_train_units",
        "scope": "weekly",
        "name_fa": "۵۰ نیرو آموزش بده",
        "icon": "🪖",
        "event_type": "train_units",
        "target_amount": 50,
        "reward_gold": 900,
        "reward_iron": 150,
        "reward_oil": 100,
    },
    {
        "key": "weekly_research",
        "scope": "weekly",
        "name_fa": "یک تحقیق رو ارتقا بده",
        "icon": "🔬",
        "event_type": "research_upgrade",
        "target_amount": 1,
        "reward_gold": 700,
        "reward_xp": 100,
    },
]

# لیست اولیه‌ی آیتم‌ها - فاز ۷
DEFAULT_ITEM_TYPES = [
    {
        "key": "energy_potion",
        "name_fa": "معجون انرژی",
        "icon": "⚡",
        "description": "بلافاصله ۵۰ انرژی برمی‌گردونه.",
        "effect_type": "energy",
        "effect_value": 50,
        "duration_minutes": 0,
        "tradeable": True,
    },
    {
        "key": "medkit",
        "name_fa": "جعبه کمک‌های اولیه",
        "icon": "❤️",
        "description": "بلافاصله ۵۰ HP ترمیم می‌کنه.",
        "effect_type": "hp",
        "effect_value": 50,
        "duration_minutes": 0,
        "tradeable": True,
    },
    {
        "key": "attack_scroll",
        "name_fa": "طلسم حمله",
        "icon": "🗡️",
        "description": "به مدت ۱ ساعت ۲۰٪ به قدرت حمله‌ات اضافه می‌کنه.",
        "effect_type": "attack_percent",
        "effect_value": 20,
        "duration_minutes": 60,
        "tradeable": True,
    },
    {
        "key": "defense_scroll",
        "name_fa": "طلسم دفاع",
        "icon": "🛡️",
        "description": "به مدت ۱ ساعت ۲۰٪ به قدرت دفاعت اضافه می‌کنه.",
        "effect_type": "defense_percent",
        "effect_value": 20,
        "duration_minutes": 60,
        "tradeable": True,
    },
    {
        "key": "loot_crate",
        "name_fa": "جعبه غنیمت",
        "icon": "🎁",
        "description": "با باز کردنش مقداری منابع تصادفی می‌گیری.",
        "effect_type": "random_resources",
        "effect_value": 0,
        "duration_minutes": 0,
        "tradeable": True,
    },
]

# لیست اولیه‌ی دستاوردها - فاز ۸
DEFAULT_ACHIEVEMENT_TYPES = [
    {
        "key": "reach_level_5",
        "name_fa": "اولین قدم",
        "icon": "🥉",
        "description": "به سطح ۵ برس.",
        "condition_field": "level",
        "condition_value": 5,
        "reward_gold": 300,
        "reward_xp": 0,
    },
    {
        "key": "reach_level_15",
        "name_fa": "فرمانده باتجربه",
        "icon": "🥈",
        "description": "به سطح ۱۵ برس.",
        "condition_field": "level",
        "condition_value": 15,
        "reward_gold": 1500,
        "reward_xp": 0,
    },
    {
        "key": "win_10_battles",
        "name_fa": "جنگجو",
        "icon": "⚔️",
        "description": "۱۰ نبرد رو ببر.",
        "condition_field": "battles_won_total",
        "condition_value": 10,
        "reward_gold": 500,
        "reward_xp": 100,
    },
    {
        "key": "win_50_battles",
        "name_fa": "فاتح",
        "icon": "🏆",
        "description": "۵۰ نبرد رو ببر.",
        "condition_field": "battles_won_total",
        "condition_value": 50,
        "reward_gold": 3000,
        "reward_xp": 500,
    },
    {
        "key": "upgrade_5_buildings",
        "name_fa": "معمار",
        "icon": "🏗️",
        "description": "۵ بار ساختمان بساز یا ارتقا بده.",
        "condition_field": "buildings_upgraded_total",
        "condition_value": 5,
        "reward_gold": 400,
        "reward_xp": 50,
    },
    {
        "key": "trade_5_times",
        "name_fa": "تاجر",
        "icon": "💼",
        "description": "۵ بار در بازار معامله کن (خرید یا فروش).",
        "condition_field": "market_trades_total",
        "condition_value": 5,
        "reward_gold": 400,
        "reward_xp": 50,
    },
]

# لیست اولیه‌ی تحقیقات اتحادی - سرمایه‌گذاری رهبر از خزانه‌ی اتحاد، اثر روی همه‌ی اعضا
DEFAULT_ALLIANCE_RESEARCH_TYPES = [
    {
        "key": "military_academy",
        "name_fa": "آکادمی نظامی اتحاد",
        "icon": "🏛️",
        # +درصد حمله برای همه‌ی اعضا، فقط وقتی اتحاد در حال جنگه
        "effect_type": "alliance_attack_percent",
        "effect_per_level": 5.0,
        "cost_gold_per_level": 1500,
        "base_research_seconds": 600,
        "max_level": 5,
    },
]

# لیست اولیه‌ی فروشگاه - فاز ۹ (قیمت‌ها به تلگرام استارز/XTR)
# نکته: reward_item_key در init_db به ItemType.id واقعی تبدیل میشه (چون قبل از سید شدن آیتم‌ها اینجا id نداریم)
DEFAULT_SHOP_ITEMS = [
    {
        "key": "gold_pack_small",
        "name_fa": "بسته طلای کوچک",
        "icon": "💰",
        "description": "۲۰۰۰ طلا مستقیم به حسابت اضافه میشه.",
        "price_stars": 30,
        "reward_gold": 2000,
    },
    {
        "key": "gold_pack_large",
        "name_fa": "بسته طلای بزرگ",
        "icon": "💰",
        "description": "۱۲۰۰۰ طلا مستقیم به حسابت اضافه میشه.",
        "price_stars": 150,
        "reward_gold": 12000,
    },
    {
        "key": "coin_pack_small",
        "name_fa": "بسته سکه کوچک",
        "icon": "🪙",
        "description": "۱۰۰ سکه پرمیوم می‌گیری.",
        "price_stars": 50,
        "reward_coins": 100,
    },
    {
        "key": "energy_bundle",
        "name_fa": "بسته ۵ معجون انرژی",
        "icon": "⚡",
        "description": "۵ عدد معجون انرژی به اینونتوریت اضافه میشه.",
        "price_stars": 40,
        "reward_item_key": "energy_potion",
        "reward_item_quantity": 5,
    },
    {
        "key": "war_bundle",
        "name_fa": "بسته جنگی",
        "icon": "⚔️",
        "description": "۳ عدد طلسم حمله به اینونتوریت اضافه میشه.",
        "price_stars": 80,
        "reward_item_key": "attack_scroll",
        "reward_item_quantity": 3,
    },
]


async def _seed_missing_by_key(session, model, defaults: list[dict], key_field: str = "key") -> None:
    """
    برخلاف «فقط اگه جدول کاملاً خالیه سید کن»، این تابع فقط ردیف‌هایی که
    key‌شون از قبل نیست رو اضافه می‌کنه. این‌جوری وقتی به DEFAULT_* یه آیتم/
    تحقیق/ماموریت جدید اضافه می‌کنیم، بدون لمس داده‌های موجود (و بدون
    نیاز به خالی کردن دیتابیس) خودش برای همه‌ی دیتابیس‌های در حال اجرا ظاهر میشه.
    """
    result = await session.execute(select(model))
    existing_keys = {getattr(row, key_field) for row in result.scalars().all()}
    for data in defaults:
        if data[key_field] not in existing_keys:
            session.add(model(**data))


async def init_db() -> None:
    """جدول‌ها رو می‌سازه و اگه چیز جدیدی به لیست‌های پیش‌فرض اضافه شده بود، سیدش می‌کنه."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(Country))
        existing_countries = list(result.scalars().all())
        existing_country_names = {c.name_fa for c in existing_countries}
        for c in DEFAULT_COUNTRIES:
            if c["name_fa"] not in existing_country_names:
                session.add(Country(**c))

        await _seed_missing_by_key(session, BuildingType, DEFAULT_BUILDING_TYPES)
        await _seed_missing_by_key(session, UnitType, DEFAULT_UNIT_TYPES)
        await _seed_missing_by_key(session, ResearchType, DEFAULT_RESEARCH_TYPES)
        await _seed_missing_by_key(session, MissionType, DEFAULT_MISSION_TYPES)
        await _seed_missing_by_key(session, ItemType, DEFAULT_ITEM_TYPES)
        await _seed_missing_by_key(session, AchievementType, DEFAULT_ACHIEVEMENT_TYPES)
        await _seed_missing_by_key(session, AllianceResearchType, DEFAULT_ALLIANCE_RESEARCH_TYPES)

        # ShopItem قبل از سید شدن نیاز داره reward_item_key رو به id واقعی ItemType تبدیل کنه
        result = await session.execute(select(ShopItem))
        existing_shop_keys = {row.key for row in result.scalars().all()}
        if any(s["key"] not in existing_shop_keys for s in DEFAULT_SHOP_ITEMS):
            result_items = await session.execute(select(ItemType))
            item_type_by_key = {it.key: it.id for it in result_items.scalars().all()}
            for s in DEFAULT_SHOP_ITEMS:
                if s["key"] in existing_shop_keys:
                    continue
                data = dict(s)
                item_key = data.pop("reward_item_key", None)
                if item_key is not None:
                    data["reward_item_type_id"] = item_type_by_key.get(item_key)
                session.add(ShopItem(**data))

        await session.commit()


def get_session() -> AsyncSession:
    return async_session()
