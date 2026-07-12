import os
from dataclasses import dataclass


@dataclass
class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./warbot.db")

    # --- تنظیمات اقتصادی و بازی (فاز ۱) ---
    START_GOLD: int = 500
    START_COINS: int = 0  # سکه پرمیوم (خرید با پول واقعی) - فاز فروشگاه
    START_ENERGY: int = 100
    MAX_ENERGY: int = 100
    ENERGY_REGEN_PER_MINUTE: int = 1  # هر دقیقه چقدر انرژی برمی‌گرده
    START_HP: int = 100
    MAX_HP: int = 100
    START_LEVEL: int = 1
    XP_BASE_TO_NEXT_LEVEL: int = 100  # XP لازم برای لول ۲
    XP_GROWTH_FACTOR: float = 1.35  # هر لول چقدر سخت‌تر بشه

    # --- منابع و ساختمان (فاز ۲) ---
    BASE_RESOURCE_STORAGE: int = 1000  # سقف اولیه‌ی هر منبع (نفت/آهن/غذا) قبل از ساخت انبار
    RESOURCE_COST_GROWTH: float = 1.4  # هزینه‌ی ساخت/ارتقا هر لول چقدر بیشتر میشه
    BUILD_TIME_GROWTH: float = 1.25  # زمان ساخت هر لول چقدر بیشتر میشه

    # --- ارتش و تحقیقات (فاز ۳) ---
    UNIT_UPGRADE_STAT_BONUS_PER_LEVEL: float = 0.10  # هر لول ارتقای نیرو، ۱۰٪ به حمله/دفاع اضافه می‌کنه
    UNIT_UPGRADE_COST_GROWTH: float = 1.5
    UNIT_UPGRADE_TIME_GROWTH: float = 1.3
    UNIT_BASE_UPGRADE_SECONDS: int = 180

    RESEARCH_COST_GROWTH: float = 1.5
    RESEARCH_TIME_GROWTH: float = 1.3

    # --- نبرد (فاز ۴) ---
    ATTACK_ENERGY_COST: int = 15
    MIN_HP_PERCENT_TO_ATTACK: int = 20  # اگه HP کمتر از این درصد باشه، نمی‌تونی حمله کنی
    WINNER_HP_LOSS_PERCENT: int = 5
    LOSER_HP_LOSS_PERCENT: int = 15
    WINNER_UNIT_LOSS_PERCENT: float = 0.05
    LOSER_UNIT_LOSS_PERCENT: float = 0.15
    PVP_LOOT_PERCENT: int = 15  # چند درصد از منابع بازنده غارت میشه
    PVP_LEVEL_RANGE: int = 3  # فقط بازیکن‌های هم‌سطح (±) قابل حمله‌ان
    PVP_TARGETS_SHOWN: int = 5

    # --- ماموریت و جوایز (فاز ۵) ---
    DAILY_CHEST_GOLD_MIN: int = 100
    DAILY_CHEST_GOLD_MAX: int = 400
    DAILY_CHEST_XP: int = 20

    ONLINE_GIFT_COOLDOWN_HOURS: int = 4
    ONLINE_GIFT_GOLD: int = 80
    ONLINE_GIFT_ENERGY: int = 20

    WHEEL_COOLDOWN_HOURS: int = 24

    # --- اتحاد (فاز ۶) ---
    ALLIANCE_MEMBER_LIMIT: int = 20
    ALLIANCE_WAR_DURATION_HOURS: int = 24
    ALLIANCE_CHAT_HISTORY_LIMIT: int = 20
    ALLIANCE_CREATE_COST_GOLD: int = 2000

    # --- صرافی منابع (فروش/خرید آنی با ربات) ---
    EXCHANGE_SELL_PRICE_IRON: int = 8   # هر واحد آهن رو ربات چقدر می‌خره
    EXCHANGE_SELL_PRICE_OIL: int = 10
    EXCHANGE_SELL_PRICE_FOOD: int = 4
    EXCHANGE_BUY_MARKUP_PERCENT: int = 15  # قیمت خرید از ربات نسبت به قیمت فروش چقدر بالاتره

    # --- بازار، حراج و آیتم (فاز ۷) ---
    MARKET_TAX_PERCENT: int = 5  # درصدی که از فروش کم میشه (نه به فروشنده میره نه به خریدار)
    AUCTION_MIN_DURATION_HOURS: int = 1
    AUCTION_MAX_DURATION_HOURS: int = 48
    AUCTION_DEFAULT_DURATION_HOURS: int = 24
    AUCTION_MIN_BID_INCREMENT_PERCENT: int = 5

    # --- رفرال و دستاورد (فاز ۸) ---
    REFERRAL_MILESTONE_LEVEL: int = 5
    REFERRAL_MILESTONE_GOLD: int = 500
    LEADERBOARD_SIZE: int = 10

    # --- پنل مدیریت (فاز ۱۱) ---
    # آیدی عددی تلگرام ادمین‌ها، جدا شده با کاما، مثلا "111111,222222"
    ADMIN_TELEGRAM_IDS: str = os.getenv("ADMIN_TELEGRAM_IDS", "")

    # --- بیانیه ملی (فاز ۱۳) ---
    # آیدی عددی کانال بیانیه‌ها (کانالی که ربات توش ادمینه). برای کانال‌ها معمولاً
    # با -100 شروع میشه، مثلا "-1001234567890". اگه خالی/۰ باشه، تایید بیانیه غیرفعاله.
    STATEMENT_CHANNEL_ID: int = int(os.getenv("STATEMENT_CHANNEL_ID", "0") or "0")
    STATEMENT_COOLDOWN_HOURS: int = 6  # هر کاربر هر چند ساعت یک‌بار میتونه بیانیه جدید ثبت کنه
    STATEMENT_MIN_LENGTH: int = 10
    STATEMENT_MAX_LENGTH: int = 1000

    # --- عضویت اجباری (فاز ۱۴) ---
    # لیست کانال‌های عضویت اجباری، جدا شده با کاما. ربات باید توی همه‌ی این
    # کانال‌ها ادمین باشه تا بتونه عضویت رو چک کنه. دو فرمت پشتیبانی میشه:
    #   ۱) کانال عمومی:  @channel_username
    #   ۲) کانال خصوصی:  -1001234567890|https://t.me/+AbCdEfGhIjKlMnOp
    #      (chat_id عددی و لینک دعوت با | از هم جدا میشن، چون برای کانال
    #      خصوصی نمیشه لینک t.me رو خودکار از روی chat_id ساخت)
    # مثال کامل در .env:
    #   FORCE_JOIN_CHANNELS=@mychannel,-1001234567890|https://t.me/+AbCdEfGhIjKlMnOp
    FORCE_JOIN_CHANNELS: str = os.getenv("FORCE_JOIN_CHANNELS", "")

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.ADMIN_TELEGRAM_IDS.split(",") if x.strip().isdigit()}

    @property
    def force_join_channels(self) -> list[tuple[str, str]]:
        """
        خروجی: لیست (chat_id, invite_url) از روی FORCE_JOIN_CHANNELS.
        اگه متغیر خالی باشه، لیست خالی برمی‌گرده (فیچر غیرفعال).
        """
        result: list[tuple[str, str]] = []
        raw = self.FORCE_JOIN_CHANNELS.strip()
        if not raw:
            return result

        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            if "|" in item:
                chat_id, url = item.split("|", 1)
                chat_id, url = chat_id.strip(), url.strip()
            elif item.startswith("@"):
                chat_id = item
                url = f"https://t.me/{item[1:]}"
            else:
                # اگه فرمت نامعتبر بود (نه @username و نه chat_id|url)، رد میشه
                continue
            if chat_id and url:
                result.append((chat_id, url))
        return result


settings = Settings()
