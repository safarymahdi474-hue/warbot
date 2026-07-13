from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Country(Base):
    """
    کشور/جناح قابل انتخاب. لیست اولیه رو در db.py سید می‌کنیم.
    فازهای بعدی: هر کشور می‌تونه بونوس منابع/نظامی خاص خودش رو داشته باشه.
    """
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_fa: Mapped[str] = mapped_column(String(64), nullable=False)
    flag_emoji: Mapped[str] = mapped_column(String(8), default="🏳️")
    # بونوس‌های اختصاصی کشور (فاز نظامی/منابع بعدا استفاده میشه)
    resource_bonus_percent: Mapped[float] = mapped_column(Float, default=0.0)
    military_bonus_percent: Mapped[float] = mapped_column(Float, default=0.0)

    users: Mapped[list["User"]] = relationship(back_populates="country")


class User(Base):
    """
    پروفایل اصلی بازیکن. این هسته‌ی کل بازیه و بقیه‌ی جدول‌ها (ارتش، منابع،
    اتحاد، اینونتوری و ...) در فازهای بعدی به این جدول وصل می‌شن.
    """
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("telegram_id", "room_id", name="uq_users_telegram_room"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nickname: Mapped[str] = mapped_column(String(32), nullable=False)

    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"), nullable=True)
    country: Mapped["Country"] = relationship(back_populates="users")

    # --- پول و منابع پایه (فاز ۱: طلا. فاز منابع: نفت/آهن/غذا جدا میشن) ---
    gold: Mapped[int] = mapped_column(Integer, default=0)
    coins: Mapped[int] = mapped_column(Integer, default=0)  # سکه پرمیوم

    # --- انرژی ---
    energy: Mapped[int] = mapped_column(Integer, default=100)
    max_energy: Mapped[int] = mapped_column(Integer, default=100)
    last_energy_update: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- جان ---
    hp: Mapped[int] = mapped_column(Integer, default=100)
    max_hp: Mapped[int] = mapped_column(Integer, default=100)

    # --- لول و XP ---
    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)

    # --- معرفی دوستان ---
    referral_code: Mapped[str] = mapped_column(String(16), unique=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # --- مدیریت ---
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # --- منابع (فاز ۲) ---
    oil: Mapped[int] = mapped_column(Integer, default=0)
    iron: Mapped[int] = mapped_column(Integer, default=0)
    food: Mapped[int] = mapped_column(Integer, default=200)  # کمی غذای اولیه

    max_oil: Mapped[int] = mapped_column(Integer, default=1000)
    max_iron: Mapped[int] = mapped_column(Integer, default=1000)
    max_food: Mapped[int] = mapped_column(Integer, default=1000)

    last_resource_collect: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    buildings: Mapped[list["UserBuilding"]] = relationship(back_populates="user")
    units: Mapped[list["UserUnit"]] = relationship(back_populates="user")
    researches: Mapped[list["UserResearch"]] = relationship(back_populates="user")
    mission_progress: Mapped[list["UserMissionProgress"]] = relationship(back_populates="user")

    # --- جوایز و ماموریت (فاز ۵) ---
    last_daily_chest_claim: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_online_gift_claim: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_wheel_spin_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- اتحاد (فاز ۶) ---
    alliance_id: Mapped[int | None] = mapped_column(ForeignKey("alliances.id"), nullable=True)
    alliance_role: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'leader'|'officer'|'member'
    alliance: Mapped["Alliance"] = relationship(back_populates="members", foreign_keys=[alliance_id])

    # --- بازار و اینونتوری (فاز ۷) ---
    inventory: Mapped[list["UserInventory"]] = relationship(back_populates="user")
    active_boosts: Mapped[list["ActiveBoost"]] = relationship(back_populates="user")

    # --- آمار برای دستاورد و رفرال (فاز ۸) ---
    battles_won_total: Mapped[int] = mapped_column(Integer, default=0)
    buildings_upgraded_total: Mapped[int] = mapped_column(Integer, default=0)
    market_trades_total: Mapped[int] = mapped_column(Integer, default=0)
    referral_milestone_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- تنظیمات (فاز ۱۰) ---
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- روم گروهی (فاز ۱۲) ---
    # room_id=None یعنی پروفایل اصلی (چت خصوصی با ربات). هر گروه یه Room جدا داره
    # و همه‌چیز (منابع، ارتش، ساختمان، اتحاد، بازار و ...) بین روم‌ها کاملاً ایزوله‌ست.
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    room: Mapped["Room"] = relationship()


class BuildingType(Base):
    """
    نوع ساختمان (مثل مزرعه، معدن آهن، چاه نفت، انبار). این‌ها ثابت‌ان و در db.py
    سید می‌شن. هر کاربر برای هر نوع ساختمان یک ردیف UserBuilding داره.
    """
    __tablename__ = "building_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)  # 'farm', 'iron_mine', 'oil_well', 'warehouse'
    name_fa: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(8), default="🏗️")

    # اگه این ساختمان منبع تولید می‌کنه (مثلا 'food'، 'iron'، 'oil')، وگرنه None (مثل انبار)
    produces: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_production_per_hour: Mapped[int] = mapped_column(Integer, default=0)

    # انبار به‌جای تولید، سقف ذخیره‌سازی رو بالا می‌بره
    storage_bonus_per_level: Mapped[int] = mapped_column(Integer, default=0)

    base_cost_gold: Mapped[int] = mapped_column(Integer, default=0)
    base_cost_iron: Mapped[int] = mapped_column(Integer, default=0)
    base_build_time_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_level: Mapped[int] = mapped_column(Integer, default=20)

    user_buildings: Mapped[list["UserBuilding"]] = relationship(back_populates="building_type")


