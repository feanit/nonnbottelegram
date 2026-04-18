import logging
import sys
import json
import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

# Проверка версии Python
if sys.version_info >= (3, 12):
    print("⚠️ Внимание: Вы используете Python 3.12+. Если возникнут проблемы, установите Python 3.11")

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        filters,
        ContextTypes,
        ConversationHandler,
    )
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("📦 Установите библиотеку: pip install python-telegram-bot")
    sys.exit(1)

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8682519221:AAFj9JWFaFJilAYGT5grumO85A8GcL3k2vY"

MODERATION_CHAT_ID = -4990558993
CHANNEL_ID = -1003389680331

MODERATORS = [8050152690, 8516314184, 5276008299, 5051417982]

# Максимальное количество игроков в клубе
MAX_CLUB_MEMBERS = 10

# Минимальная длина ника
MIN_NICKNAME_LENGTH = 2

# КД на смену ника (дней)
NICKNAME_CHANGE_COOLDOWN_DAYS = 14

# Базовые значения КД (в днях)
COOLDOWN_BASE = {
    "free_agent": 1,
    "custom_text": 1,
    "transfer": 2,
    "resume": 30,
}

# Глобальный КД между отправкой заявок (минут)
REQUEST_COOLDOWN_MINUTES = 2

# Привилегии в точном формате
PRIVILEGES = {
    "player": "[Игрок]",
    "vip": "[Вип]",
    "owner": "[Овнер]"
}

PRIVILEGE_EMOJIS = {
    "player": "👤",
    "vip": "💎",
    "owner": "👑"
}

CLUBS = [
    "Notem Esports",
    "FUX Esports",
    "Seta Division",
    "Natures Vincere",
    "Qlach",
    "Team Kuesa",
    "Trile Gaming",
    "Mythic Esports",
    "Lazy Raccoon",
    "LK Gaming",
    "Rifal Esports",
    "Elegate",
    "HMBL",
    "Uncore Esports",
    "Scream Esports",
    "Orions Gaming",
    "Moud",
    "Silly Z",
    "Team Elektro",
    "Vatik",
    "Only Reals",
    "INTR",
    "Vetra Gaming",
    "Qerix",
    "Mortal Sinners",
    "Unity Force",
]

TEAM_OWNERS: Dict[int, str] = {}

DATA_FILE = "bot_data.json"

# ==================== СОСТОЯНИЯ ====================
(
    REGISTER_NICKNAME,
    WAITING_FOR_FREE_AGENT_COMMENT,
    WAITING_FOR_CUSTOM_TEXT,
    WAITING_FOR_RETIRE_COMMENT,
    WAITING_FOR_RESUME_COMMENT,
    WAITING_FOR_TRANSFER_COMMENT,
    WAITING_FOR_BAN_REASON,
    WAITING_FOR_RESET_CD_USER,
    WAITING_FOR_NEW_NICKNAME,
    WAITING_FOR_PRIVILEGE_USER,
    WAITING_FOR_REJECT_REASON,
    WAITING_FOR_TRANSFER_NICKNAME,
    WAITING_FOR_CLUB_CLOSE_CONFIRM,
    WAITING_FOR_IDEA_TEXT,           # новое состояние
) = range(14)

# ==================== БАЗА ДАННЫХ ====================
users: Dict[int, dict] = {}
clubs_data: Dict[str, dict] = {}
pending_posts: Dict[int, dict] = {}
banned_users: Dict[int, dict] = {}
pending_transfers: Dict[int, dict] = {}

# Статусы клуба: "active" - активен, "closed" - закрыт
CLUB_STATUS = {
    "active": "🟢 Активен",
    "closed": "🔴 Закрыт"
}

for club in CLUBS:
    clubs_data[club] = {
        "owner_id": None,
        "players": [],
        "transfer_cooldowns": {},
        "status": "active",
        "closed_date": None,
    }

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ====================
def save_data():
    data = {
        "users": {},
        "banned_users": {},
        "team_owners": {str(k): v for k, v in TEAM_OWNERS.items()},
        "clubs_data": {},
        "pending_posts": {},
        "pending_transfers": {}
    }

    for uid, user_data in users.items():
        data["users"][str(uid)] = user_data.copy()
        if "reg_date" in data["users"][str(uid)] and data["users"][str(uid)]["reg_date"]:
            data["users"][str(uid)]["reg_date"] = data["users"][str(uid)]["reg_date"].isoformat()
        if "retire_date" in data["users"][str(uid)] and data["users"][str(uid)]["retire_date"]:
            data["users"][str(uid)]["retire_date"] = data["users"][str(uid)]["retire_date"].isoformat()
        if "last_free_agent_date" in data["users"][str(uid)] and data["users"][str(uid)]["last_free_agent_date"]:
            data["users"][str(uid)]["last_free_agent_date"] = data["users"][str(uid)][
                "last_free_agent_date"].isoformat()
        if "last_custom_text_date" in data["users"][str(uid)] and data["users"][str(uid)]["last_custom_text_date"]:
            data["users"][str(uid)]["last_custom_text_date"] = data["users"][str(uid)][
                "last_custom_text_date"].isoformat()
        if "last_nickname_change_date" in data["users"][str(uid)] and data["users"][str(uid)]["last_nickname_change_date"]:
            data["users"][str(uid)]["last_nickname_change_date"] = data["users"][str(uid)]["last_nickname_change_date"].isoformat()
        if "last_request_time" in data["users"][str(uid)] and data["users"][str(uid)]["last_request_time"]:
            data["users"][str(uid)]["last_request_time"] = data["users"][str(uid)]["last_request_time"].isoformat()

    for uid, ban_data in banned_users.items():
        data["banned_users"][str(uid)] = ban_data.copy()
        if "date" in data["banned_users"][str(uid)]:
            data["banned_users"][str(uid)]["date"] = data["banned_users"][str(uid)]["date"].isoformat()

    for club_name, club_data in clubs_data.items():
        data["clubs_data"][club_name] = {
            "owner_id": club_data["owner_id"],
            "players": club_data["players"],
            "transfer_cooldowns": {},
            "status": club_data.get("status", "active"),
            "closed_date": club_data.get("closed_date")
        }
        for uid, cooldown_date in club_data["transfer_cooldowns"].items():
            data["clubs_data"][club_name]["transfer_cooldowns"][str(uid)] = cooldown_date.isoformat()
        if club_data.get("closed_date"):
            data["clubs_data"][club_name]["closed_date"] = club_data["closed_date"].isoformat()

    # Сохраняем pending_posts
    for post_id, post in pending_posts.items():
        post_copy = post.copy()
        if "extra_data" in post_copy and post_copy["extra_data"]:
            extra = post_copy["extra_data"].copy()
            for k, v in extra.items():
                if isinstance(v, datetime):
                    extra[k] = v.isoformat()
            post_copy["extra_data"] = extra
        data["pending_posts"][str(post_id)] = post_copy

    # Сохраняем pending_transfers
    for transfer_id, transfer in pending_transfers.items():
        data["pending_transfers"][str(transfer_id)] = transfer

    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("✅ Данные сохранены")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")


def load_data():
    global users, banned_users, TEAM_OWNERS, clubs_data, pending_posts, pending_transfers

    if not os.path.exists(DATA_FILE):
        logger.info("📁 Новый файл данных")
        return

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        users.clear()
        for uid_str, user_data in data.get("users", {}).items():
            uid = int(uid_str)
            if "reg_date" in user_data and user_data["reg_date"]:
                user_data["reg_date"] = datetime.fromisoformat(user_data["reg_date"])
            if "retire_date" in user_data and user_data["retire_date"]:
                user_data["retire_date"] = datetime.fromisoformat(user_data["retire_date"])
            if "last_free_agent_date" in user_data and user_data["last_free_agent_date"]:
                user_data["last_free_agent_date"] = datetime.fromisoformat(user_data["last_free_agent_date"])
            if "last_custom_text_date" in user_data and user_data["last_custom_text_date"]:
                user_data["last_custom_text_date"] = datetime.fromisoformat(user_data["last_custom_text_date"])
            if "last_nickname_change_date" in user_data and user_data["last_nickname_change_date"]:
                user_data["last_nickname_change_date"] = datetime.fromisoformat(user_data["last_nickname_change_date"])
            if "last_request_time" in user_data and user_data["last_request_time"]:
                user_data["last_request_time"] = datetime.fromisoformat(user_data["last_request_time"])
            users[uid] = user_data

        banned_users.clear()
        for uid_str, ban_data in data.get("banned_users", {}).items():
            uid = int(uid_str)
            if "date" in ban_data and ban_data["date"]:
                ban_data["date"] = datetime.fromisoformat(ban_data["date"])
            banned_users[uid] = ban_data

        TEAM_OWNERS.clear()
        for uid_str, club_name in data.get("team_owners", {}).items():
            TEAM_OWNERS[int(uid_str)] = club_name

        for club_name, club_data in data.get("clubs_data", {}).items():
            if club_name in clubs_data:
                clubs_data[club_name]["owner_id"] = club_data.get("owner_id")
                clubs_data[club_name]["players"] = club_data.get("players", [])
                clubs_data[club_name]["status"] = club_data.get("status", "active")
                if club_data.get("closed_date"):
                    clubs_data[club_name]["closed_date"] = datetime.fromisoformat(club_data["closed_date"])
                else:
                    clubs_data[club_name]["closed_date"] = None
                for uid_str, cooldown_str in club_data.get("transfer_cooldowns", {}).items():
                    uid = int(uid_str)
                    clubs_data[club_name]["transfer_cooldowns"][uid] = datetime.fromisoformat(cooldown_str)

        # Восстанавливаем pending_posts
        pending_posts.clear()
        for post_id_str, post_data in data.get("pending_posts", {}).items():
            post_id = int(post_id_str)
            if "extra_data" in post_data and post_data["extra_data"]:
                extra = post_data["extra_data"]
                for k, v in extra.items():
                    if isinstance(v, str) and v.endswith(('+00:00', 'Z')):  # примерное определение
                        try:
                            extra[k] = datetime.fromisoformat(v)
                        except:
                            pass
            pending_posts[post_id] = post_data

        # Восстанавливаем pending_transfers
        pending_transfers.clear()
        for transfer_id_str, transfer_data in data.get("pending_transfers", {}).items():
            transfer_id = int(transfer_id_str)
            pending_transfers[transfer_id] = transfer_data

        logger.info(f"✅ Загружено: {len(users)} пользователей, {len(banned_users)} банов, "
                    f"{len(pending_posts)} заявок, {len(pending_transfers)} трансферов")
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def is_private_chat(update: Update) -> bool:
    """Проверяет, является ли чат личным (с учётом возможного None)."""
    if update.effective_chat is None:
        logger.warning("effective_chat is None в is_private_chat")
        return False
    return update.effective_chat.type == 'private'


