import secrets
import string

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message
from sqlalchemy import select

from bot.config import settings
from bot.database.db import get_session
from bot.utils.context import current_room, user_scope
from bot.database.models import (
    BuildingType,
    Country,
    ItemType,
    ResearchType,
    UnitType,
    User,
    UserBuilding,
    UserInventory,
    UserResearch,
    UserUnit,
)
from bot.keyboards.menus import countries_keyboard, main_menu_keyboard

router = Router(name="start")


@router.my_chat_member()
async def on_bot_added_to_chat(event: ChatMemberUpdated) -> None:
    """وقتی ربات به یه گروه جدید اضافه میشه، یه توضیح کوتاه درباره فضای بازی مستقل میده."""
    if event.chat.type == "private":
        return
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
        await event.bot.send_message(
            event.chat.id,
            "🎮 سلام! از الان این گروه یه <b>فضای بازی مستقل</b>ه.\n\n"
            "هر عضو گروه با زدن /start یه پروفایل مخصوص همین گروه می‌سازه؛ منابع، ارتش، "
            "ساختمان، اتحاد و بازار فقط بین اعضای همین گروه رد و بدل میشه و به پروفایل "
            "خصوصی یا گروه‌های دیگه ربطی نداره.\n\n"
            "برای شروع، هر کی /start رو بزنه!",
            parse_mode="HTML",
        )