class UserBuilding(Base):
    """
    نمونه‌ی ساخته‌شده (یا نشده) یک ساختمان برای یک کاربر خاص.
    level=0 یعنی هنوز ساخته نشده.
    """
    __tablename__ = "user_buildings"
    __table_args__ = (
        UniqueConstraint("user_id", "building_type_id", name="uq_user_building_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    building_type_id: Mapped[int] = mapped_column(ForeignKey("building_types.id"))

    level: Mapped[int] = mapped_column(Integer, default=0)
    upgrade_finish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="buildings")
    building_type: Mapped["BuildingType"] = relationship(back_populates="user_buildings")


class UnitType(Base):
    """
    نوع نیروی نظامی (سرباز، تانک، هواپیما، کشتی). ثابت‌ان و در db.py سید می‌شن.
    """
    __tablename__ = "unit_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)  # 'soldier', 'tank', 'plane', 'ship'
    category: Mapped[str] = mapped_column(String(16))  # 'soldier' | 'tank' | 'plane' | 'ship'
    name_fa: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(8), default="⚔️")

    base_attack: Mapped[int] = mapped_column(Integer, default=1)
    base_defense: Mapped[int] = mapped_column(Integer, default=1)

    cost_gold: Mapped[int] = mapped_column(Integer, default=0)
    cost_iron: Mapped[int] = mapped_column(Integer, default=0)
    cost_oil: Mapped[int] = mapped_column(Integer, default=0)
    train_seconds_per_unit: Mapped[int] = mapped_column(Integer, default=10)

    min_player_level: Mapped[int] = mapped_column(Integer, default=1)
    max_level: Mapped[int] = mapped_column(Integer, default=10)  # سقف ارتقای نیرو (فاز ارتقای نیروها)

    user_units: Mapped[list["UserUnit"]] = relationship(back_populates="unit_type")


class UserUnit(Base):
    """
    تعداد نیروی هر نوع که کاربر مالکشه + سطح ارتقای اون نوع نیرو
    (ارتقا روی کل نیروهای همون نوع اثر می‌ذاره، نه یک واحد به‌تنهایی).
    """
    __tablename__ = "user_units"
    __table_args__ = (UniqueConstraint("user_id", "unit_type_id", name="uq_user_unit_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    unit_type_id: Mapped[int] = mapped_column(ForeignKey("unit_types.id"))

    quantity: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)  # لول ۱ = بدون ارتقا
    upgrade_finish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="units")
    unit_type: Mapped["UnitType"] = relationship(back_populates="user_units")


