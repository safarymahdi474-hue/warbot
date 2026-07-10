from bot.config import settings
from bot.database.models import User

SELL_PRICES = {
    "iron": settings.EXCHANGE_SELL_PRICE_IRON,
    "oil": settings.EXCHANGE_SELL_PRICE_OIL,
    "food": settings.EXCHANGE_SELL_PRICE_FOOD,
}

RESOURCE_LABELS = {"iron": "⛏️ آهن", "oil": "🛢️ نفت", "food": "🌾 غذا"}


def buy_price(resource_type: str) -> int:
    sell = SELL_PRICES[resource_type]
    return max(sell + 1, round(sell * (1 + settings.EXCHANGE_BUY_MARKUP_PERCENT / 100)))


def sell_resource(user: User, resource_type: str, quantity: int) -> tuple[str | None, str | None]:
    """خروجی: (پیام موفقیت, پیام خطا) - دقیقاً یکی از این دو پر میشه."""
    if quantity <= 0:
        return None, "تعداد باید مثبت باشه."
    current = getattr(user, resource_type)
    if current < quantity:
        return None, f"به این مقدار {RESOURCE_LABELS[resource_type]} نداری."

    gold_gained = SELL_PRICES[resource_type] * quantity
    setattr(user, resource_type, current - quantity)
    user.gold += gold_gained
    return f"✅ {quantity} {RESOURCE_LABELS[resource_type]} فروختی و 💰{gold_gained} گرفتی.", None


def buy_resource(user: User, resource_type: str, quantity: int) -> tuple[str | None, str | None]:
    """خروجی: (پیام موفقیت, پیام خطا) - دقیقاً یکی از این دو پر میشه."""
    if quantity <= 0:
        return None, "تعداد باید مثبت باشه."

    price = buy_price(resource_type)
    max_field = f"max_{resource_type}"
    current = getattr(user, resource_type)
    cap = getattr(user, max_field)

    if current >= cap:
        return None, "انبارت پره، جا برای این منبع نداری."

    actual_quantity = min(quantity, cap - current)
    actual_cost = price * actual_quantity
    if user.gold < actual_cost:
        # با طلای موجود، حداکثر چقدر می‌تونه بخره
        affordable = user.gold // price
        if affordable <= 0:
            return None, f"طلای کافی نداری. هر واحد {RESOURCE_LABELS[resource_type]} = 💰{price}"
        actual_quantity = min(actual_quantity, affordable)
        actual_cost = price * actual_quantity

    user.gold -= actual_cost
    setattr(user, resource_type, current + actual_quantity)

    msg = f"✅ {actual_quantity} {RESOURCE_LABELS[resource_type]} خریدی و 💰{actual_cost} پرداخت کردی."
    if actual_quantity < quantity:
        msg += "\n(به خاطر محدودیت انبار یا طلا، کمتر از درخواستت خریداری شد.)"
    return msg, None
