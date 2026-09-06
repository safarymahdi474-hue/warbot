from bot.config import settings
from bot.database.models import User

# لیگ‌ها بر اساس درجه‌ی نظامی، از پایین به بالا. هر لیگ یه حداقل کاپ داره.
LEAGUES = [
    {"key": "soldier", "name_fa": "سرباز", "icon": "🎖️", "min_cup": 0},
    {"key": "corporal", "name_fa": "سرجوخه", "icon": "🎖️", "min_cup": 100},
    {"key": "sergeant", "name_fa": "گروهبان", "icon": "🎖️", "min_cup": 250},
    {"key": "warrant_officer", "name_fa": "استوار", "icon": "🏅", "min_cup": 500},
    {"key": "lieutenant", "name_fa": "ستوان", "icon": "🏅", "min_cup": 800},
    {"key": "captain", "name_fa": "سروان", "icon": "🏅", "min_cup": 1200},
    {"key": "major", "name_fa": "سرگرد", "icon": "🥈", "min_cup": 1700},
    {"key": "colonel", "name_fa": "سرهنگ", "icon": "🥈", "min_cup": 2300},
    {"key": "brigadier", "name_fa": "سرتیپ", "icon": "🥇", "min_cup": 3000},
    {"key": "general", "name_fa": "سپهبد", "icon": "👑", "min_cup": 4000},
]


def get_league_index(cup: int) -> int:
    """ایندکس لیگی که این مقدار کاپ توش قرار می‌گیره (بالاترین آستانه‌ای که ازش رد شده)."""
    index = 0
    for i, league in enumerate(LEAGUES):
        if cup >= league["min_cup"]:
            index = i
        else:
            break
    return index


def get_league(cup: int) -> dict:
    return LEAGUES[get_league_index(cup)]


def get_league_by_index(index: int) -> dict:
    index = max(0, min(len(LEAGUES) - 1, index))
    return LEAGUES[index]


def can_fight(attacker: User, defender: User) -> bool:
    """فقط لیگ خودش یا یه لیگ بالاتر/پایین‌تر قابل حمله‌ست."""
    diff = abs(get_league_index(attacker.league_cup) - get_league_index(defender.league_cup))
    return diff <= settings.LEAGUE_MATCH_TIER_RANGE


def apply_league_result(winner: User, loser: User) -> tuple[int, int]:
    """
    کاپ برنده/بازنده رو آپدیت می‌کنه. خروجی: (میزان کاپ گرفته‌شده توسط برنده, میزان کاپ ازدست‌رفته‌ی بازنده).
    """
    gain = settings.LEAGUE_CUP_WIN_GAIN
    loss = min(loser.league_cup, settings.LEAGUE_CUP_LOSE_PENALTY)

    winner.league_cup += gain
    loser.league_cup = max(0, loser.league_cup - settings.LEAGUE_CUP_LOSE_PENALTY)
    return gain, loss


def build_league_progress_text(user: User) -> str:
    league = get_league(user.league_cup)
    index = get_league_index(user.league_cup)
    lines = [f"{league['icon']} <b>لیگ فعلی: {league['name_fa']}</b>", f"🏆 کاپ: {user.league_cup}"]

    if index < len(LEAGUES) - 1:
        next_league = LEAGUES[index + 1]
        remaining = next_league["min_cup"] - user.league_cup
        lines.append(f"⬆️ تا لیگ {next_league['name_fa']}: {remaining} کاپ مونده")
    else:
        lines.append("🏆 تو بالاترین لیگ (سپهبد) هستی!")

    return "\n".join(lines)
