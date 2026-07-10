from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from bot.config import settings
from bot.database.models import (
    AchievementType,
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

# لیست اولیه کشورها/جناح‌ها - می‌تونی بعدا از پنل ادمین اضافه/ویرایش کنی
DEFAULT_COUNTRIES = [
    {"name_fa": "ایران", "flag_emoji": "🇮🇷", "resource_bonus_percent": 5, "military_bonus_percent": 0},
    {"name_fa": "روسیه", "flag_emoji": "🇷🇺", "resource_bonus_percent": 0, "military_bonus_percent": 10},
    {"name_fa": "آمریکا", "flag_emoji": "🇺🇸", "resource_bonus_percent": 0, "military_bonus_percent": 10},
    {"name_fa": "چین", "flag_emoji": "🇨🇳", "resource_bonus_percent": 10, "military_bonus_percent": 0},
    {"name_fa": "آلمان", "flag_emoji": "🇩🇪", "resource_bonus_percent": 5, "military_bonus_percent": 5},
    {"name_fa": "ترکیه", "flag_emoji": "🇹🇷", "resource_bonus_percent": 5, "military_bonus_percent": 5},
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
        "key": "artillery",
        "category": "tank",
        "name_fa": "توپخانه",
        "icon": "💣",
        "base_attack": 130,
        "base_defense": 20,
        "cost_gold": 1300,
        "cost_iron": 250,
        "cost_oil": 60,
        "train_seconds_per_unit": 220,
        "min_player_level": 8,
        "max_level": 10,
    },
    {
        "key": "drone",
        "category": "plane",
        "name_fa": "پهپاد شناسایی",
        "icon": "🛸",
        "base_attack": 60,
        "base_defense": 15,
        "cost_gold": 450,
        "cost_iron": 40,
        "cost_oil": 60,
        "train_seconds_per_unit": 60,
        "min_player_level": 4,
        "max_level": 10,
    },
    {
        "key": "special_forces",
        "category": "soldier",
        "name_fa": "نیروی ویژه",
        "icon": "🥷",
        "base_attack": 25,
        "base_defense": 25,
        "cost_gold": 250,
        "cost_iron": 30,
        "cost_oil": 10,
        "train_seconds_per_unit": 60,
        "min_player_level": 5,
        "max_level": 10,
    },
    {
        "key": "submarine",
        "category": "ship",
        "name_fa": "زیردریایی",
        "icon": "🌊",
        "base_attack": 220,
        "base_defense": 60,
        "cost_gold": 2500,
        "cost_iron": 400,
        "cost_oil": 300,
        "train_seconds_per_unit": 400,
        "min_player_level": 12,
        "max_level": 10,
    },
]

# لیست اولیه‌ی تحقیقات - فاز ۳
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


async def init_db() -> None:
    """جدول‌ها رو می‌سازه و اگه چیزی سید نشده بود، داده‌های پیش‌فرض رو اضافه می‌کنه."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        result = await session.execute(select(Country))
        if result.scalars().first() is None:
            for c in DEFAULT_COUNTRIES:
                session.add(Country(**c))

        result = await session.execute(select(BuildingType))
        if result.scalars().first() is None:
            for b in DEFAULT_BUILDING_TYPES:
                session.add(BuildingType(**b))

        result = await session.execute(select(UnitType))
        if result.scalars().first() is None:
            for u in DEFAULT_UNIT_TYPES:
                session.add(UnitType(**u))

        result = await session.execute(select(ResearchType))
        if result.scalars().first() is None:
            for r in DEFAULT_RESEARCH_TYPES:
                session.add(ResearchType(**r))

        result = await session.execute(select(MissionType))
        if result.scalars().first() is None:
            for m in DEFAULT_MISSION_TYPES:
                session.add(MissionType(**m))

        result = await session.execute(select(ItemType))
        if result.scalars().first() is None:
            for i in DEFAULT_ITEM_TYPES:
                session.add(ItemType(**i))

        result = await session.execute(select(AchievementType))
        if result.scalars().first() is None:
            for a in DEFAULT_ACHIEVEMENT_TYPES:
                session.add(AchievementType(**a))

        result = await session.execute(select(ShopItem))
        if result.scalars().first() is None:
            result_items = await session.execute(select(ItemType))
            item_type_by_key = {it.key: it.id for it in result_items.scalars().all()}
            for s in DEFAULT_SHOP_ITEMS:
                data = dict(s)
                item_key = data.pop("reward_item_key", None)
                if item_key is not None:
                    data["reward_item_type_id"] = item_type_by_key.get(item_key)
                session.add(ShopItem(**data))

        await session.commit()


def get_session() -> AsyncSession:
    return async_session()
