from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy import select

from bot.database.db import get_session
from bot.utils.context import user_scope
from bot.database.models import ShopItem, User
from bot.utils.shop import grant_purchase_reward, list_shop_items

router = Router(name="shop")


def shop_keyboard(items: list[ShopItem]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{i.icon} {i.name_fa} — ⭐️{i.price_stars}", callback_data=f"buy_shop_item:{i.id}"
            )
        ]
        for i in items
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_shop_text(items: list[ShopItem]) -> str:
    lines = ["🛍️ <b>فروشگاه</b>\nخرید با تلگرام استارز (⭐️ Stars)\n"]
    for i in items:
        lines.append(f"{i.icon} <b>{i.name_fa}</b> — ⭐️{i.price_stars}\n   {i.description}")
    return "\n\n".join(lines)


@router.message(Command("shop"))
async def cmd_shop(message: Message) -> None:
    async with get_session() as session:
        items = await list_shop_items(session)
    await message.answer(build_shop_text(items), reply_markup=shop_keyboard(items), parse_mode="HTML")


@router.callback_query(F.data == "show_shop")
async def cb_shop(callback: CallbackQuery) -> None:
    async with get_session() as session:
        items = await list_shop_items(session)
    await callback.message.edit_text(
        build_shop_text(items), reply_markup=shop_keyboard(items), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_shop_item:"))
async def cb_buy_shop_item(callback: CallbackQuery) -> None:
    shop_item_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        shop_item = await session.get(ShopItem, shop_item_id)
        if shop_item is None or not shop_item.active:
            await callback.answer("این آیتم دیگه در دسترس نیست.", show_alert=True)
            return

    # برای پرداخت با تلگرام استارز: currency="XTR"، provider_token خالی، و مبلغ‌ها
    # مستقیم به‌عنوان تعداد استارز هستن (نه ضرب‌در-۱۰۰ مثل ارزهای معمولی)
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{shop_item.icon} {shop_item.name_fa}",
        description=shop_item.description,
        payload=f"shop_item:{shop_item.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=shop_item.name_fa, amount=shop_item.price_stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # اینجا می‌تونیم موجودی/اعتبار آیتم رو دوباره چک کنیم؛ فعلاً همیشه تایید می‌کنیم
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    payload = message.successful_payment.invoice_payload
    if not payload.startswith("shop_item:"):
        return
    shop_item_id = int(payload.split(":")[1])

    async with get_session() as session:
        result = await session.execute(select(User).where(*user_scope(message.from_user.id)))
        user = result.scalar_one_or_none()
        shop_item = await session.get(ShopItem, shop_item_id)

        if user is None or shop_item is None:
            await message.answer("خطا در ثبت خرید. لطفاً به پشتیبانی پیام بده.")
            return

        await grant_purchase_reward(
            session, user, shop_item, message.successful_payment.telegram_payment_charge_id
        )
        await session.commit()

    reward_parts = []
    if shop_item.reward_gold:
        reward_parts.append(f"💰{shop_item.reward_gold}")
    if shop_item.reward_coins:
        reward_parts.append(f"🪙{shop_item.reward_coins}")
    if shop_item.reward_item_quantity:
        reward_parts.append(f"🎁×{shop_item.reward_item_quantity}")

    await message.answer(
        f"✅ خرید «{shop_item.name_fa}» موفق بود!\nدریافتی: {' '.join(reward_parts)}\n\n🙏 ممنون از حمایتت!"
    )