class TrainingOrder(Base):
    """صف آموزش/خرید نیرو. وقتی finish_at برسه، quantity به UserUnit اضافه میشه."""
    __tablename__ = "training_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    unit_type_id: Mapped[int] = mapped_column(ForeignKey("unit_types.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    finish_at: Mapped[datetime] = mapped_column(DateTime)


class ResearchType(Base):
    """
    تحقیق و توسعه: بونوس‌های سراسری روی کل ارتش (نه فقط یک نوع نیرو).
    effect_type: 'attack_percent' | 'defense_percent' | 'training_speed_percent'
    """
    __tablename__ = "research_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    name_fa: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(8), default="🔬")
    effect_type: Mapped[str] = mapped_column(String(32))
    effect_per_level: Mapped[float] = mapped_column(Float, default=2.0)  # درصد به‌ازای هر لول

    cost_gold: Mapped[int] = mapped_column(Integer, default=0)
    cost_iron: Mapped[int] = mapped_column(Integer, default=0)
    cost_oil: Mapped[int] = mapped_column(Integer, default=0)
    base_research_seconds: Mapped[int] = mapped_column(Integer, default=300)
    max_level: Mapped[int] = mapped_column(Integer, default=10)

    user_researches: Mapped[list["UserResearch"]] = relationship(back_populates="research_type")


class UserResearch(Base):
    __tablename__ = "user_researches"
    __table_args__ = (UniqueConstraint("user_id", "research_type_id", name="uq_user_research_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    research_type_id: Mapped[int] = mapped_column(ForeignKey("research_types.id"))

    level: Mapped[int] = mapped_column(Integer, default=0)
    upgrade_finish_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="researches")
    research_type: Mapped["ResearchType"] = relationship(back_populates="user_researches")


class BattleReport(Base):
    """
    گزارش هر نبرد (PvP یا با ربات). defender_id=None یعنی نبرد با NPC بوده.
    winner: 'attacker' | 'defender'
    """
    __tablename__ = "battle_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attacker_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    defender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_pvp: Mapped[bool] = mapped_column(Boolean, default=True)

    winner: Mapped[str] = mapped_column(String(16))  # 'attacker' | 'defender'
    attacker_power: Mapped[int] = mapped_column(Integer, default=0)
    defender_power: Mapped[int] = mapped_column(Integer, default=0)

    attacker_units_lost: Mapped[int] = mapped_column(Integer, default=0)
    defender_units_lost: Mapped[int] = mapped_column(Integer, default=0)
    attacker_hp_lost: Mapped[int] = mapped_column(Integer, default=0)

    loot_gold: Mapped[int] = mapped_column(Integer, default=0)
    loot_iron: Mapped[int] = mapped_column(Integer, default=0)
    loot_oil: Mapped[int] = mapped_column(Integer, default=0)
    loot_food: Mapped[int] = mapped_column(Integer, default=0)
    xp_gained: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    attacker: Mapped["User"] = relationship(foreign_keys=[attacker_id])
    defender: Mapped["User"] = relationship(foreign_keys=[defender_id])


class PvpSeasonScore(Base):
    """
    شمارش پیروزی‌های PvP هر کاربر در یک بازه‌ی هفتگی (period_key مثل '2026-W28').
    برای رتبه‌بندی هفتگی و جایزه‌ی پایان فصل استفاده میشه.
    """
    __tablename__ = "pvp_season_scores"
    __table_args__ = (UniqueConstraint("user_id", "period_key", name="uq_user_pvp_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    period_key: Mapped[str] = mapped_column(String(16))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship()


class MissionType(Base):
    """
    تعریف ثابت یک ماموریت (روزانه یا هفتگی). event_type باید با اسم رویدادی که
    در record_progress صدا زده میشه یکی باشه (مثلا 'bot_battle'، 'train_units').
    """
    __tablename__ = "mission_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True)
    scope: Mapped[str] = mapped_column(String(16))  # 'daily' | 'weekly'
    name_fa: Mapped[str] = mapped_column(String(128))
    icon: Mapped[str] = mapped_column(String(8), default="🎯")
    event_type: Mapped[str] = mapped_column(String(32))
    target_amount: Mapped[int] = mapped_column(Integer, default=1)

    reward_gold: Mapped[int] = mapped_column(Integer, default=0)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0)
    reward_iron: Mapped[int] = mapped_column(Integer, default=0)
    reward_oil: Mapped[int] = mapped_column(Integer, default=0)
    reward_food: Mapped[int] = mapped_column(Integer, default=0)

    progress_rows: Mapped[list["UserMissionProgress"]] = relationship(back_populates="mission_type")


class UserMissionProgress(Base):
    """
    پیشرفت هر کاربر روی هر ماموریت، برای یک دوره‌ی مشخص (period_key).
    period_key برای روزانه مثلا '2026-07-09' و برای هفتگی مثلا '2026-W28' هست،
    یعنی با شروع دوره‌ی جدید خودکار یک ردیف تازه (progress=0) ساخته میشه.
    """
    __tablename__ = "user_mission_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "mission_type_id", "period_key", name="uq_user_mission_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mission_type_id: Mapped[int] = mapped_column(ForeignKey("mission_types.id"))
    period_key: Mapped[str] = mapped_column(String(16))

    progress: Mapped[int] = mapped_column(Integer, default=0)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="mission_progress")
    mission_type: Mapped["MissionType"] = relationship(back_populates="progress_rows")


class Alliance(Base):
    __tablename__ = "alliances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    tag: Mapped[str] = mapped_column(String(8))  # مثلا [IRN]
    description: Mapped[str] = mapped_column(String(256), default="")
    leader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    member_limit: Mapped[int] = mapped_column(Integer, default=20)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["User"]] = relationship(back_populates="alliance", foreign_keys="User.alliance_id")