def is_banned(user_id: int) -> bool:
    return user_id in banned_users


def get_cooldown_days(uid: int, cooldown_type: str) -> int:
    """Возвращает количество дней для КД с учётом привилегии VIP (уменьшение в 2 раза)"""
    base_days = COOLDOWN_BASE.get(cooldown_type, 1)
    if uid in users and users[uid].get("privilege") == "vip":
        return max(1, base_days // 2)
    return base_days


def get_cooldown_delta(uid: int, cooldown_type: str) -> timedelta:
    """Возвращает timedelta для КД с учётом привилегии"""
    days = get_cooldown_days(uid, cooldown_type)
    return timedelta(days=days)


def check_free_agent_cooldown(uid: int) -> Tuple[bool, Optional[str]]:
    if uid not in users or "last_free_agent_date" not in users[uid] or not users[uid]["last_free_agent_date"]:
        return True, None
    last = users[uid]["last_free_agent_date"]
    delta = get_cooldown_delta(uid, "free_agent")
    if datetime.now() - last < delta:
        remaining = delta - (datetime.now() - last)
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        return False, f"⏳ {hours}ч {minutes}м"
    return True, None


def check_custom_text_cooldown(uid: int) -> Tuple[bool, Optional[str]]:
    if uid not in users or "last_custom_text_date" not in users[uid] or not users[uid]["last_custom_text_date"]:
        return True, None
    last = users[uid]["last_custom_text_date"]
    delta = get_cooldown_delta(uid, "custom_text")
    if datetime.now() - last < delta:
        remaining = delta - (datetime.now() - last)
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        return False, f"⏳ {hours}ч {minutes}м"
    return True, None


def check_nickname_change_cooldown(uid: int) -> Tuple[bool, Optional[str]]:
    """Проверяет КД на смену ника (14 дней)"""
    if uid not in users or "last_nickname_change_date" not in users[uid] or not users[uid]["last_nickname_change_date"]:
        return True, None
    last = users[uid]["last_nickname_change_date"]
    delta = timedelta(days=NICKNAME_CHANGE_COOLDOWN_DAYS)
    if datetime.now() - last < delta:
        remaining = delta - (datetime.now() - last)
        days = remaining.days
        hours = remaining.seconds // 3600
        return False, f"⏳ {days}д {hours}ч"
    return True, None


def check_request_cooldown(uid: int) -> Tuple[bool, Optional[str]]:
    """Проверяет, можно ли отправить новую заявку (глобальный 2-минутный КД)."""
    if uid not in users or "last_request_time" not in users[uid] or not users[uid]["last_request_time"]:
        return True, None
    last = users[uid]["last_request_time"]
    delta = timedelta(minutes=REQUEST_COOLDOWN_MINUTES)
    if datetime.now() - last < delta:
        remaining = delta - (datetime.now() - last)
        minutes = remaining.seconds // 60
        seconds = remaining.seconds % 60
        return False, f"⏳ {minutes}м {seconds}с"
    return True, None


def check_cooldown(uid: int, club: str):
    if uid not in clubs_data[club]["transfer_cooldowns"]:
        return True, ""
    last = clubs_data[club]["transfer_cooldowns"][uid]
    delta = get_cooldown_delta(uid, "transfer")
    if datetime.now() - last < delta:
        remain = delta - (datetime.now() - last)
        hours = remain.seconds // 3600
        minutes = (remain.seconds % 3600) // 60
        return False, f"⏳ {hours}ч {minutes}м"
    return True, ""


def check_resume_cooldown(uid: int):
    if uid not in users or not users[uid].get("retire_date"):
        return True, ""
    last = users[uid]["retire_date"]
    delta = get_cooldown_delta(uid, "resume")
    if datetime.now() - last < delta:
        remain = delta - (datetime.now() - last)
        return False, f"⏳ {remain.days}д"
    return True, ""


def is_valid_nickname(text: str) -> Tuple[bool, Optional[str]]:
    if len(text) < MIN_NICKNAME_LENGTH:
        return False, f"❌ Ник должен содержать минимум {MIN_NICKNAME_LENGTH} символа"
    if not re.match(r'^[A-Za-z0-9_]+$', text):
        return False, "❌ Ник может содержать только английские буквы, цифры и символ _"
    return True, None


def is_nickname_taken(nickname: str, exclude_user_id: int = None) -> bool:
    for uid, user_data in users.items():
        if exclude_user_id and uid == exclude_user_id:
            continue
        if user_data.get("nickname", "").lower() == nickname.lower():
            return True
    return False


def find_user_by_nickname(nickname: str) -> Optional[int]:
    for uid, user_data in users.items():
        if user_data.get("nickname", "").lower() == nickname.lower():
            return uid
    return None


def find_user_by_username(username: str) -> Optional[int]:
    for uid, user_data in users.items():
        if user_data.get("username", "").lower() == username.lower():
            return uid
    return None


def get_user_privilege_text(user_data: dict) -> str:
    privilege = user_data.get("privilege", "player")
    return PRIVILEGES.get(privilege, "[Игрок]")


def get_user_privilege_emoji(user_data: dict) -> str:
    privilege = user_data.get("privilege", "player")
    return PRIVILEGE_EMOJIS.get(privilege, "👤")


def format_privilege_for_post(user_data: dict) -> str:
    return get_user_privilege_text(user_data)


def update_username(uid: int, new_username: str):
    if uid in users and users[uid].get("username") != new_username:
        users[uid]["username"] = new_username
        save_data()


def escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def truncate_text(text: str, max_length: int = 4000) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 50] + "\n\n... (текст обрезан из-за ограничения длины)"


def get_main_keyboard(user_id: int):
    if is_banned(user_id):
        return None

    keyboard = []

    if users.get(user_id, {}).get("retired"):
        keyboard = [
            [InlineKeyboardButton("👤 Профиль", callback_data="profile"),
             InlineKeyboardButton("🌟 Возобновить", callback_data="resume")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📢 Свободный агент", callback_data="free_agent"),
             InlineKeyboardButton("📝 Свой текст", callback_data="custom_text")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile"),
             InlineKeyboardButton("⚡ Завершить", callback_data="retire")],
            [InlineKeyboardButton("🌟 Возобновить", callback_data="resume"),
             InlineKeyboardButton("✏️ Сменить ник", callback_data="change_nickname")],
        ]

        if user_id in TEAM_OWNERS:
            club_name = TEAM_OWNERS[user_id]
            if clubs_data[club_name]["status"] == "active":
                keyboard.append([
                    InlineKeyboardButton("🔄 Трансфер", callback_data="transfer"),
                    InlineKeyboardButton("🏢 Управление клубом", callback_data="manage_club")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("🏢 Управление клубом (закрыт)", callback_data="manage_club")
                ])

    # Кнопка "Предложить идею" доступна всем (даже retired)
    keyboard.append([InlineKeyboardButton("💡 Предложить идею", callback_data="suggest_idea")])

    if user_id in MODERATORS:
        keyboard.append([InlineKeyboardButton("🛠 Модератор", callback_data="moderator_panel")])

    return InlineKeyboardMarkup(keyboard)


