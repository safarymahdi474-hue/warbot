def power_bar(value_a: int, value_b: int, length: int = 10) -> str:
    """
    نواری که نسبت دو قدرت (مثلاً حمله در برابر دفاع) رو گرافیکی نشون میده.
    هرچی value_a نسبت به مجموع بزرگ‌تر باشه، بخش ⚔️ بزرگ‌تره.
    """
    total = value_a + value_b
    filled = length // 2 if total <= 0 else round(length * value_a / total)
    filled = max(0, min(length, filled))
    return "⚔️" * filled + "🛡️" * (length - filled)


def hp_bar(current: int, maximum: int, length: int = 10) -> str:
    if maximum <= 0:
        maximum = 1
    filled = round(length * max(0, min(current, maximum)) / maximum)
    filled = max(0, min(length, filled))
    return "🟩" * filled + "⬜️" * (length - filled)