class Registration(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_country = State()


def generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


async def _get_sorted_countries(session) -> list[Country]:
    """ترتیب پایدار (بر اساس id) که شماره‌ی صفحه‌ها هر بار یکسان بمونه."""
    result = await session.execute(select(Country).order_by(Country.id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# بازگشت مشترک به منوی اصلی - از همه‌ی بخش‌های ربات صدا زده میشه
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "show_main_menu")
async def cb_show_main_menu(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text("🏠 منوی اصلی:", reply_markup=main_menu_keyboard())
    except Exception:
        await callback.message.answer("🏠 منوی اصلی:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, command: CommandObject) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(*user_scope(message.from_user.id))
        )
        user = result.scalar_one_or_none()

        if user is not None:
            await message.answer(
                f"خوش برگشتی، {user.nickname}! 👋",
                reply_markup=main_menu_keyboard(),
            )
            return

        # کاربر جدیده -> شروع فرآیند ثبت‌نام
        # اگه با کد معرف اومده باشه (/start CODE123) ذخیره‌اش می‌کنیم برای فاز دعوت دوستان
        referral_code_used = command.args
        await state.update_data(referred_by_code=referral_code_used)

    if message.chat.type == "private":
        intro = "🎮 به بازی خوش اومدی!\n\n"
    else:
        intro = (
            "🎮 به بازی خوش اومدی!\n\n"
            "🏠 چون اینجا یه گروهه، از الان این گروه یه <b>فضای بازی مستقل</b> برای اعضاشه: "
            "منابع، ارتش، ساختمان، اتحاد و بازار فقط بین اعضای همین گروه رد و بدل میشه و به "
            "پروفایل خصوصی یا گروه‌های دیگه‌ت ربطی نداره.\n\n"
        )

    await message.answer(
        intro + "قبل از هر چیز، یه اسم/نیک‌نیم برای خودت انتخاب کن (۳ تا ۲۰ حرف):",
        parse_mode="HTML",
    )
    await state.set_state(Registration.waiting_for_nickname)


@router.message(Registration.waiting_for_nickname)
async def process_nickname(message: Message, state: FSMContext) -> None:
    nickname = (message.text or "").strip()
    if not (3 <= len(nickname) <= 20):
        await message.answer("نیک‌نیم باید بین ۳ تا ۲۰ حرف باشه. دوباره امتحان کن:")
        return

    await state.update_data(nickname=nickname)

    async with get_session() as session:
        countries = await _get_sorted_countries(session)

    await message.answer(
        "عالی! حالا کشور یا جناحت رو انتخاب کن 🌍\n"
        "(این انتخاب روی منابع و قدرت نظامی اولیه‌ات تاثیر داره)",
        reply_markup=countries_keyboard(countries, page=0),
    )
    await state.set_state(Registration.waiting_for_country)


@router.callback_query(Registration.waiting_for_country, F.data.startswith("countries_page:"))
async def process_countries_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])

    async with get_session() as session:
        countries = await _get_sorted_countries(session)

    try:
        await callback.message.edit_reply_markup(reply_markup=countries_keyboard(countries, page=page))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(Registration.waiting_for_country, F.data == "countries_noop")
async def process_countries_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(Registration.waiting_for_country, F.data.startswith("pick_country:"))
async def process_country(callback: CallbackQuery, state: FSMContext) -> None:
    country_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    nickname = data["nickname"]
    referred_by_code = data.get("referred_by_code")

    async with get_session() as session:
        country = await session.get(Country, country_id)
        if country is None:
            await callback.answer("این کشور پیدا نشد، دوباره امتحان کن.", show_alert=True)
            return

        referred_by_id = None
        if referred_by_code:
            result = await session.execute(
                select(User).where(User.referral_code == referred_by_code)
            )
            referrer = result.scalar_one_or_none()
            if referrer is not None:
                referred_by_id = referrer.id
                # پاداش دعوت‌کننده (مقدار نمونه - در فاز "پاداش دعوت" کامل میشه)
                referrer.gold += 200

        new_user = User(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            nickname=nickname,
            room_id=current_room(),
            country_id=country.id,
            gold=settings.START_GOLD,
            coins=settings.START_COINS,
            energy=settings.START_ENERGY,
            max_energy=settings.MAX_ENERGY,
            hp=settings.START_HP,
            max_hp=settings.MAX_HP,
            level=settings.START_LEVEL,
            xp=0,
            referral_code=generate_referral_code(),
            referred_by_id=referred_by_id,
        )
        session.add(new_user)
        await session.flush()  # برای گرفتن new_user.id قبل از commit

        # برای هر نوع ساختمان، یک ردیف با level=0 (هنوز ساخته نشده) می‌سازیم
        result = await session.execute(select(BuildingType))
        for bt in result.scalars().all():
            session.add(UserBuilding(user_id=new_user.id, building_type_id=bt.id, level=0))

        # برای هر نوع نیرو، یک ردیف با quantity=0, level=1 می‌سازیم
        result = await session.execute(select(UnitType))
        for ut in result.scalars().all():
            session.add(UserUnit(user_id=new_user.id, unit_type_id=ut.id, quantity=0, level=1))

        # برای هر نوع تحقیق، یک ردیف با level=0 می‌سازیم
        result = await session.execute(select(ResearchType))
        for rt in result.scalars().all():
            session.add(UserResearch(user_id=new_user.id, research_type_id=rt.id, level=0))

        # بسته استارتر: کمی آیتم رایگان برای شروع (و امتحان بازار/اینونتوری)
        starter_item_keys = {"energy_potion": 2, "medkit": 2, "attack_scroll": 1}
        result = await session.execute(select(ItemType))
        for it in result.scalars().all():
            if it.key in starter_item_keys:
                session.add(
                    UserInventory(user_id=new_user.id, item_type_id=it.id, quantity=starter_item_keys[it.key])
                )

        await session.commit()

    await state.clear()
    room_note = "" if callback.message.chat.type == "private" else "\n\n🏠 این پروفایل مخصوص همین گروهه."
    await callback.message.edit_text(
        f"✅ ثبت‌نام کامل شد!\n\n"
        f"👤 نیک‌نیم: {nickname}\n"
        f"{country.flag_emoji} کشور: {country.name_fa}\n"
        f"💰 طلای شروع: {settings.START_GOLD}"
        f"{room_note}\n\n"
        f"حالا می‌تونی وارد بازی بشی 👇"
    )
    await callback.message.answer("منوی اصلی:", reply_markup=main_menu_keyboard())
    await callback.answer()