def get_manage_club_keyboard(club_name: str, club_status: str):
    keyboard = [
        [InlineKeyboardButton("👥 Игроки", callback_data=f"club_players_{club_name}"),
         InlineKeyboardButton("📊 Профиль клуба", callback_data=f"club_profile_{club_name}")],
    ]
    if club_status == "active":
        keyboard.append([InlineKeyboardButton("🔴 Закрыть клуб (потеря прав)", callback_data=f"close_club_{club_name}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


def get_moderator_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚫 Забанить", callback_data="mod_ban"),
         InlineKeyboardButton("✅ Разбанить", callback_data="mod_unban")],
        [InlineKeyboardButton("📋 Список банов", callback_data="mod_ban_list")],
        [InlineKeyboardButton("🔄 Сбросить КД", callback_data="mod_reset_cd")],
        [InlineKeyboardButton("⚡ Сбросить КД возврата", callback_data="mod_force_retire")],
        [InlineKeyboardButton("👑 Выдать привилегию", callback_data="mod_give_privilege")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def format_profile(user_data: dict, user_id: int = None):
    privilege_text = get_user_privilege_text(user_data)
    privilege_emoji = get_user_privilege_emoji(user_data)

    if user_data.get("club"):
        status = f"🏢 Клуб: {user_data['club']}"
        club_status = clubs_data.get(user_data['club'], {}).get("status", "active")
        if club_status == "closed":
            status += " (🔴 Клуб закрыт)"
    else:
        status = "✅ Свободный агент"

    career = "❌ Завершил" if user_data.get("retired") else "✅ Активен"

    cd_text = ""
    if user_data.get("retire_date") and user_data.get("retired"):
        retire_date = user_data["retire_date"]
        delta_days = get_cooldown_days(user_id, "resume") if user_id else 30
        if datetime.now() - retire_date < timedelta(days=delta_days):
            remaining = timedelta(days=delta_days) - (datetime.now() - retire_date)
            cd_text = f"\n⏳ КД возврата: {remaining.days}д {remaining.seconds // 3600}ч"

    if user_data.get("last_free_agent_date"):
        last = user_data["last_free_agent_date"]
        delta_days = get_cooldown_days(user_id, "free_agent") if user_id else 1
        if datetime.now() - last < timedelta(days=delta_days):
            remaining = timedelta(days=delta_days) - (datetime.now() - last)
            cd_text += f"\n⏳ КД свободного агента: {remaining.seconds // 3600}ч {(remaining.seconds % 3600) // 60}м"

    if user_data.get("last_custom_text_date"):
        last = user_data["last_custom_text_date"]
        delta_days = get_cooldown_days(user_id, "custom_text") if user_id else 1
        if datetime.now() - last < timedelta(days=delta_days):
            remaining = timedelta(days=delta_days) - (datetime.now() - last)
            cd_text += f"\n⏳ КД своего текста: {remaining.seconds // 3600}ч {(remaining.seconds % 3600) // 60}м"

    if user_data.get("last_nickname_change_date"):
        last = user_data["last_nickname_change_date"]
        if datetime.now() - last < timedelta(days=NICKNAME_CHANGE_COOLDOWN_DAYS):
            remaining = timedelta(days=NICKNAME_CHANGE_COOLDOWN_DAYS) - (datetime.now() - last)
            cd_text += f"\n⏳ КД смены ника: {remaining.days}д {remaining.seconds // 3600}ч"

    ban_text = ""
    if user_id and is_banned(user_id):
        ban_text = f"\n\n🚫 **Забанен**\nПричина: {banned_users[user_id]['reason']}"

    safe_nickname = escape_markdown(user_data['nickname'])
    safe_username = escape_markdown(user_data['username'])
    safe_status = escape_markdown(status)
    safe_career = escape_markdown(career)
    safe_cd = escape_markdown(cd_text) if cd_text else ""
    safe_ban = escape_markdown(ban_text) if ban_text else ""

    return f"""
👤 **Профиль**

{privilege_emoji} **{privilege_text}**
🎮 **Ник:** `{safe_nickname}`
📱 **Username:** @{safe_username}
🆔 **ID:** `{user_id}`

📌 **Статус:** {safe_status}
⚡ **Карьера:** {safe_career}{safe_cd}{safe_ban}
"""


async def format_club_profile(club_name: str, club_data: dict):
    players = []
    for pid in club_data["players"][:10]:
        if pid in users:
            u = users[pid]
            privilege_text = get_user_privilege_text(u)
            privilege_emoji = get_user_privilege_emoji(u)
            emoji = "🔴" if u.get("retired") else "🟢"
            ban = "🚫" if is_banned(pid) else ""
            safe_nickname = escape_markdown(u['nickname'])
            players.append(f"{emoji}{ban} {privilege_emoji} {safe_nickname} {privilege_text}")

    owner_info = "Нет владельца"
    if club_data["owner_id"] and club_data["owner_id"] in users:
        owner = users[club_data["owner_id"]]
        safe_owner_nick = escape_markdown(owner['nickname'])
        safe_owner_username = escape_markdown(owner['username'])
        owner_info = f"{safe_owner_nick} (@{safe_owner_username})"
    else:
        owner_info = "❌ Владелец удален (клуб закрыт)"

    status_text = CLUB_STATUS.get(club_data.get("status", "active"), "🟢 Активен")
    closed_info = ""
    if club_data.get("status") == "closed" and club_data.get("closed_date"):
        closed_info = f"\n📅 **Закрыт:** {club_data['closed_date'].strftime('%d.%m.%Y')}"

    members_count = len(club_data['players'])
    members_info = f"\n📊 **Заполненность:** {members_count}/{MAX_CLUB_MEMBERS}"

    safe_club_name = escape_markdown(club_name)

    return f"""
🏢 **Профиль клуба**

📛 **Название:** {safe_club_name}
👑 **Владелец:** {owner_info}
📊 **Статус:** {status_text}{closed_info}
👥 **Игроков:** {members_count}{members_info}

**Состав команды:**
{chr(10).join(players) if players else '❌ Нет игроков'}
"""


def format_player_info(user_data: dict, user_id: int):
    privilege_text = get_user_privilege_text(user_data)
    privilege_emoji = get_user_privilege_emoji(user_data)

    club = user_data.get("club")
    if club:
        status = f"🏢 Клуб: {club}"
        club_status = clubs_data.get(club, {}).get("status", "active")
        if club_status == "closed":
            status += " (🔴 Клуб закрыт)"
    else:
        status = "✅ Свободный агент"

    career_start = "Неизвестно"
    if "reg_date" in user_data and user_data["reg_date"]:
        career_start = user_data["reg_date"].strftime("%d.%m.%Y %H:%M")

    safe_nickname = escape_markdown(user_data['nickname'])
    safe_username = escape_markdown(user_data['username'])
    safe_status = escape_markdown(status)
    safe_start = escape_markdown(career_start)

    return f"""
👤 **Информация об игроке**

{privilege_emoji} **{privilege_text}**
🎮 **Ник:** `{safe_nickname}`
📱 **Username:** @{safe_username}
🆔 **ID:** `{user_id}`
🏢 **Текущий клуб:** {safe_status}
📅 **Начало карьеры:** {safe_start}
"""


# ==================== КОМАНДЫ МОДЕРАТОРОВ ====================
async def reset_cds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in MODERATORS:
        await update.message.reply_text("❌ Нет прав")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /reset_cds ID_игрока")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return

    if target_id not in users:
        await update.message.reply_text("❌ Игрок с таким ID не найден")
        return

    for club in clubs_data:
        if target_id in clubs_data[club]["transfer_cooldowns"]:
            del clubs_data[club]["transfer_cooldowns"][target_id]

    if target_id in users:
        if "last_free_agent_date" in users[target_id]:
            del users[target_id]["last_free_agent_date"]
        if "last_custom_text_date" in users[target_id]:
            del users[target_id]["last_custom_text_date"]
        if "retire_date" in users[target_id]:
            users[target_id]["retire_date"] = None
        if "last_nickname_change_date" in users[target_id]:
            del users[target_id]["last_nickname_change_date"]
        if "last_request_time" in users[target_id]:
            del users[target_id]["last_request_time"]

    save_data()
    await update.message.reply_text(f"✅ Все КД сброшены для игрока с ID {target_id}")


async def force_retire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in MODERATORS:
        await update.message.reply_text("❌ Нет прав")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /force_retire ID_игрока")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return

    if target_id not in users:
        await update.message.reply_text("❌ Игрок с таким ID не найден")
        return

    users[target_id]["retire_date"] = None
    save_data()
    await update.message.reply_text(f"✅ КД на возвращение карьеры сброшен для игрока с ID {target_id}")


async def give_privilege(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in MODERATORS:
        await update.message.reply_text("❌ Нет прав")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /give_privilege ID_игрока player/vip/owner")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return

    privilege = context.args[1].lower()

    if privilege not in ["player", "vip", "owner"]:
        await update.message.reply_text("❌ Доступные привилегии: player, vip, owner")
        return

    if target_id not in users:
        await update.message.reply_text("❌ Игрок с таким ID не найден")
        return

    users[target_id]["privilege"] = privilege
    save_data()

    privilege_text = PRIVILEGES.get(privilege, "[Игрок]")
    await update.message.reply_text(f"✅ Игроку с ID {target_id} выдана привилегия {privilege_text}!")

    try:
        await context.bot.send_message(
            target_id,
            f"🎉 Вам выдана привилегия {privilege_text}!"
        )
    except:
        pass


# ==================== КОМАНДА ДЛЯ МОДЕРАТОРОВ: ЗАКРЫТЬ КЛУБ ====================
async def close_club_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in MODERATORS:
        await update.message.reply_text("❌ У вас нет прав модератора")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /close_club ID_владельца")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return

    if target_id not in users:
        await update.message.reply_text(f"❌ Пользователь с ID {target_id} не найден")
        return

    if target_id not in TEAM_OWNERS:
        await update.message.reply_text(f"❌ Пользователь с ID {target_id} не является владельцем клуба")
        return

    club_name = TEAM_OWNERS[target_id]

    if clubs_data[club_name]["status"] == "closed":
        await update.message.reply_text(f"❌ Клуб {club_name} уже закрыт")
        return

    players_in_club = clubs_data[club_name]["players"].copy()

    for pid in players_in_club:
        if pid in users:
            users[pid]["club"] = None
            users[pid]["free_agent"] = True

    clubs_data[club_name]["status"] = "closed"
    clubs_data[club_name]["closed_date"] = datetime.now()
    clubs_data[club_name]["players"] = []

    if target_id in TEAM_OWNERS:
        del TEAM_OWNERS[target_id]

    clubs_data[club_name]["owner_id"] = None
    save_data()

    await update.message.reply_text(
        f"✅ Клуб {club_name} успешно закрыт модератором!\n"
        f"Владелец с ID {target_id} больше не имеет прав на клуб.\n"
        f"Все игроки ({len(players_in_club)}) стали свободными агентами."
    )

    try:
        await context.bot.send_message(
            target_id,
            f"🔴 Ваш клуб {club_name} был закрыт модератором.\n"
            f"Вы больше не являетесь владельцем клуба."
        )
    except:
        pass

    for pid in players_in_club:
        try:
            await context.bot.send_message(
                pid,
                f"🔴 Клуб **{club_name}**, в котором вы состояли, был закрыт.\n"
                f"Теперь вы свободный агент.",
                parse_mode='Markdown'
            )
        except:
            pass

    # Уведомление в группу модерации
    try:
        await context.bot.send_message(
            MODERATION_CHAT_ID,
            f"🔔 Клуб **{club_name}** закрыт модератором @{update.effective_user.username}\n"
            f"Владелец: @{users[target_id]['username']} (ID: {target_id})\n"
            f"Освобождено игроков: {len(players_in_club)}"
        )
    except:
        pass


# ==================== КОМАНДА ДЛЯ МОДЕРАТОРОВ: ПЕРЕВОД ИГРОКА В КЛУБ ====================
async def transfer_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in MODERATORS:
        await update.message.reply_text("❌ У вас нет прав модератора")
        return ConversationHandler.END

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: `/transfer_player ID_игрока Название клуба`\n"
            f"Доступные клубы: {', '.join(CLUBS)}",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return ConversationHandler.END

    club_name = " ".join(context.args[1:]).strip('"')

    if club_name not in CLUBS:
        await update.message.reply_text(
            f"❌ Клуб '{club_name}' не найден.\n"
            f"Доступные клубы: {', '.join(CLUBS)}"
        )
        return ConversationHandler.END

    if clubs_data[club_name]["status"] == "closed":
        await update.message.reply_text(f"❌ Клуб '{club_name}' закрыт. Сначала откройте его.")
        return ConversationHandler.END

    if len(clubs_data[club_name]["players"]) >= MAX_CLUB_MEMBERS:
        await update.message.reply_text(
            f"❌ В клубе '{club_name}' уже максимальное количество игроков ({MAX_CLUB_MEMBERS})."
        )
        return ConversationHandler.END

    if target_id not in users:
        await update.message.reply_text(f"❌ Игрок с ID {target_id} не найден в базе.")
        return ConversationHandler.END

    target_user = users[target_id]

    if is_banned(target_id):
        await update.message.reply_text(f"❌ Игрок с ID {target_id} забанен и не может быть переведен.")
        return ConversationHandler.END

    if target_user.get("retired"):
        await update.message.reply_text(f"❌ Игрок с ID {target_id} завершил карьеру и не может быть переведен.")
        return ConversationHandler.END

    old_club = target_user.get("club")

    if old_club and old_club in clubs_data:
        if target_id in clubs_data[old_club]["players"]:
            clubs_data[old_club]["players"].remove(target_id)

    users[target_id]["club"] = club_name
    users[target_id]["free_agent"] = False
    if target_id not in clubs_data[club_name]["players"]:
        clubs_data[club_name]["players"].append(target_id)

    save_data()

    await update.message.reply_text(
        f"✅ Игрок с ID {target_id} успешно переведен в клуб {club_name}!"
    )

    try:
        privilege_text = get_user_privilege_text(target_user)
        await context.bot.send_message(
            target_id,
            f"👤 {privilege_text} {target_user['nickname']} (@{target_user['username']}), "
            f"вы были переведены модератором в клуб {club_name}!"
        )
    except:
        pass

    try:
        moderator = users.get(user_id, {}).get('nickname', 'Модератор')
        await context.bot.send_message(
            MODERATION_CHAT_ID,
            f"🔔 Модераторский перевод\n\n"
            f"Модератор: {moderator} (@{update.effective_user.username})\n"
            f"Игрок: {target_user['nickname']} (@{target_user['username']})\n"
            f"ID: {target_id}\n"
            f"Из клуба: {old_club if old_club else 'нет'}\n"
            f"Переведен в клуб: {club_name}"
        )
    except:
        pass

    return ConversationHandler.END


# ==================== КОМАНДА ДЛЯ ВЛАДЕЛЬЦА: ЗАКРЫТЬ СВОЙ КЛУБ ====================
async def close_my_club(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        await update.message.reply_text("🤖 Эта команда доступна только в личных сообщениях.")
        return ConversationHandler.END

    user_id = update.effective_user.id

    if user_id not in TEAM_OWNERS:
        await update.message.reply_text("❌ У вас нет клуба для закрытия")
        return ConversationHandler.END

    club_name = TEAM_OWNERS[user_id]

    if clubs_data[club_name]["status"] == "closed":
        await update.message.reply_text(f"❌ Клуб {club_name} уже закрыт")
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, закрыть", callback_data=f"confirm_close_club_{club_name}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="back_to_main")
        ]
    ]

    await update.message.reply_text(
        f"⚠️ Вы уверены, что хотите **закрыть клуб {club_name}**?\n\n"
        f"После закрытия:\n"
        f"• Вы потеряете права владельца клуба\n"
        f"• Все игроки клуба станут свободными агентами\n"
        f"• Кнопки трансфера исчезнут\n"
        f"• Только модератор сможет назначить нового владельца",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_CLUB_CLOSE_CONFIRM


# ==================== КОМАНДА /transfer (для владельцев клубов) ====================
async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /transfer <ник> - предложить трансфер игроку. Работает в любом чате."""
    uid = update.effective_user.id

    if uid not in users:
        await update.message.reply_text("❌ Вы не зарегистрированы. Используйте /start в ЛС с ботом.")
        return

    if uid not in TEAM_OWNERS:
        await update.message.reply_text("❌ Вы не являетесь владельцем клуба.")
        return

    club = TEAM_OWNERS[uid]

    if clubs_data[club]["status"] == "closed":
        await update.message.reply_text("❌ Ваш клуб закрыт. Трансферы недоступны.")
        return

    if len(clubs_data[club]["players"]) >= MAX_CLUB_MEMBERS:
        await update.message.reply_text(f"❌ В вашем клубе уже максимальное количество игроков ({MAX_CLUB_MEMBERS}).")
        return

    if not context.args:
        await update.message.reply_text("❌ Использование: /transfer <ник игрока>")
        return

    nickname = " ".join(context.args).strip()

    target_id = find_user_by_nickname(nickname)
    if not target_id:
        await update.message.reply_text(f"❌ Игрок с ником '{nickname}' не найден.")
        return

    if target_id == uid:
        await update.message.reply_text("❌ Вы не можете отправить трансфер самому себе.")
        return

    if is_banned(target_id):
        await update.message.reply_text("❌ Этот игрок забанен.")
        return
    if users[target_id].get("retired"):
        await update.message.reply_text(f"❌ Игрок {users[target_id]['nickname']} завершил карьеру.")
        return
    if target_id in clubs_data[club]["players"]:
        await update.message.reply_text(f"❌ Игрок {users[target_id]['nickname']} уже в вашем клубе.")
        return
    if not users[target_id].get("free_agent"):
        current_club = users[target_id].get("club")
        if current_club:
            await update.message.reply_text(f"❌ Игрок {users[target_id]['nickname']} уже в клубе {current_club}.")
            return

    ok, msg = check_cooldown(target_id, club)
    if not ok:
        await update.message.reply_text(f"❌ У игрока ещё КД {msg}")
        return

    transfer_id = len(pending_transfers) + 1
    pending_transfers[transfer_id] = {
        "owner_id": uid,
        "owner_club": club,
        "target_id": target_id,
        "status": "pending"
    }
    save_data()

    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"accept_transfer_{transfer_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_transfer_{transfer_id}")
        ]
    ]

    try:
        await context.bot.send_message(
            target_id,
            f"📢 Вам предложили трансфер в клуб {club}!\n\n"
            f"От: {users[uid]['nickname']}\n"
            f"Клуб: {club}\n\n"
            f"Хотите присоединиться?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text(
            f"✅ Запрос на трансфер отправлен игроку {users[target_id]['nickname']}. Ожидайте ответа."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить запрос игроку: {e}")


# ==================== ОБРАБОТЧИКИ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Этот бот работает только в личных сообщениях. Пожалуйста, используйте /start в ЛС с ботом.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid in users:
            update_username(uid, update.effective_user.username or "no_username")

        if is_banned(uid):
            await update.message.reply_text("🚫 Вы забанены")
            return ConversationHandler.END
        if uid in users:
            nickname = users[uid]['nickname']
            await update.message.reply_text(f"👋 С возвращением {nickname}, выберите что вас интересует!", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END
        await update.message.reply_text(
            f"👋 Введи ник (только английские буквы, цифры и символ _, минимум {MIN_NICKNAME_LENGTH} символа):")
        return REGISTER_NICKNAME
    except Exception as e:
        logger.error(f"Ошибка в start для пользователя {update.effective_user.id if update.effective_user else 'unknown'}: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def register_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Эта команда доступна только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        nickname = update.message.text.strip()

        is_valid, error_message = is_valid_nickname(nickname)
        if not is_valid:
            await update.message.reply_text(f"{error_message}\nПопробуй еще раз:")
            return REGISTER_NICKNAME

        if is_nickname_taken(nickname):
            await update.message.reply_text("❌ Этот ник уже занят другим игроком\nПопробуй другой ник:")
            return REGISTER_NICKNAME

        username = update.effective_user.username or "no_username"
        users[uid] = {
            "nickname": nickname,
            "username": username,
            "free_agent": True,
            "club": None,
            "retired": False,
            "retire_date": None,
            "last_free_agent_date": None,
            "last_custom_text_date": None,
            "privilege": "player",
            "reg_date": datetime.now(),
            "last_nickname_change_date": None,
            "last_request_time": None
        }
        save_data()
        await update.message.reply_text(f"✅ Регистрация завершена, {nickname}!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в register_nickname: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Ошибка при регистрации. Попробуйте /start заново.")
        return ConversationHandler.END


async def set_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in MODERATORS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /set_owner ID_пользователя Название клуба")
        return ConversationHandler.END

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return ConversationHandler.END

    club_name = " ".join(context.args[1:]).strip('"')

    if club_name not in CLUBS:
        await update.message.reply_text(f"❌ Клуб не найден")
        return ConversationHandler.END

    if target_id not in users:
        await update.message.reply_text(f"❌ Пользователь с ID {target_id} не найден")
        return ConversationHandler.END

    old_owner_id = clubs_data[club_name]["owner_id"]
    if old_owner_id and old_owner_id in TEAM_OWNERS:
        del TEAM_OWNERS[old_owner_id]

    TEAM_OWNERS[target_id] = club_name
    clubs_data[club_name]["owner_id"] = target_id
    clubs_data[club_name]["status"] = "active"
    clubs_data[club_name]["closed_date"] = None
    save_data()
    await update.message.reply_text(f"✅ Владелец назначен!")
    return ConversationHandler.END


# ==================== КНОПКИ ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    try:
        # Сначала обрабатываем действия, которые должны работать в любом чате (например, в группе модерации)
        if data.startswith("approve_"):
            await moderation_approve(update, context)
            return ConversationHandler.END
        if data.startswith("reject_"):
            post_id = int(data.split("_")[1])
            context.user_data["reject_post_id"] = post_id
            await q.edit_message_text("📝 Напиши причину отклонения заявки:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_REJECT_REASON

        # Теперь проверяем, что остальные действия выполняются только в личных сообщениях
        if not is_private_chat(update):
            await q.edit_message_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        if uid in users:
            update_username(uid, q.from_user.username or "no_username")

        if uid not in users:
            await q.edit_message_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        if is_banned(uid) and data != "profile":
            await q.edit_message_text("🚫 Вы забанены")
            return ConversationHandler.END

        if users[uid].get("retired") and data not in ["profile", "resume", "back_to_main", "suggest_idea"]:
            await q.edit_message_text(
                "❌ Вы завершили карьеру. Чтобы создавать заявки, сначала возобновите карьеру.",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        if data == "free_agent":
            # Глобальный КД
            ok_req, msg_req = check_request_cooldown(uid)
            if not ok_req:
                await q.edit_message_text(f"❌ Слишком частые заявки!\n{msg_req}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            # Специфичный КД (проверка, но не установка)
            ok, msg = check_free_agent_cooldown(uid)
            if not ok:
                await q.edit_message_text(f"❌ {msg}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            await q.edit_message_text("📝 Напиши комментарий:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_FREE_AGENT_COMMENT

        elif data == "custom_text":
            ok_req, msg_req = check_request_cooldown(uid)
            if not ok_req:
                await q.edit_message_text(f"❌ Слишком частые заявки!\n{msg_req}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok, msg = check_custom_text_cooldown(uid)
            if not ok:
                await q.edit_message_text(f"❌ {msg}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            await q.edit_message_text("📝 Напиши свой текст:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_CUSTOM_TEXT

        elif data == "profile":
            await q.edit_message_text(format_profile(users[uid], uid), parse_mode='MarkdownV2',
                                      reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        elif data == "change_nickname":
            if users[uid].get("retired"):
                await q.edit_message_text("❌ Вы завершили карьеру. Смена ника недоступна.",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok_req, msg_req = check_request_cooldown(uid)
            if not ok_req:
                await q.edit_message_text(f"❌ Слишком частые заявки!\n{msg_req}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok, msg = check_nickname_change_cooldown(uid)
            if not ok:
                await q.edit_message_text(f"❌ Сменить ник можно раз в {NICKNAME_CHANGE_COOLDOWN_DAYS} дней.\n{msg}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            await q.edit_message_text(
                f"✏️ Введи новый ник (только английские буквы, цифры и символ _, минимум {MIN_NICKNAME_LENGTH} символа):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_NEW_NICKNAME

        elif data == "retire":
            if users[uid].get("retired"):
                await q.edit_message_text("❌ Ты уже завершил карьеру", reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok_req, msg_req = check_request_cooldown(uid)
            if not ok_req:
                await q.edit_message_text(f"❌ Слишком частые заявки!\n{msg_req}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            await q.edit_message_text("📝 Напиши комментарий к завершению карьеры:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_RETIRE_COMMENT

        elif data == "resume":
            if not users[uid].get("retired"):
                await q.edit_message_text("❌ Ты не завершал карьеру", reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok_req, msg_req = check_request_cooldown(uid)
            if not ok_req:
                await q.edit_message_text(f"❌ Слишком частые заявки!\n{msg_req}",
                                          reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            ok, msg = check_resume_cooldown(uid)
            if not ok:
                await q.edit_message_text(f"❌ {msg}", reply_markup=get_main_keyboard(uid))
                return ConversationHandler.END
            await q.edit_message_text("📝 Напиши комментарий к возвращению:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_RESUME_COMMENT

        elif data == "transfer" and uid in TEAM_OWNERS:
            club = TEAM_OWNERS[uid]
            if clubs_data[club]["status"] == "closed":
                await q.edit_message_text(
                    "❌ Ваш клуб закрыт. Трансферы недоступны.",
                    reply_markup=get_main_keyboard(uid)
                )
                return ConversationHandler.END

            if len(clubs_data[club]["players"]) >= MAX_CLUB_MEMBERS:
                await q.edit_message_text(
                    f"❌ В вашем клубе уже максимальное количество игроков ({MAX_CLUB_MEMBERS}).\n"
                    f"Чтобы пригласить нового игрока, нужно кого-то удалить.",
                    reply_markup=get_main_keyboard(uid)
                )
                return ConversationHandler.END

            await q.edit_message_text(
                f"🔄 Введи ник игрока (только английские буквы, цифры и символ _, минимум {MIN_NICKNAME_LENGTH} символа), которому хочешь предложить трансфер в {club}:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]])
            )
            context.user_data["transfer_club"] = club
            return WAITING_FOR_TRANSFER_NICKNAME

        elif data.startswith("accept_transfer_"):
            transfer_id = int(data.split("_")[2])
            if transfer_id not in pending_transfers:
                await q.edit_message_text("❌ Этот запрос уже обработан")
                return ConversationHandler.END

            transfer = pending_transfers[transfer_id]
            if transfer["target_id"] != uid:
                await q.edit_message_text("❌ Это не ваш запрос")
                return ConversationHandler.END

            if clubs_data[transfer['owner_club']]["status"] == "closed":
                await q.edit_message_text(
                    "❌ Клуб закрыт. Трансфер невозможен.",
                    reply_markup=get_main_keyboard(uid)
                )
                try:
                    await context.bot.send_message(
                        transfer["owner_id"],
                        f"❌ Игрок {users[uid]['nickname']} не может принять трансфер, так как клуб закрыт."
                    )
                except:
                    pass
                del pending_transfers[transfer_id]
                save_data()
                return ConversationHandler.END

            if len(clubs_data[transfer['owner_club']]["players"]) >= MAX_CLUB_MEMBERS:
                await q.edit_message_text(
                    f"❌ В клубе {transfer['owner_club']} уже максимальное количество игроков ({MAX_CLUB_MEMBERS}).\n"
                    f"Трансфер невозможен.",
                    reply_markup=get_main_keyboard(uid)
                )
                try:
                    await context.bot.send_message(
                        transfer["owner_id"],
                        f"❌ Игрок {users[uid]['nickname']} не может принять трансфер, так как в клубе {transfer['owner_club']} нет мест."
                    )
                except:
                    pass
                del pending_transfers[transfer_id]
                save_data()
                return ConversationHandler.END

            context.user_data["transfer_id"] = transfer_id
            await q.edit_message_text("📝 Напиши комментарий к трансферу (почему хочешь перейти):",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_TRANSFER_COMMENT

        elif data.startswith("decline_transfer_"):
            transfer_id = int(data.split("_")[2])
            if transfer_id not in pending_transfers:
                await q.edit_message_text("❌ Этот запрос уже обработан")
                return ConversationHandler.END

            transfer = pending_transfers[transfer_id]
            if transfer["target_id"] != uid:
                await q.edit_message_text("❌ Это не ваш запрос")
                return ConversationHandler.END

            try:
                await context.bot.send_message(
                    transfer["owner_id"],
                    f"❌ Игрок {users[uid]['nickname']} отклонил предложение о трансфере в {transfer['owner_club']}."
                )
            except:
                pass

            del pending_transfers[transfer_id]
            save_data()
            await q.edit_message_text("❌ Ты отклонил предложение о трансфере", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        elif data == "manage_club" and uid in TEAM_OWNERS:
            club = TEAM_OWNERS[uid]
            club_status = clubs_data[club].get("status", "active")
            await q.edit_message_text(
                f"🏢 Управление клубом {club}",
                reply_markup=get_manage_club_keyboard(club, club_status)
            )
            return ConversationHandler.END

        elif data.startswith("close_club_"):
            club = data.replace("close_club_", "")
            if uid not in TEAM_OWNERS or TEAM_OWNERS[uid] != club:
                await q.edit_message_text("❌ У вас нет прав на управление этим клубом")
                return ConversationHandler.END

            keyboard = [
                [
                    InlineKeyboardButton("✅ Да, закрыть", callback_data=f"confirm_close_club_{club}"),
                    InlineKeyboardButton("❌ Нет, отмена", callback_data="manage_club")
                ]
            ]
            await q.edit_message_text(
                f"⚠️ Вы уверены, что хотите **закрыть клуб {club}**?\n\n"
                f"После закрытия:\n"
                f"• Вы потеряете права владельца клуба\n"
                f"• Все игроки клуба станут свободными агентами\n"
                f"• Кнопки трансфера исчезнут\n"
                f"• Только модератор сможет назначить нового владельца",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ConversationHandler.END

        elif data.startswith("confirm_close_club_"):
            club = data.replace("confirm_close_club_", "")
            if uid not in TEAM_OWNERS or TEAM_OWNERS[uid] != club:
                await q.edit_message_text("❌ У вас нет прав на управление этим клубом")
                return ConversationHandler.END

            players_in_club = clubs_data[club]["players"].copy()

            for pid in players_in_club:
                if pid in users:
                    users[pid]["club"] = None
                    users[pid]["free_agent"] = True

            clubs_data[club]["status"] = "closed"
            clubs_data[club]["closed_date"] = datetime.now()
            clubs_data[club]["players"] = []

            if uid in TEAM_OWNERS:
                del TEAM_OWNERS[uid]

            clubs_data[club]["owner_id"] = None
            save_data()

            await q.edit_message_text(
                f"🔴 Клуб {club} успешно закрыт!\n\n"
                f"Вы больше не являетесь владельцем клуба.\n"
                f"Все игроки ({len(players_in_club)}) стали свободными агентами.\n"
                f"Кнопки управления клубом и трансферов будут скрыты.",
                reply_markup=get_main_keyboard(uid)
            )

            # Уведомление модераторов
            try:
                await context.bot.send_message(
                    MODERATION_CHAT_ID,
                    f"🔔 Клуб **{club}** закрыт владельцем @{users[uid]['username']}\n"
                    f"Освобождено игроков: {len(players_in_club)}"
                )
            except:
                pass

            for pid in players_in_club:
                try:
                    await context.bot.send_message(
                        pid,
                        f"🔴 Клуб **{club}**, в котором вы состояли, был закрыт владельцем.\n"
                        f"Теперь вы свободный агент.",
                        parse_mode='Markdown'
                    )
                except:
                    pass

            return ConversationHandler.END

        elif data.startswith("club_players_"):
            club = data.replace("club_players_", "")
            players = []
            for pid in clubs_data[club]["players"]:
                if pid in users:
                    players.append((pid, users[pid]))
            if not players:
                await q.edit_message_text("❌ В клубе нет игроков",
                                          reply_markup=get_manage_club_keyboard(club, clubs_data[club]["status"]))
                return ConversationHandler.END

            members_count = len(players)
            members_info = f"({members_count}/{MAX_CLUB_MEMBERS})"

            kb = []
            for pid, ud in players[:10]:
                cd_info = ""
                if pid in clubs_data[club]["transfer_cooldowns"]:
                    cd_date = clubs_data[club]["transfer_cooldowns"][pid]
                    if datetime.now() - cd_date < get_cooldown_delta(pid, "transfer"):
                        remaining = get_cooldown_delta(pid, "transfer") - (datetime.now() - cd_date)
                        cd_info = f" ⏳{remaining.seconds // 3600}ч"
                privilege_emoji = get_user_privilege_emoji(ud)
                kb.append([InlineKeyboardButton(f"❌ {privilege_emoji} {ud['nickname'][:15]}{cd_info}",
                                                callback_data=f"kick_player_{pid}_{club}")])
            kb.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_club")])
            await q.edit_message_text(f"👥 Выбери игрока для удаления {members_info}:",
                                      reply_markup=InlineKeyboardMarkup(kb))
            return ConversationHandler.END

        elif data.startswith("kick_player_"):
            parts = data.split("_")
            pid = int(parts[2])
            club = "_".join(parts[3:])
            if pid in clubs_data[club]["players"]:
                clubs_data[club]["players"].remove(pid)
                users[pid]["club"] = None
                users[pid]["free_agent"] = True
                save_data()
                await q.edit_message_text(f"✅ Игрок {users[pid]['nickname']} удален из клуба",
                                          reply_markup=get_manage_club_keyboard(club, clubs_data[club]["status"]))
            return ConversationHandler.END

        elif data.startswith("club_profile_"):
            club = data.replace("club_profile_", "")
            await q.edit_message_text(await format_club_profile(club, clubs_data[club]), parse_mode='Markdown',
                                      reply_markup=get_manage_club_keyboard(club, clubs_data[club]["status"]))
            return ConversationHandler.END

        elif data == "moderator_panel" and uid in MODERATORS:
            await q.edit_message_text("🛠 Панель модератора:", reply_markup=get_moderator_keyboard())
            return ConversationHandler.END

        elif data == "mod_ban" and uid in MODERATORS:
            await q.edit_message_text("🚫 Введи @username и причину через пробел:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_BAN_REASON

        elif data == "mod_unban" and uid in MODERATORS:
            if not banned_users:
                await q.edit_message_text("✅ Нет забаненных пользователей", reply_markup=get_moderator_keyboard())
                return ConversationHandler.END
            kb = []
            for bid in list(banned_users.keys())[:10]:
                if bid in users:
                    privilege_emoji = get_user_privilege_emoji(users[bid])
                    kb.append([InlineKeyboardButton(f"✅ {privilege_emoji} {users[bid]['nickname']}",
                                                    callback_data=f"unban_{bid}")])
            kb.append([InlineKeyboardButton("🔙 Назад", callback_data="moderator_panel")])
            await q.edit_message_text("Выбери пользователя для разбана:", reply_markup=InlineKeyboardMarkup(kb))
            return ConversationHandler.END

        elif data.startswith("unban_") and uid in MODERATORS:
            bid = int(data.split("_")[1])
            if bid in banned_users:
                del banned_users[bid]
                save_data()
                await q.edit_message_text("✅ Пользователь разбанен", reply_markup=get_moderator_keyboard())
            return ConversationHandler.END

        elif data == "mod_ban_list" and uid in MODERATORS:
            if not banned_users:
                await q.edit_message_text("✅ Нет забаненных пользователей", reply_markup=get_moderator_keyboard())
                return ConversationHandler.END
            text = "📋 Список забаненных:\n"
            for bid, bd in banned_users.items():
                if bid in users:
                    privilege_emoji = get_user_privilege_emoji(users[bid])
                    text += f"\n• {privilege_emoji} {users[bid]['nickname']}: {bd['reason']} ({bd['date'].strftime('%d.%m.%Y')})"
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Назад", callback_data="moderator_panel")]]))
            return ConversationHandler.END

        elif data == "mod_reset_cd" and uid in MODERATORS:
            await q.edit_message_text("🔄 Введи @username для сброса КД:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="moderator_panel")]]))
            return WAITING_FOR_RESET_CD_USER

        elif data == "mod_force_retire" and uid in MODERATORS:
            await q.edit_message_text("⚡ Введи @username для сброса КД на возвращение карьеры:",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Отмена", callback_data="moderator_panel")]]))
            return WAITING_FOR_RETIRE_COMMENT

        elif data == "mod_give_privilege" and uid in MODERATORS:
            await q.edit_message_text("👑 Введи @username и привилегию (player/vip/owner) через пробел:",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Отмена", callback_data="moderator_panel")]]))
            return WAITING_FOR_PRIVILEGE_USER

        elif data == "back_to_main":
            await q.edit_message_text("Главное меню:", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        elif data == "ignore":
            return ConversationHandler.END

        elif data == "suggest_idea":
            await q.edit_message_text(
                "💡 Напиши свою идею или предложение по улучшению бота:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]])
            )
            return WAITING_FOR_IDEA_TEXT

        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в button_handler: {e}", exc_info=True)
        await q.edit_message_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


# ==================== ТЕКСТ ====================
async def handle_free_agent_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Вы завершили карьеру. Чтобы создавать заявки, сначала возобновите карьеру.",
                                            reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        # Глобальный КД (повторная проверка на случай обхода через старый callback)
        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        comment = escape_html(update.message.text)
        privilege = format_privilege_for_post(users[uid])
        post = f"<b>📢 Свободный агент:</b>\n\n🔘 {privilege} <b>{users[uid]['nickname']}</b> (@{users[uid]['username']}) — Ищет клуб.\nКомментарий: {comment}"
        post = truncate_text(post)

        # Устанавливаем глобальный КД (специфичный будет установлен при одобрении)
        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "free_agent", uid)
        await update.message.reply_text("✅ Заявка отправлена на модерацию!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_free_agent_comment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_custom_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Вы завершили карьеру. Чтобы создавать заявки, сначала возобновите карьеру.",
                                            reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        text = escape_html(update.message.text)
        privilege = format_privilege_for_post(users[uid])
        post = f"<b>📝 Свой текст:</b>\n\n{privilege} <b>{users[uid]['nickname']}</b>\n{text}"
        post = truncate_text(post)

        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "custom", uid)
        await update.message.reply_text("✅ Заявка отправлена на модерацию!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_custom_text: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_new_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Вы завершили карьеру. Смена ника недоступна.",
                                            reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        new_nickname = update.message.text.strip()

        is_valid, error_message = is_valid_nickname(new_nickname)
        if not is_valid:
            await update.message.reply_text(f"{error_message}\nПопробуй еще раз:", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_NEW_NICKNAME

        if is_nickname_taken(new_nickname, uid):
            await update.message.reply_text("❌ Этот ник уже занят другим игроком\nПопробуй другой ник:",
                                            reply_markup=InlineKeyboardMarkup(
                                                [[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]))
            return WAITING_FOR_NEW_NICKNAME

        old_nickname = users[uid]['nickname']
        privilege = format_privilege_for_post(users[uid])
        post = f"<b>❗️ Смена никнейма в тм:</b>\n\n🔘 {privilege} @{users[uid]['username']} — <b>{old_nickname}</b> ➡️ <b>{new_nickname}</b>"
        post = truncate_text(post)

        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "nickname_change", uid,
                                 {"new_nickname": new_nickname, "old_nickname": old_nickname})

        await update.message.reply_text("✅ Заявка на смену никнейма отправлена на модерацию!",
                                        reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_new_nickname: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_retire_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id

        if uid in users:
            update_username(uid, update.effective_user.username or "no_username")

        if uid in MODERATORS and context.user_data.get("force_retire"):
            username = update.message.text.strip().replace('@', '')
            target_id = None
            for uid2, user_data in users.items():
                if user_data['username'] == username:
                    target_id = uid2
                    break
            if target_id:
                users[target_id]["retire_date"] = None
                save_data()
                await update.message.reply_text(f"✅ КД на возвращение карьеры сброшен для @{username}",
                                                reply_markup=get_moderator_keyboard())
            else:
                await update.message.reply_text("❌ Игрок не найден", reply_markup=get_moderator_keyboard())
            context.user_data["force_retire"] = False
            return ConversationHandler.END

        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Ты уже завершил карьеру", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        comment = escape_html(update.message.text)
        privilege = format_privilege_for_post(users[uid])
        post = f"<b>🥀 Завершение карьеры в тм:</b>\n\n🔘 {privilege} <b>{users[uid]['nickname']}</b> (@{users[uid]['username']}) — Завершает.\nКомментарий: {comment}"
        post = truncate_text(post)

        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "retire", uid)
        await update.message.reply_text("✅ Заявка отправлена на модерацию!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_retire_comment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_resume_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        if not users[uid].get("retired"):
            await update.message.reply_text("❌ Ты не завершал карьеру", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        comment = escape_html(update.message.text)
        privilege = format_privilege_for_post(users[uid])
        post = f"<b>🌹 Возвращение карьеры в тм:</b>\n\n🔘 {privilege} <b>{users[uid]['nickname']}</b> (@{users[uid]['username']}) — Возвращается.\nКомментарий: {comment}"
        post = truncate_text(post)

        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "resume", uid)
        await update.message.reply_text("✅ Заявка отправлена на модерацию!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_resume_comment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_transfer_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Вы завершили карьеру. Трансферы недоступны.",
                                            reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        if uid not in TEAM_OWNERS:
            await update.message.reply_text("❌ У вас нет прав владельца клуба")
            return ConversationHandler.END

        nickname = update.message.text.strip()
        club = context.user_data.get("transfer_club")

        if not club:
            await update.message.reply_text("❌ Ошибка, начни заново", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        if clubs_data[club]["status"] == "closed":
            await update.message.reply_text(
                "❌ Ваш клуб закрыт. Трансферы недоступны.",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        if len(clubs_data[club]["players"]) >= MAX_CLUB_MEMBERS:
            await update.message.reply_text(
                f"❌ В вашем клубе уже максимальное количество игроков ({MAX_CLUB_MEMBERS}).\n"
                f"Чтобы пригласить нового игрока, нужно кого-то удалить.",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        is_valid, error_message = is_valid_nickname(nickname)
        if not is_valid:
            await update.message.reply_text(
                f"{error_message}\nПопробуй еще раз:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]])
            )
            return WAITING_FOR_TRANSFER_NICKNAME

        target_id = find_user_by_nickname(nickname)

        if not target_id:
            await update.message.reply_text(
                f"❌ Игрок с ником '{nickname}' не найден\nПроверь правильность написания или попробуй другой ник:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]])
            )
            return WAITING_FOR_TRANSFER_NICKNAME

        if is_banned(target_id):
            await update.message.reply_text(
                "❌ Этот игрок забанен и не может участвовать в трансферах",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        if users[target_id].get("retired"):
            await update.message.reply_text(
                f"❌ Игрок {users[target_id]['nickname']} завершил карьеру и не может участвовать в трансферах",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        if target_id in clubs_data[club]["players"]:
            await update.message.reply_text(
                f"❌ Игрок {users[target_id]['nickname']} уже в вашем клубе",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        if not users[target_id].get("free_agent"):
            current_club = users[target_id].get("club")
            if current_club:
                await update.message.reply_text(
                    f"❌ Игрок {users[target_id]['nickname']} уже в клубе {current_club}.\n"
                    f"Предложение о трансфере можно отправить только свободному агенту.",
                    reply_markup=get_main_keyboard(uid)
                )
                return ConversationHandler.END

        ok, msg = check_cooldown(target_id, club)
        if not ok:
            await update.message.reply_text(
                f"❌ У игрока ещё КД {msg}",
                reply_markup=get_main_keyboard(uid)
            )
            return ConversationHandler.END

        transfer_id = len(pending_transfers) + 1
        pending_transfers[transfer_id] = {
            "owner_id": uid,
            "owner_club": club,
            "target_id": target_id,
            "status": "pending"
        }
        save_data()

        keyboard = [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_transfer_{transfer_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_transfer_{transfer_id}")
            ]
        ]

        try:
            await context.bot.send_message(
                target_id,
                f"📢 Вам предложили трансфер в клуб {club}!\n\n"
                f"От: {users[uid]['nickname']}\n"
                f"Клуб: {club}\n\n"
                f"Хотите присоединиться?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await update.message.reply_text(
                f"✅ Запрос на трансфер отправлен игроку {users[target_id]['nickname']}. Ожидайте ответа.",
                reply_markup=get_main_keyboard(uid)
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Не удалось отправить запрос игроку: {e}",
                reply_markup=get_main_keyboard(uid)
            )

        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_transfer_nickname: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_transfer_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id

        if uid in users:
            update_username(uid, update.effective_user.username or "no_username")

        if users[uid].get("retired"):
            await update.message.reply_text("❌ Вы завершили карьеру. Трансферы недоступны.",
                                            reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        transfer_id = context.user_data.get("transfer_id")
        if not transfer_id or transfer_id not in pending_transfers:
            await update.message.reply_text("❌ Ошибка, начни заново", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        transfer = pending_transfers[transfer_id]
        if transfer["target_id"] != uid:
            await update.message.reply_text("❌ Это не ваш запрос", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        if clubs_data[transfer['owner_club']]["status"] == "closed":
            await update.message.reply_text(
                "❌ Клуб закрыт. Трансфер невозможен.",
                reply_markup=get_main_keyboard(uid)
            )
            try:
                await context.bot.send_message(
                    transfer["owner_id"],
                    f"❌ Игрок {users[uid]['nickname']} не может принять трансфер, так как клуб закрыт."
                )
            except:
                pass
            del pending_transfers[transfer_id]
            save_data()
            return ConversationHandler.END

        if len(clubs_data[transfer['owner_club']]["players"]) >= MAX_CLUB_MEMBERS:
            await update.message.reply_text(
                f"❌ В клубе {transfer['owner_club']} уже максимальное количество игроков ({MAX_CLUB_MEMBERS}).\n"
                f"Трансфер невозможен.",
                reply_markup=get_main_keyboard(uid)
            )
            try:
                await context.bot.send_message(
                    transfer["owner_id"],
                    f"❌ Игрок {users[uid]['nickname']} не может принять трансфер, так как в клубе {transfer['owner_club']} нет мест."
                )
            except:
                pass
            del pending_transfers[transfer_id]
            save_data()
            return ConversationHandler.END

        ok_req, msg_req = check_request_cooldown(uid)
        if not ok_req:
            await update.message.reply_text(f"❌ Слишком частые заявки!\n{msg_req}", reply_markup=get_main_keyboard(uid))
            return ConversationHandler.END

        comment = escape_html(update.message.text)
        privilege = format_privilege_for_post(users[uid])

        post = f"<b>📢 Трансфер в клуб:</b>\n\n🔘 {privilege} <b>{users[uid]['nickname']}</b> (@{users[uid]['username']}) ➡️ {transfer['owner_club']}\nКомментарий: {comment}"
        post = truncate_text(post)

        users[uid]["last_request_time"] = datetime.now()
        save_data()

        await send_to_moderation(update, context, post, "transfer", uid, {
            "target": uid,
            "club": transfer['owner_club'],
            "owner_id": transfer['owner_id']
        })

        try:
            await context.bot.send_message(
                transfer['owner_id'],
                f"✅ Игрок {users[uid]['nickname']} принял предложение о трансфере в {transfer['owner_club']}!\n"
                f"Заявка отправлена на модерацию."
            )
        except:
            pass

        del pending_transfers[transfer_id]
        save_data()
        context.user_data["transfer_id"] = None

        await update.message.reply_text("✅ Заявка отправлена на модерацию!", reply_markup=get_main_keyboard(uid))
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_transfer_comment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


async def handle_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MODERATORS:
        return ConversationHandler.END
    text = update.message.text.strip()
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Формат: @username причина")
        return ConversationHandler.END
    username, reason = parts[0], parts[1]
    target_id = None
    for uid, ud in users.items():
        if f"@{ud['username']}" == username:
            target_id = uid
            break
    if not target_id:
        await update.message.reply_text("❌ Игрок не найден")
        return ConversationHandler.END
    banned_users[target_id] = {"reason": reason, "date": datetime.now()}
    save_data()
    await update.message.reply_text(f"✅ {username} забанен")
    return ConversationHandler.END


async def handle_reset_cd_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MODERATORS:
        return ConversationHandler.END
    username = update.message.text.strip().replace('@', '')
    target_id = None
    for uid, user_data in users.items():
        if user_data['username'] == username:
            target_id = uid
            break
    if not target_id:
        await update.message.reply_text("❌ Игрок не найден", reply_markup=get_moderator_keyboard())
        return ConversationHandler.END
    for club in clubs_data:
        if target_id in clubs_data[club]["transfer_cooldowns"]:
            del clubs_data[club]["transfer_cooldowns"][target_id]
    if target_id in users:
        if "last_free_agent_date" in users[target_id]:
            del users[target_id]["last_free_agent_date"]
        if "last_custom_text_date" in users[target_id]:
            del users[target_id]["last_custom_text_date"]
        if "last_nickname_change_date" in users[target_id]:
            del users[target_id]["last_nickname_change_date"]
        if "last_request_time" in users[target_id]:
            del users[target_id]["last_request_time"]
    save_data()
    await update.message.reply_text(f"✅ КД сброшены для @{username}", reply_markup=get_moderator_keyboard())
    return ConversationHandler.END


async def handle_privilege_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MODERATORS:
        return ConversationHandler.END
    text = update.message.text.strip()
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await update.message.reply_text("❌ Формат: @username player/vip/owner")
        return ConversationHandler.END

    username = parts[0].replace('@', '')
    privilege = parts[1].lower()

    if privilege not in ["player", "vip", "owner"]:
        await update.message.reply_text("❌ Доступные привилегии: player, vip, owner")
        return ConversationHandler.END

    target_id = None
    for uid, user_data in users.items():
        if user_data['username'] == username:
            target_id = uid
            break

    if not target_id:
        await update.message.reply_text("❌ Игрок не найден")
        return ConversationHandler.END

    users[target_id]["privilege"] = privilege
    save_data()

    privilege_text = PRIVILEGES.get(privilege, "[Игрок]")
    await update.message.reply_text(f"✅ Игроку @{username} выдана привилегия {privilege_text}!",
                                    reply_markup=get_moderator_keyboard())

    try:
        await context.bot.send_message(
            target_id,
            f"🎉 Вам выдана привилегия {privilege_text}!"
        )
    except:
        pass

    return ConversationHandler.END


async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in MODERATORS:
        return ConversationHandler.END

    reason = update.message.text.strip()
    post_id = context.user_data.get("reject_post_id")

    if not post_id or post_id not in pending_posts:
        await update.message.reply_text("❌ Заявка уже обработана", reply_markup=get_moderator_keyboard())
        return ConversationHandler.END

    post = pending_posts[post_id]

    try:
        await context.bot.send_message(
            post["author_id"],
            f"❌ Ваша заявка отклонена\nПричина: {reason}"
        )
    except:
        pass

    # Не удаляем глобальный КД, так как он уже установлен при отправке заявки.
    # Специфичный КД не устанавливался, поэтому игрок может попробовать снова через 2 минуты.

    del pending_posts[post_id]
    save_data()
    del context.user_data["reject_post_id"]

    await update.message.reply_text(f"✅ Заявка #{post_id} отклонена с причиной", reply_markup=get_moderator_keyboard())
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in users:
        await update.message.reply_text("❌ Действие отменено", reply_markup=get_main_keyboard(uid))
    else:
        await update.message.reply_text("❌ Действие отменено")
    return ConversationHandler.END


# ==================== НОВЫЙ ОБРАБОТЧИК ИДЕЙ ====================
async def handle_idea_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_private_chat(update):
            await update.message.reply_text("🤖 Это действие доступно только в личных сообщениях.")
            return ConversationHandler.END

        uid = update.effective_user.id
        if uid not in users:
            await update.message.reply_text("❌ Зарегистрируйся через /start")
            return ConversationHandler.END

        update_username(uid, update.effective_user.username or "no_username")

        idea_text = escape_html(update.message.text)

        # Формируем сообщение для модераторов
        user_info = f"{get_user_privilege_text(users[uid])} {users[uid]['nickname']} (@{users[uid]['username']})"
        post = f"<b>💡 Предложение от пользователя</b>\n\n{user_info}\n\nТекст идеи:\n{idea_text}"
        post = truncate_text(post)

        # Отправляем в чат модерации (не сохраняем в pending_posts)
        try:
            await context.bot.send_message(MODERATION_CHAT_ID, post, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Ошибка отправки идеи в модерацию: {e}")

        await update.message.reply_text(
            "✅ Спасибо за идею! Мы рассмотрим её в ближайшее время.",
            reply_markup=get_main_keyboard(uid)
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_idea_text: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END


# ==================== КОМАНДЫ /club и /player ====================
async def club_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о клубе. Работает в любом чате."""
    try:
        args = context.args
        if args:
            club_name = " ".join(args).strip('"')
            if club_name in clubs_data:
                text = await format_club_profile(club_name, clubs_data[club_name])
                await update.message.reply_text(text, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Клуб '{club_name}' не найден. Доступные клубы:\n" + ", ".join(CLUBS))
        else:
            uid = update.effective_user.id
            if uid in users:
                club = users[uid].get("club")
                if club:
                    text = await format_club_profile(club, clubs_data[club])
                    await update.message.reply_text(text, parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Вы не состоите в клубе. Используйте /club <название клуба> для просмотра другого клуба.")
            else:
                await update.message.reply_text("❌ Вы не зарегистрированы. Зарегистрируйтесь через /start в ЛС с ботом.")
    except Exception as e:
        logger.error(f"Ошибка в /club: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при формировании профиля клуба. Попробуйте позже.")


async def player_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию об игроке. Работает в любом чате."""
    try:
        args = context.args
        if args:
            query = " ".join(args).strip()
            target_id = find_user_by_nickname(query)
            if not target_id:
                target_id = find_user_by_username(query.replace('@', ''))
            if target_id and target_id in users:
                user_data = users[target_id]
                text = format_player_info(user_data, target_id)
                await update.message.reply_text(text, parse_mode='MarkdownV2')
            else:
                await update.message.reply_text(f"❌ Игрок с ником или username '{query}' не найден.")
        else:
            uid = update.effective_user.id
            if uid in users:
                text = format_player_info(users[uid], uid)
                await update.message.reply_text(text, parse_mode='MarkdownV2')
            else:
                await update.message.reply_text("❌ Вы не зарегистрированы. Зарегистрируйтесь через /start в ЛС с ботом.")
    except Exception as e:
        logger.error(f"Ошибка в /player: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Произошла ошибка при формировании профиля игрока. Попробуйте позже.")


# ==================== МОДЕРАЦИЯ ====================
async def send_to_moderation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, post_type: str,
                             author_id: int, extra_data: dict = None):
    post_id = len(pending_posts) + 1
    keyboard = [[InlineKeyboardButton("✅ Принять", callback_data=f"approve_{post_id}"),
                 InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{post_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await context.bot.send_message(MODERATION_CHAT_ID, f"🔔 Новая заявка #{post_id}\n\n{text}",
                                           reply_markup=reply_markup, parse_mode='HTML')
            pending_posts[post_id] = {"text": text, "type": post_type, "author_id": author_id,
                                      "extra_data": extra_data or {}}
            save_data()
            logger.info(f"📬 Заявка #{post_id} отправлена на модерацию")
            return
        except Exception as e:
            logger.error(f"❌ Ошибка отправки заявки #{post_id} (попытка {attempt+1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                await update.message.reply_text("❌ Ошибка отправки на модерацию. Повторите попытку позже.")
                raise


async def moderation_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    post_id = int(data.split("_")[1])

    if query.from_user.id not in MODERATORS:
        await query.edit_message_text("❌ У вас нет прав модератора")
        return

    if post_id not in pending_posts:
        await query.edit_message_text("❌ Заявка уже обработана")
        return

    post = pending_posts[post_id]

    try:
        if post["type"] == "free_agent" and post["author_id"] in users:
            old_club = users[post["author_id"]].get("club")
            if old_club and old_club in clubs_data:
                if post["author_id"] in clubs_data[old_club]["players"]:
                    clubs_data[old_club]["players"].remove(post["author_id"])
            users[post["author_id"]]["club"] = None
            users[post["author_id"]]["free_agent"] = True

        if post["type"] == "retire" and post["author_id"] in users:
            owner_id = post["author_id"]
            if owner_id in TEAM_OWNERS:
                club_name = TEAM_OWNERS[owner_id]
                players_in_club = clubs_data[club_name]["players"].copy()
                for pid in players_in_club:
                    if pid in users:
                        users[pid]["club"] = None
                        users[pid]["free_agent"] = True
                clubs_data[club_name]["status"] = "closed"
                clubs_data[club_name]["closed_date"] = datetime.now()
                clubs_data[club_name]["players"] = []
                del TEAM_OWNERS[owner_id]
                clubs_data[club_name]["owner_id"] = None
                for pid in players_in_club:
                    try:
                        await context.bot.send_message(
                            pid,
                            f"🔴 Клуб **{club_name}** был закрыт, так как его владелец завершил карьеру.\n"
                            f"Теперь вы свободный агент.",
                            parse_mode='Markdown'
                        )
                    except:
                        pass

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await context.bot.send_message(CHANNEL_ID, post["text"], parse_mode='HTML')
                break
            except Exception as e:
                logger.error(f"❌ Ошибка публикации в канал (попытка {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise

        # Установка специфичных КД после одобрения
        if post["type"] == "free_agent":
            users[post["author_id"]]["last_free_agent_date"] = datetime.now()
        elif post["type"] == "custom":
            users[post["author_id"]]["last_custom_text_date"] = datetime.now()
        elif post["type"] == "nickname_change":
            new_nickname = post["extra_data"].get("new_nickname")
            users[post["author_id"]]["nickname"] = new_nickname
            users[post["author_id"]]["last_nickname_change_date"] = datetime.now()
        elif post["type"] == "retire":
            users[post["author_id"]]["retired"] = True
            users[post["author_id"]]["retire_date"] = datetime.now()
        elif post["type"] == "resume":
            users[post["author_id"]]["retired"] = False
            # retire_date не сбрасываем, остаётся для КД возврата
        elif post["type"] == "transfer":
            target = post["extra_data"].get("target")
            club = post["extra_data"].get("club")
            owner_id = post["extra_data"].get("owner_id")
            if target in users and club in clubs_data:
                old_club = users[target].get("club")
                if old_club and old_club in clubs_data:
                    if target in clubs_data[old_club]["players"]:
                        clubs_data[old_club]["players"].remove(target)
                users[target]["club"] = club
                users[target]["free_agent"] = False
                if target not in clubs_data[club]["players"]:
                    clubs_data[club]["players"].append(target)
                clubs_data[club]["transfer_cooldowns"][target] = datetime.now()
                if owner_id:
                    try:
                        await context.bot.send_message(
                            owner_id,
                            f"✅ Трансфер игрока {users[target]['nickname']} в {club} одобрен!"
                        )
                    except:
                        pass

        save_data()
        await query.edit_message_text(f"✅ Заявка #{post_id} опубликована!")

        try:
            await context.bot.send_message(post["author_id"], "✅ Ваша заявка опубликована!")
        except:
            pass

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await query.edit_message_text(f"❌ Ошибка при публикации")

    del pending_posts[post_id]
    save_data()


# ==================== MAIN ====================
def main():
    load_data()

    print("✅ Бот запускается...")
    print(f"📢 Токен: {BOT_TOKEN[:10]}...")
    print(f"📢 ID группы модерации: {MODERATION_CHAT_ID}")
    print(f"📢 ID канала: {CHANNEL_ID}")
    print(f"📢 Максимальное количество игроков в клубе: {MAX_CLUB_MEMBERS}")
    print(f"📢 Минимальная длина ника: {MIN_NICKNAME_LENGTH}")

    try:
        app = Application.builder().token(BOT_TOKEN).build()
        print("✅ Токен принят!")

        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
                CommandHandler("closemyclub", close_my_club),
                CommandHandler("transfer_player", transfer_player),
                CallbackQueryHandler(button_handler,
                                     pattern="^(free_agent|custom_text|retire|resume|change_nickname|transfer|accept_transfer_.*|mod_ban|mod_reset_cd|mod_force_retire|mod_give_privilege|reject_.*|suggest_idea)$")
            ],
            states={
                REGISTER_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_nickname)],
                WAITING_FOR_FREE_AGENT_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_agent_comment)],
                WAITING_FOR_CUSTOM_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_text)],
                WAITING_FOR_NEW_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_nickname)],
                WAITING_FOR_RETIRE_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_retire_comment)],
                WAITING_FOR_RESUME_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_resume_comment)],
                WAITING_FOR_TRANSFER_COMMENT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_comment)],
                WAITING_FOR_TRANSFER_NICKNAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_nickname)],
                WAITING_FOR_BAN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ban_reason)],
                WAITING_FOR_RESET_CD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reset_cd_user)],
                WAITING_FOR_PRIVILEGE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_privilege_user)],
                WAITING_FOR_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reject_reason)],
                WAITING_FOR_CLUB_CLOSE_CONFIRM: [],
                WAITING_FOR_IDEA_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_idea_text)],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^back_to_main$")
            ],
        )

        app.add_handler(conv_handler)

        app.add_handler(CallbackQueryHandler(button_handler,
                                             pattern="^(profile|manage_club|club_players_.*|club_profile_.*|kick_player_.*|moderator_panel|mod_unban|unban_.*|mod_ban_list|decline_transfer_.*|close_club_.*|confirm_close_club_.*|ignore|back_to_main)$"))

        app.add_handler(CallbackQueryHandler(moderation_approve, pattern="^approve_.*$"))

        app.add_handler(CommandHandler("set_owner", set_owner))
        app.add_handler(CommandHandler("reset_cds", reset_cds))
        app.add_handler(CommandHandler("force_retire", force_retire))
        app.add_handler(CommandHandler("give_privilege", give_privilege))
        app.add_handler(CommandHandler("close_club", close_club_command))

        app.add_handler(CommandHandler("club", club_command))
        app.add_handler(CommandHandler("player", player_command))
        app.add_handler(CommandHandler("transfer", transfer_command))

        print("✅ Бот готов к работе! Нажми Ctrl+C для остановки")
        app.run_polling()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