class AllianceChatMessage(Base):
    __tablename__ = "alliance_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alliance_id: Mapped[int] = mapped_column(ForeignKey("alliances.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AllianceWar(Base):
    """
    جنگ بین دو اتحاد. در طول جنگ، هر نبرد PvP موفق بین اعضای دو طرف به امتیاز
    اتحاد مهاجم اضافه میشه (به‌وسیله‌ی battle.py صدا زده میشه).
    """
    __tablename__ = "alliance_wars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alliance_a_id: Mapped[int] = mapped_column(ForeignKey("alliances.id"))
    alliance_b_id: Mapped[int] = mapped_column(ForeignKey("alliances.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    score_a: Mapped[int] = mapped_column(Integer, default=0)
    score_b: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # 'active' | 'finished'
    winner_alliance_id: Mapped[int | None] = mapped_column(ForeignKey("alliances.id"), nullable=True)


class ItemType(Base):
    """
    نوع آیتم قابل مصرف/معامله. effect_type: 'energy' | 'hp' | 'attack_percent' |
    'defense_percent' | 'random_resources'. duration_minutes=0 یعنی اثر آنی (نه بوست موقت).
    """
    __tablename__ = "item_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)
    name_fa: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(8), default="📦")
    description: Mapped[str] = mapped_column(String(256), default="")
    effect_type: Mapped[str] = mapped_column(String(32))
    effect_value: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    tradeable: Mapped[bool] = mapped_column(Boolean, default=True)


class UserInventory(Base):
    __tablename__ = "user_inventory"
    __table_args__ = (UniqueConstraint("user_id", "item_type_id", name="uq_user_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="inventory")
    item_type: Mapped["ItemType"] = relationship()


class ActiveBoost(Base):
    """بوست موقت فعال (مثلا +۲۰٪ حمله تا یک ساعت دیگه)، از مصرف یک آیتم."""
    __tablename__ = "active_boosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    boost_type: Mapped[str] = mapped_column(String(32))  # 'attack_percent' | 'defense_percent'
    value: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="active_boosts")


class MarketListing(Base):
    """آگهی خرید فوری در بازار - برای منابع (آهن/نفت/غذا) یا آیتم‌ها."""
    __tablename__ = "market_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'iron'|'oil'|'food'
    item_type_id: Mapped[int | None] = mapped_column(ForeignKey("item_types.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_gold: Mapped[int] = mapped_column(Integer, default=0)  # قیمت کل لات (نه واحد)
    status: Mapped[str] = mapped_column(String(16), default="active")  # 'active'|'sold'|'cancelled'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    seller: Mapped["User"] = relationship(foreign_keys=[seller_id])
    item_type: Mapped["ItemType"] = relationship()


class AuctionListing(Base):
    """حراج مزایده‌ای برای آیتم‌ها. بالاترین پیشنهاد در زمان اتمام برنده میشه."""
    __tablename__ = "auction_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    starting_price: Mapped[int] = mapped_column(Integer, default=0)
    current_bid: Mapped[int] = mapped_column(Integer, default=0)
    current_bidder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="active")  # 'active'|'finished'|'cancelled'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    seller: Mapped["User"] = relationship(foreign_keys=[seller_id])
    current_bidder: Mapped["User"] = relationship(foreign_keys=[current_bidder_id])
    item_type: Mapped["ItemType"] = relationship()


class AchievementType(Base):
    """دستاورد دائمی. condition_field اسم فیلدی از User هست که با condition_value مقایسه میشه."""
    __tablename__ = "achievement_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True)
    name_fa: Mapped[str] = mapped_column(String(128))
    icon: Mapped[str] = mapped_column(String(8), default="🏅")
    description: Mapped[str] = mapped_column(String(256), default="")
    condition_field: Mapped[str] = mapped_column(String(32))
    condition_value: Mapped[int] = mapped_column(Integer, default=1)
    reward_gold: Mapped[int] = mapped_column(Integer, default=0)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_type_id", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    achievement_type_id: Mapped[int] = mapped_column(ForeignKey("achievement_types.id"))
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ShopItem(Base):
    """
    آیتم فروشگاه که با تلگرام استارز (XTR) خریداری میشه. price_stars مستقیم
    تعداد استارز هست (برخلاف ارزهای معمولی، برای XTR ضرب‌در-۱۰۰ لازم نیست).
    """
    __tablename__ = "shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True)
    name_fa: Mapped[str] = mapped_column(String(128))
    icon: Mapped[str] = mapped_column(String(8), default="🛍️")
    description: Mapped[str] = mapped_column(String(256), default="")
    price_stars: Mapped[int] = mapped_column(Integer, default=1)

    reward_gold: Mapped[int] = mapped_column(Integer, default=0)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0)
    reward_item_type_id: Mapped[int | None] = mapped_column(ForeignKey("item_types.id"), nullable=True)
    reward_item_quantity: Mapped[int] = mapped_column(Integer, default=0)

    active: Mapped[bool] = mapped_column(Boolean, default=True)

    reward_item_type: Mapped["ItemType"] = relationship()


class Purchase(Base):
    """لاگ خریدهای موفق درون‌برنامه‌ای (برای حسابرسی و پشتیبانی)."""
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    shop_item_id: Mapped[int] = mapped_column(ForeignKey("shop_items.id"))
    stars_paid: Mapped[int] = mapped_column(Integer, default=0)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PrivateMessage(Base):
    __tablename__ = "private_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])
    receiver: Mapped["User"] = relationship(foreign_keys=[receiver_id])


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="open")  # 'open' | 'closed'
    admin_reply: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship()


class AdminLog(Base):
    """لاگ اقدامات مدیریتی (بن، آن‌بن، پیام همگانی و ...) برای حسابرسی."""
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(32))  # 'ban'|'unban'|'broadcast'|'promote_admin'
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger)
    target_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    details: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Room(Base):
    """
    یک گروه تلگرامی که ربات توش اضافه شده و به‌عنوان یه فضای بازی مستقل عمل می‌کنه.
    همه‌ی پروفایل‌های User با room_id برابر این، کاملاً از پروفایل اصلی و روم‌های
    دیگه ایزوله‌ان (منابع، ارتش، ساختمان، اتحاد، بازار، همه‌چیز).
    """
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128), default="گروه")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BannedTelegramUser(Base):
    """
    بن سراسری روی خود شخص تلگرامی (نه یک پروفایل خاص در یک روم)، چون فرد
    می‌تونه در چند روم مختلف پروفایل جدا داشته باشه و باید همه‌جا مسدود بشه.
    """
    __tablename__ = "banned_telegram_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    banned_by: Mapped[int] = mapped_column(BigInteger)
    banned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
