
import os
import random
from datetime import datetime, timedelta, time, UTC

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime, text as sql_text
from sqlalchemy.orm import declarative_base, sessionmaker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ChatMemberHandler, ChatJoinRequestHandler, ContextTypes, filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")

PUBLIC_BIO_TAG = os.getenv("PUBLIC_BIO_TAG", "@antijavana").strip()
REQUIRE_BIO_TAG = os.getenv("REQUIRE_BIO_TAG", "true").lower() == "true"

KICK_AFTER_MINUTES = int(os.getenv("KICK_AFTER_MINUTES", "30"))
CONFIRM_AFTER_MINUTES = int(os.getenv("CONFIRM_AFTER_MINUTES", "30"))
PROOF_KICK_HOUR = int(os.getenv("PROOF_KICK_HOUR", "21"))
PROOF_KICK_MINUTE = int(os.getenv("PROOF_KICK_MINUTE", "50"))
REWARD_START_HOUR = int(os.getenv("REWARD_START_HOUR", "22"))
REWARD_START_MINUTE = int(os.getenv("REWARD_START_MINUTE", "5"))
LOCK_END_HOUR = int(os.getenv("LOCK_END_HOUR", "1"))
REWARD_DELETE_HOUR = int(os.getenv("REWARD_DELETE_HOUR", "0"))
REWARD_DELETE_MINUTE = int(os.getenv("REWARD_DELETE_MINUTE", "45"))
ADMIN_REWARD_REMINDER_HOURS = [int(x.strip()) for x in os.getenv("ADMIN_REWARD_REMINDER_HOURS", "12,18,21").split(",") if x.strip().isdigit()]
MIN_USERNAME_REQUIRED = os.getenv("MIN_USERNAME_REQUIRED", "true").lower() == "true"
SUSPICIOUS_REQUIRES_ADMIN = os.getenv("SUSPICIOUS_REQUIRES_ADMIN", "true").lower() == "true"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN manquant")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS manquant")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquant")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

BRANCHES = ["tiktok", "leakmedia", "reddit", "discord"]
BRANCH_LABELS = {"tiktok": "TikTok", "leakmedia": "Leakmedia", "reddit": "Reddit", "discord": "Discord"}


class Config(Base):
    __tablename__ = "antijavana_bot_config"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


class Group(Base):
    __tablename__ = "antijavana_bot_groups"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)
    is_central = Column(Boolean, default=False)
    is_promo = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "antijavana_bot_users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    joined_central_at = Column(DateTime, nullable=True)
    redirected_private = Column(Boolean, default=False)
    branch = Column(String(50), nullable=True)
    accepted = Column(Boolean, default=False)
    last_proof_at = Column(DateTime, nullable=True)
    pending_kick_until = Column(DateTime, nullable=True)
    pending_confirm_until = Column(DateTime, nullable=True)
    pending_confirm_branch = Column(String(50), nullable=True)
    proof_miss_count = Column(Integer, default=0)
    no_click_count = Column(Integer, default=0)
    suspicious = Column(Boolean, default=False)
    manual_review = Column(Boolean, default=False)
    banned_forever = Column(Boolean, default=False)
    banned_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BranchContent(Base):
    __tablename__ = "antijavana_bot_branch_content"
    id = Column(Integer, primary_key=True)
    branch = Column(String(50), unique=True, nullable=False)
    instructions = Column(Text, nullable=True)
    photo_file_id = Column(String(255), nullable=True)
    is_complete = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Reward(Base):
    __tablename__ = "antijavana_bot_rewards"
    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    active = Column(Boolean, default=True)
    published = Column(Boolean, default=False)
    message_id = Column(BigInteger, nullable=True)
    published_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Proof(Base):
    __tablename__ = "antijavana_bot_proofs"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    file_id = Column(String(255), nullable=True)
    caption = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    session_date = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class JoinRequestLog(Base):
    __tablename__ = "antijavana_bot_join_requests"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    status = Column(String(50), default="pending")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


def migrate():
    statements = [
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS pending_confirm_until TIMESTAMP",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS pending_confirm_branch VARCHAR(50)",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS proof_miss_count INTEGER DEFAULT 0",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS no_click_count INTEGER DEFAULT 0",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS suspicious BOOLEAN DEFAULT FALSE",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS manual_review BOOLEAN DEFAULT FALSE",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS banned_forever BOOLEAN DEFAULT FALSE",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS banned_reason TEXT",
        "ALTER TABLE antijavana_bot_proofs ADD COLUMN IF NOT EXISTS session_date VARCHAR(20)",
        "ALTER TABLE antijavana_bot_rewards ADD COLUMN IF NOT EXISTS message_id BIGINT",
        "ALTER TABLE antijavana_bot_rewards ADD COLUMN IF NOT EXISTS published_at TIMESTAMP",
        "ALTER TABLE antijavana_bot_rewards ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    ]
    with engine.begin() as conn:
        for st in statements:
            conn.execute(sql_text(st))


migrate()


def db():
    return SessionLocal()


def now_utc():
    return datetime.now(UTC).replace(tzinfo=None)


def today_key():
    return now_utc().strftime("%Y-%m-%d")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_reward_lock_time(dt=None) -> bool:
    dt = dt or now_utc()
    return dt.hour >= REWARD_START_HOUR or dt.hour < LOCK_END_HOUR


def proof_cutoff_passed(dt=None) -> bool:
    dt = dt or now_utc()
    return (dt.hour, dt.minute) >= (PROOF_KICK_HOUR, PROOF_KICK_MINUTE)


def reward_publish_due(dt=None) -> bool:
    dt = dt or now_utc()
    return (dt.hour, dt.minute) >= (REWARD_START_HOUR, REWARD_START_MINUTE)


def reward_delete_due(dt=None) -> bool:
    dt = dt or now_utc()
    return (dt.hour == REWARD_DELETE_HOUR and dt.minute >= REWARD_DELETE_MINUTE) or (dt.hour > REWARD_DELETE_HOUR and dt.hour < LOCK_END_HOUR)


def get_config(session, key, default=""):
    row = session.get(Config, key)
    return row.value if row and row.value is not None else default


def set_config(session, key, value):
    row = session.get(Config, key)
    if not row:
        session.add(Config(key=key, value=value))
    else:
        row.value = value


def already_done(session, job_name):
    return get_config(session, f"job_done:{job_name}:{today_key()}", "") == "1"


def mark_done(session, job_name):
    set_config(session, f"job_done:{job_name}:{today_key()}", "1")


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Gestion groupes", callback_data="admin:groups")],
        [InlineKeyboardButton("🧲 Publicité", callback_data="admin:ad")],
        [InlineKeyboardButton("🌐 Plateformes", callback_data="admin:platforms")],
        [InlineKeyboardButton("🎁 Récompenses", callback_data="admin:rewards")],
        [InlineKeyboardButton("✅ Preuves", callback_data="admin:proofs")],
        [InlineKeyboardButton("🧑‍⚖️ Revues manuelles", callback_data="admin:manual_review")],
        [InlineKeyboardButton("📊 Statistiques", callback_data="admin:stats")],
    ])


def back_main():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")]])


def groups_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Choisir groupe principal", callback_data="groups:choose_central")],
        [InlineKeyboardButton("📢 Choisir groupes publicité", callback_data="groups:promo_list")],
        [InlineKeyboardButton("📌 Message épinglé", callback_data="groups:pin_instruction")],
        [InlineKeyboardButton("🚀 Publier pub maintenant", callback_data="ad:publish_all")],
        [InlineKeyboardButton("📋 Voir configuration", callback_data="groups:summary")],
        [InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")],
    ])


def ad_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Modifier texte pub", callback_data="ad:set_text")],
        [InlineKeyboardButton("🖼 Modifier photo pub", callback_data="ad:set_photo")],
        [InlineKeyboardButton("👀 Aperçu pub", callback_data="ad:preview")],
        [InlineKeyboardButton("🚀 Publier dans groupes actifs", callback_data="ad:publish_all")],
        [InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")],
    ])


def platform_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="platform:tiktok"), InlineKeyboardButton("Leakmedia", callback_data="platform:leakmedia")],
        [InlineKeyboardButton("Reddit", callback_data="platform:reddit"), InlineKeyboardButton("Discord", callback_data="platform:discord")],
        [InlineKeyboardButton("📊 Répartition", callback_data="platform:balance")],
        [InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")],
    ])


def platform_edit_menu(branch):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Modifier texte", callback_data=f"platform_text:{branch}")],
        [InlineKeyboardButton("2️⃣ Modifier photo", callback_data=f"platform_photo:{branch}")],
        [InlineKeyboardButton("👀 Aperçu", callback_data=f"platform_preview:{branch}")],
        [InlineKeyboardButton("✅ Marquer comme complet", callback_data=f"platform_complete:{branch}")],
        [InlineKeyboardButton("⬅️ Plateformes", callback_data="admin:platforms")],
    ])


def user_join_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Demander l’accès", callback_data="user:join")]])


def central_instruction_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Je suis intéressé", callback_data="user:interested")]])


def platform_choice_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="user_branch:tiktok"), InlineKeyboardButton("Leakmedia", callback_data="user_branch:leakmedia")],
        [InlineKeyboardButton("Reddit", callback_data="user_branch:reddit"), InlineKeyboardButton("Discord", callback_data="user_branch:discord")],
    ])


def confirm_buttons(branch):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ OUI", callback_data=f"user_confirm:yes:{branch}"), InlineKeyboardButton("❌ NON", callback_data=f"user_confirm:no:{branch}")]])


def manual_review_buttons(user_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Accepter", callback_data=f"review:approve:{user_id}"), InlineKeyboardButton("❌ Refuser", callback_data=f"review:refuse:{user_id}")], [InlineKeyboardButton("⬅️ Menu", callback_data="admin:main")]])


async def notify_admins(context, text):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except Exception:
            pass


async def safe_callback_text(q, text, reply_markup=None):
    """Edits text messages, edits caption messages, or sends a new message if Telegram cannot edit."""
    try:
        if q.message and (q.message.text is not None):
            return await safe_callback_text(q, text, reply_markup=reply_markup)
        if q.message and (q.message.caption is not None):
            return await q.edit_message_caption(caption=text, reply_markup=reply_markup)
        return await q.message.reply_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            return await q.message.reply_text(text, reply_markup=reply_markup)
        except Exception:
            return None


def bot_start_url(context=None):
    username = BOT_USERNAME
    try:
        if not username and context and context.bot and context.bot.username:
            username = context.bot.username
    except Exception:
        pass
    return f"https://t.me/{username}" if username else None


async def validate_bio_tag(context, user_id):
    if not REQUIRE_BIO_TAG:
        return True, "bio check disabled"
    try:
        chat = await context.bot.get_chat(user_id)
        bio = getattr(chat, "bio", None) or ""
        if PUBLIC_BIO_TAG.lower() in bio.lower():
            return True, "bio ok"
        return False, f"bio sans {PUBLIC_BIO_TAG}"
    except Exception:
        return False, "bio inaccessible"


def looks_suspicious_user(user):
    reasons = []
    if MIN_USERNAME_REQUIRED and not user.username:
        reasons.append("aucun username")
    if getattr(user, "is_bot", False):
        reasons.append("compte bot")
    return bool(reasons), ", ".join(reasons)


async def ensure_pinned_instruction(context, central_chat_id):
    with db() as s:
        active_count = s.query(User).filter_by(accepted=True, banned_forever=False).count()
        pending_count = s.query(User).filter(User.pending_kick_until != None, User.banned_forever == False).count()
        message_id = get_config(s, "central_pinned_instruction_message_id", "")

    text = (
        "📌 Instructions du groupe\n\n"
        "Pour rester ici, clique sur le bouton ci-dessous et termine le processus en privé.\n\n"
        f"⏱ Délai après entrée : {KICK_AFTER_MINUTES} min\n"
        f"📸 Preuve obligatoire avant {PROOF_KICK_HOUR:02d}h{PROOF_KICK_MINUTE:02d}\n"
        f"🔒 Fermeture récompense : {REWARD_START_HOUR:02d}h → {LOCK_END_HOUR:02d}h\n\n"
        f"Actifs : {active_count} | En attente : {pending_count}"
    )

    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=central_chat_id, message_id=int(message_id), text=text, reply_markup=central_instruction_buttons())
            return
        except Exception:
            pass

    msg = await context.bot.send_message(central_chat_id, text, reply_markup=central_instruction_buttons())
    try:
        await context.bot.pin_chat_message(central_chat_id, msg.message_id, disable_notification=True)
    except Exception:
        pass

    with db() as s:
        set_config(s, "central_pinned_instruction_message_id", str(msg.message_id))
        s.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    if is_admin(user.id):
        await update.message.reply_text("🛠 Panel admin\n\nTout se gère avec les boutons ci-dessous.", reply_markup=main_menu())
        return

    with db() as s:
        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u:
            u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
            s.add(u)
        if u.banned_forever:
            s.commit()
            await update.message.reply_text("Accès refusé.")
            return
        u.redirected_private = True
        s.commit()

    await update.message.reply_text(
        f"🎉 Bienvenue.\n\n1) Mets {PUBLIC_BIO_TAG} dans ta bio publique.\n2) Clique ci-dessous pour demander l’accès au groupe.",
        reply_markup=user_join_button()
    )


async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        if not g:
            s.add(Group(chat_id=chat.id, title=chat.title, is_promo=False, is_active=True))
        else:
            g.title = chat.title
            g.updated_at = now_utc()
        s.commit()


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.my_chat_member.chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        if not g:
            s.add(Group(chat_id=chat.id, title=chat.title, is_promo=False, is_active=True))
        else:
            g.title = chat.title
            g.updated_at = now_utc()
        s.commit()


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    chat = req.chat
    user = req.from_user

    with db() as s:
        central = s.query(Group).filter_by(is_central=True).first()
        if not central or chat.id != central.chat_id:
            return

        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u:
            u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
            s.add(u)
        else:
            u.username = user.username
            u.first_name = user.first_name

        if u.banned_forever:
            s.add(JoinRequestLog(user_id=user.id, username=user.username, first_name=user.first_name, status="blocked", reason="banni définitivement"))
            s.commit()
            try:
                await req.decline()
            except Exception:
                pass
            return
        s.commit()

    if is_reward_lock_time():
        with db() as s:
            s.add(JoinRequestLog(user_id=user.id, username=user.username, first_name=user.first_name, status="refused", reason="groupe fermé 22h-01h"))
            s.commit()
        try:
            await req.decline()
        except Exception:
            pass
        return

    suspicious, suspicion_reason = looks_suspicious_user(user)
    if suspicious and SUSPICIOUS_REQUIRES_ADMIN:
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u:
                u.suspicious = True
                u.manual_review = True
            s.add(JoinRequestLog(user_id=user.id, username=user.username, first_name=user.first_name, status="manual_review", reason=suspicion_reason))
            s.commit()
        try:
            await req.decline()
        except Exception:
            pass
        await notify_admins(context, f"🧑‍⚖️ Demande suspecte.\nUser ID: {user.id}\nUsername: @{user.username or 'aucun'}\nRaison: {suspicion_reason}")
        return

    bio_ok, reason = await validate_bio_tag(context, user.id)
    if not bio_ok:
        with db() as s:
            s.add(JoinRequestLog(user_id=user.id, username=user.username, first_name=user.first_name, status="refused", reason=reason))
            s.commit()
        try:
            await req.decline()
        except Exception:
            pass
        return

    try:
        await req.approve()
    except Exception:
        return

    with db() as s:
        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u:
            u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
            s.add(u)
        u.joined_central_at = now_utc()
        u.pending_kick_until = now_utc() + timedelta(minutes=KICK_AFTER_MINUTES)
        u.manual_review = False
        s.add(JoinRequestLog(user_id=user.id, username=user.username, first_name=user.first_name, status="approved", reason=reason))
        s.commit()

    await ensure_pinned_instruction(context, chat.id)


async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        is_central = bool(g and g.is_central)

    if not is_central:
        return

    for member in update.message.new_chat_members:
        with db() as s:
            u = s.query(User).filter_by(telegram_id=member.id).first()
            if not u:
                u = User(telegram_id=member.id, username=member.username, first_name=member.first_name)
                s.add(u)
            if u.banned_forever:
                s.commit()
                await kick_from_central(context, member.id, permanent=True)
                continue
            if is_reward_lock_time():
                s.commit()
                await kick_from_central(context, member.id, permanent=False)
                continue
            u.joined_central_at = now_utc()
            u.pending_kick_until = now_utc() + timedelta(minutes=KICK_AFTER_MINUTES)
            s.commit()
        await ensure_pinned_instruction(context, chat.id)


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data.startswith(("admin:", "groups:", "ad:", "platform", "reward", "review:")):
        if not is_admin(q.from_user.id):
            await safe_callback_text(q, "Accès refusé.")
            return
        await handle_admin(q, context, data)
    else:
        await handle_user_callback(q, context, data)


async def handle_admin(q, context, data):
    if data == "admin:main":
        await safe_callback_text(q, "🛠 Panel admin", reply_markup=main_menu())
        return
    if data == "admin:groups":
        await safe_callback_text(q, "📣 Gestion des groupes", reply_markup=groups_menu())
        return
    if data == "admin:ad":
        await safe_callback_text(q, "🧲 Gestion publicité", reply_markup=ad_menu())
        return
    if data == "admin:platforms":
        await safe_callback_text(q, "🌐 Configuration des plateformes", reply_markup=platform_menu())
        return
    if data == "admin:rewards":
        await safe_callback_text(q, "🎁 Récompenses", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ajouter lien récompense", callback_data="reward:add")],
            [InlineKeyboardButton("📋 Voir liens en attente", callback_data="reward:list")],
            [InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")]
        ]))
        return
    if data == "admin:manual_review":
        with db() as s:
            users = s.query(User).filter_by(manual_review=True, banned_forever=False).limit(10).all()
        if not users:
            await safe_callback_text(q, "Aucune revue manuelle en attente.", reply_markup=back_main())
            return
        txt = "🧑‍⚖️ Revues manuelles\n\n"
        buttons = []
        for u in users:
            txt += f"ID {u.telegram_id} — @{u.username or 'aucun'} — {u.first_name or ''}\n"
            buttons.append([InlineKeyboardButton(f"Décider {u.telegram_id}", callback_data=f"review:open:{u.telegram_id}")])
        buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="admin:main")])
        await safe_callback_text(q, txt, reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data.startswith("review:open:"):
        uid = int(data.split(":")[-1])
        with db() as s:
            u = s.query(User).filter_by(telegram_id=uid).first()
        if not u:
            await safe_callback_text(q, "Utilisateur introuvable.", reply_markup=back_main())
            return
        await safe_callback_text(q, f"Revue utilisateur\n\nID: {u.telegram_id}\nUsername: @{u.username or 'aucun'}\nNom: {u.first_name or ''}", reply_markup=manual_review_buttons(uid))
        return
    if data.startswith("review:approve:"):
        uid = int(data.split(":")[-1])
        with db() as s:
            u = s.query(User).filter_by(telegram_id=uid).first()
            if u:
                u.manual_review = False
                u.suspicious = False
            s.commit()
        await safe_callback_text(q, "✅ Utilisateur approuvé côté panel. Il peut refaire une demande.", reply_markup=back_main())
        return
    if data.startswith("review:refuse:"):
        uid = int(data.split(":")[-1])
        with db() as s:
            u = s.query(User).filter_by(telegram_id=uid).first()
            if u:
                u.manual_review = False
                u.no_click_count = (u.no_click_count or 0) + 1
            s.commit()
        await safe_callback_text(q, "❌ Utilisateur refusé.", reply_markup=back_main())
        return
    if data == "admin:proofs":
        with db() as s:
            pending = s.query(Proof).filter_by(session_date=today_key(), status="pending").count()
            accepted = s.query(User).filter_by(accepted=True, banned_forever=False).count()
        await safe_callback_text(q, f"✅ Preuves du jour\n\nUtilisateurs actifs : {accepted}\nPreuves reçues : {pending}", reply_markup=back_main())
        return
    if data == "admin:stats":
        with db() as s:
            users = s.query(User).count()
            accepted = s.query(User).filter_by(accepted=True, banned_forever=False).count()
            banned = s.query(User).filter_by(banned_forever=True).count()
            manual = s.query(User).filter_by(manual_review=True).count()
            refused = s.query(JoinRequestLog).filter_by(status="refused").count()
            groups = s.query(Group).count()
            promos = s.query(Group).filter_by(is_promo=True, is_active=True).count()
            counts = {b: s.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
        txt = f"📊 Statistiques\n\nUtilisateurs : {users}\nActifs : {accepted}\nBannis : {banned}\nRevues : {manual}\nDemandes refusées : {refused}\nGroupes : {groups}\nGroupes pub actifs : {promos}\n\n"
        txt += "\n".join(f"{BRANCH_LABELS[b]} : {c}" for b, c in counts.items())
        await safe_callback_text(q, txt, reply_markup=back_main())
        return
    if data == "groups:choose_central":
        with db() as s:
            groups = s.query(Group).order_by(Group.updated_at.desc()).limit(30).all()
        if not groups:
            await safe_callback_text(q, "Aucun groupe détecté.", reply_markup=groups_menu())
            return
        buttons = [[InlineKeyboardButton(("⭐ " if g.is_central else "") + (g.title or str(g.chat_id)), callback_data=f"groups:set_central:{g.chat_id}")] for g in groups]
        buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:groups")])
        await safe_callback_text(q, "Choisis le groupe principal :", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data.startswith("groups:set_central:"):
        chat_id = int(data.split(":")[-1])
        with db() as s:
            for g in s.query(Group).all():
                g.is_central = (g.chat_id == chat_id)
                if g.chat_id == chat_id:
                    g.is_promo = False
                    g.is_active = True
            s.commit()
        await ensure_pinned_instruction(context, chat_id)
        await safe_callback_text(q, "✅ Groupe principal enregistré.", reply_markup=groups_menu())
        return
    if data == "groups:pin_instruction":
        with db() as s:
            central = s.query(Group).filter_by(is_central=True).first()
        if not central:
            await safe_callback_text(q, "Aucun groupe principal défini.", reply_markup=groups_menu())
            return
        await ensure_pinned_instruction(context, central.chat_id)
        await safe_callback_text(q, "📌 Message épinglé créé/mis à jour.", reply_markup=groups_menu())
        return
    if data == "groups:promo_list":
        with db() as s:
            groups = s.query(Group).order_by(Group.updated_at.desc()).limit(30).all()
        buttons = []
        for g in groups:
            if g.is_central:
                buttons.append([InlineKeyboardButton(f"⭐ Principal — {g.title or g.chat_id}", callback_data="noop")])
            else:
                mark = "✅" if g.is_promo and g.is_active else "⬜"
                buttons.append([InlineKeyboardButton(f"{mark} {g.title or g.chat_id}", callback_data=f"groups:toggle_promo:{g.chat_id}")])
        buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:groups")])
        await safe_callback_text(q, "Coche/décoche les groupes publicité actifs :", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data.startswith("groups:toggle_promo:"):
        chat_id = int(data.split(":")[-1])
        with db() as s:
            g = s.query(Group).filter_by(chat_id=chat_id).first()
            if g and not g.is_central:
                g.is_promo = not bool(g.is_promo and g.is_active)
                g.is_active = g.is_promo
                s.commit()
        await handle_admin(q, context, "groups:promo_list")
        return
    if data == "groups:summary":
        with db() as s:
            central = s.query(Group).filter_by(is_central=True).first()
            promos = s.query(Group).filter_by(is_promo=True, is_active=True).all()
        txt = f"⭐ Principal : {central.title if central else 'non défini'}\n\n📢 Groupes pub actifs :\n"
        txt += "\n".join(f"- {g.title or g.chat_id}" for g in promos) if promos else "Aucun"
        await safe_callback_text(q, txt, reply_markup=groups_menu())
        return
    if data == "ad:set_text":
        context.user_data["admin_waiting"] = "ad_text"
        await safe_callback_text(q, "Envoie le texte de publicité.")
        return
    if data == "ad:set_photo":
        context.user_data["admin_waiting"] = "ad_photo"
        await safe_callback_text(q, "Envoie la photo de publicité.")
        return
    if data == "ad:preview":
        await send_ad_preview(q.message.chat_id, context)
        return
    if data == "ad:publish_all":
        await publish_ad_to_promos(q, context)
        return
    if data.startswith("platform:") and data != "platform:balance":
        branch = data.split(":")[-1]
        await safe_callback_text(q, f"🌐 {BRANCH_LABELS[branch]}", reply_markup=platform_edit_menu(branch))
        return
    if data == "platform:balance":
        with db() as s:
            counts = {b: s.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
        await safe_callback_text(q, "\n".join(f"{BRANCH_LABELS[b]} : {c}" for b, c in counts.items()), reply_markup=platform_menu())
        return
    if data.startswith("platform_text:"):
        branch = data.split(":")[-1]
        context.user_data["admin_waiting"] = f"platform_text:{branch}"
        await safe_callback_text(q, f"Envoie le texte pour {BRANCH_LABELS[branch]}.")
        return
    if data.startswith("platform_photo:"):
        branch = data.split(":")[-1]
        context.user_data["admin_waiting"] = f"platform_photo:{branch}"
        await safe_callback_text(q, f"Envoie la photo pour {BRANCH_LABELS[branch]}.")
        return
    if data.startswith("platform_preview:"):
        await send_platform_preview(q.message.chat_id, context, data.split(":")[-1])
        return
    if data.startswith("platform_complete:"):
        branch = data.split(":")[-1]
        with db() as s:
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row or not row.instructions or not row.photo_file_id:
                await safe_callback_text(q, "Il manque le texte ou la photo.", reply_markup=platform_edit_menu(branch))
                return
            row.is_complete = True
            s.commit()
        await safe_callback_text(q, "✅ Plateforme validée.", reply_markup=platform_menu())
        return
    if data == "reward:add":
        context.user_data["admin_waiting"] = "reward_url"
        await safe_callback_text(q, "Envoie le lien récompense.")
        return
    if data == "reward:list":
        with db() as s:
            rewards = s.query(Reward).filter_by(published=False).order_by(Reward.created_at.asc()).limit(10).all()
        txt = "\n".join(f"{r.id}. {r.url}" for r in rewards) if rewards else "Aucun lien en attente."
        await safe_callback_text(q, txt, reply_markup=back_main())
        return


async def handle_user_callback(q, context, data):
    user = q.from_user
    if data == "user:join":
        # Si le bouton est cliqué depuis un groupe, Telegram ne garantit pas que l'utilisateur
        # ait déjà lancé le bot en privé. On le redirige donc d'abord vers le bot.
        if q.message and q.message.chat and q.message.chat.type != ChatType.PRIVATE:
            url = bot_start_url(context)
            if url:
                await q.answer("Ouvre le bot en privé pour continuer.", show_alert=True)
                try:
                    await q.message.reply_text(
                        "Pour demander l’accès, ouvre d’abord le bot en privé :",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🤖 Ouvrir le bot", url=url)]])
                    )
                except Exception:
                    pass
            else:
                await q.answer("Ouvre le bot en privé avec /start.", show_alert=True)
            return

        if is_reward_lock_time():
            await safe_callback_text(q, "Le groupe est fermé entre 22h et 01h. Reviens après 01h.")
            return

        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u and u.banned_forever:
                await safe_callback_text(q, "Accès refusé.")
                return
            central = s.query(Group).filter_by(is_central=True).first()
        if not central:
            await safe_callback_text(q, "Le groupe principal n’est pas configuré.")
            return

        try:
            invite = await context.bot.create_chat_invite_link(chat_id=central.chat_id, creates_join_request=True)
            await safe_callback_text(
                q,
                f"Mets {PUBLIC_BIO_TAG} dans ta bio publique puis demande l’accès :",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚪 Envoyer une demande", url=invite.invite_link)]])
            )
        except Exception as e:
            await safe_callback_text(q, f"Erreur invitation : {e}")
        return
    if data == "user:interested":
        try:
            await context.bot.send_message(user.id, "Choisis une plateforme :", reply_markup=platform_choice_buttons())
            with db() as s:
                u = s.query(User).filter_by(telegram_id=user.id).first()
                if u:
                    u.redirected_private = True
                s.commit()
            await q.answer("Je t’ai envoyé les choix en privé.")
        except Exception:
            await q.answer("Ouvre d’abord le bot en privé avec /start.", show_alert=True)
        return
    if data.startswith("user_branch:"):
        requested = data.split(":")[-1]
        with db() as s:
            branch = choose_balanced_branch(s, requested)
            row = s.query(BranchContent).filter_by(branch=branch).first()
            instructions = row.instructions if row and row.instructions else f"Instructions pour {BRANCH_LABELS[branch]}."
            photo = row.photo_file_id if row else None
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if not u:
                u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                s.add(u)
            u.pending_confirm_branch = branch
            u.pending_confirm_until = now_utc() + timedelta(minutes=CONFIRM_AFTER_MINUTES)
            s.commit()

        txt = f"Plateforme attribuée : {BRANCH_LABELS[branch]}\n\n{instructions}\n\nConfirmes-tu ?\n\nTu as {CONFIRM_AFTER_MINUTES} minutes pour répondre."
        if photo:
            await q.message.reply_photo(photo=photo, caption=txt, reply_markup=confirm_buttons(branch))
            try:
                await q.delete_message()
            except Exception:
                pass
        else:
            await safe_callback_text(q, txt, reply_markup=confirm_buttons(branch))
        return
    if data.startswith("user_confirm:"):
        _, ans, branch = data.split(":")
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if not u:
                u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                s.add(u)
            if ans == "yes":
                u.branch = branch
                u.accepted = True
                u.pending_kick_until = None
                u.pending_confirm_until = None
                u.pending_confirm_branch = None
                s.commit()
                await safe_callback_text(q, "✅ Validé. Envoie ta preuve chaque jour avant 21h50.")
            else:
                u.accepted = False
                u.pending_confirm_until = None
                u.pending_confirm_branch = None
                u.no_click_count = (u.no_click_count or 0) + 1
                permanent = u.no_click_count >= 2
                if permanent:
                    u.banned_forever = True
                s.commit()
                await safe_callback_text(q, "❌ Refus enregistré.")
                await kick_from_central(context, user.id, permanent=permanent)
        return


def choose_balanced_branch(session, requested):
    counts = {b: session.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
    min_count = min(counts.values()) if counts else 0
    if counts.get(requested, 0) <= min_count + 1:
        return requested
    candidates = [b for b, c in counts.items() if c == min_count]
    return random.choice(candidates)


async def send_ad_preview(chat_id, context):
    with db() as s:
        text = get_config(s, "ad_text", "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous.")
        photo = get_config(s, "ad_photo", "")
    if photo:
        await context.bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=user_join_button())
    else:
        await context.bot.send_message(chat_id, text=text, reply_markup=user_join_button())


async def publish_ad_to_promos(q, context):
    if is_reward_lock_time():
        await safe_callback_text(q, "Publication bloquée entre 22h et 01h.", reply_markup=groups_menu())
        return
    with db() as s:
        promos = s.query(Group).filter_by(is_promo=True, is_active=True).all()
        text = get_config(s, "ad_text", "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous.")
        photo = get_config(s, "ad_photo", "")
    ok = fail = 0
    for g in promos:
        try:
            if photo:
                await context.bot.send_photo(g.chat_id, photo=photo, caption=text, reply_markup=user_join_button())
            else:
                await context.bot.send_message(g.chat_id, text=text, reply_markup=user_join_button())
            ok += 1
        except Exception:
            fail += 1
    await safe_callback_text(q, f"Envoyé : {ok}\nÉchecs : {fail}", reply_markup=groups_menu())


async def send_platform_preview(chat_id, context, branch):
    with db() as s:
        row = s.query(BranchContent).filter_by(branch=branch).first()
    if not row:
        await context.bot.send_message(chat_id, "Aucun contenu configuré.")
        return
    txt = row.instructions or "Texte manquant"
    if row.photo_file_id:
        await context.bot.send_photo(chat_id, photo=row.photo_file_id, caption=txt)
    else:
        await context.bot.send_message(chat_id, txt)


async def admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    waiting = context.user_data.get("admin_waiting")
    if not waiting:
        return
    with db() as s:
        if waiting == "ad_text" and update.message.text:
            set_config(s, "ad_text", update.message.text)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Texte pub enregistré.", reply_markup=ad_menu())
            return
        if waiting == "ad_photo" and update.message.photo:
            set_config(s, "ad_photo", update.message.photo[-1].file_id)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Photo pub enregistrée.", reply_markup=ad_menu())
            return
        if waiting.startswith("platform_text:") and update.message.text:
            branch = waiting.split(":")[-1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.instructions = update.message.text
            row.is_complete = False
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Texte enregistré.", reply_markup=platform_edit_menu(branch))
            return
        if waiting.startswith("platform_photo:") and update.message.photo:
            branch = waiting.split(":")[-1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.photo_file_id = update.message.photo[-1].file_id
            row.is_complete = False
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Photo enregistrée.", reply_markup=platform_edit_menu(branch))
            return
        if waiting == "reward_url" and update.message.text:
            s.add(Reward(url=update.message.text.strip()))
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Lien récompense ajouté.", reply_markup=main_menu())
            return


async def user_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or is_admin(user.id) or not update.message or not update.message.photo:
        return
    with db() as s:
        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u or not u.accepted or u.banned_forever:
            return
        s.add(Proof(user_id=user.id, file_id=update.message.photo[-1].file_id, caption=update.message.caption, session_date=today_key()))
        u.last_proof_at = now_utc()
        s.commit()
    await update.message.reply_text("✅ Preuve reçue.")


async def kick_from_central(context, user_id, permanent=False):
    with db() as s:
        central = s.query(Group).filter_by(is_central=True).first()
    if not central:
        return
    try:
        await context.bot.ban_chat_member(central.chat_id, user_id)
        if not permanent:
            await context.bot.unban_chat_member(central.chat_id, user_id)
    except Exception:
        pass


async def scheduled_kicks(context):
    now = now_utc()
    with db() as s:
        expired = s.query(User).filter(User.pending_kick_until != None, User.pending_kick_until <= now, User.accepted == False, User.banned_forever == False).all()
        confirm_expired = s.query(User).filter(User.pending_confirm_until != None, User.pending_confirm_until <= now, User.accepted == False, User.banned_forever == False).all()
        temp, perm = [], []
        for u in expired:
            u.no_click_count = (u.no_click_count or 0) + 1
            u.pending_kick_until = None
            if u.no_click_count >= 2:
                u.banned_forever = True
                perm.append(u.telegram_id)
            else:
                temp.append(u.telegram_id)
        for u in confirm_expired:
            u.no_click_count = (u.no_click_count or 0) + 1
            u.pending_confirm_until = None
            u.pending_confirm_branch = None
            if u.no_click_count >= 2:
                u.banned_forever = True
                perm.append(u.telegram_id)
            else:
                temp.append(u.telegram_id)
        central = s.query(Group).filter_by(is_central=True).first()
        s.commit()
    for uid in temp:
        await kick_from_central(context, uid, permanent=False)
    for uid in perm:
        await kick_from_central(context, uid, permanent=True)
    if central:
        await ensure_pinned_instruction(context, central.chat_id)


async def proof_and_bio_cutoff_check(context, force=False):
    with db() as s:
        if not force and already_done(s, "proof_bio_cutoff"):
            return
        if not force and not proof_cutoff_passed():
            return
        active = s.query(User).filter_by(accepted=True, banned_forever=False).all()
        mark_done(s, "proof_bio_cutoff")
        s.commit()
    temp, perm, bio_removed = [], [], []
    for u in active:
        bio_ok, _ = await validate_bio_tag(context, u.telegram_id)
        if not bio_ok:
            bio_removed.append(u.telegram_id)
            with db() as s:
                uu = s.query(User).filter_by(telegram_id=u.telegram_id).first()
                if uu:
                    uu.accepted = False
                    uu.branch = None
                s.commit()
            continue
        with db() as s:
            has_proof = s.query(Proof).filter_by(user_id=u.telegram_id, session_date=today_key()).first()
            uu = s.query(User).filter_by(telegram_id=u.telegram_id).first()
            if has_proof or not uu:
                continue
            uu.accepted = False
            uu.branch = None
            uu.proof_miss_count = (uu.proof_miss_count or 0) + 1
            if uu.proof_miss_count >= 2:
                uu.banned_forever = True
                perm.append(uu.telegram_id)
            else:
                temp.append(uu.telegram_id)
            s.commit()
    for uid in bio_removed:
        await kick_from_central(context, uid, permanent=False)
    for uid in temp:
        await kick_from_central(context, uid, permanent=False)
    for uid in perm:
        await kick_from_central(context, uid, permanent=True)
    await notify_admins(context, f"Contrôle terminé. Bio retirée: {len(bio_removed)} | Sans preuve: {len(temp)} | Bans: {len(perm)}")


async def publish_reward(context, force=False):
    with db() as s:
        if not force and already_done(s, "reward_publish"):
            return
        if not force and not reward_publish_due():
            return
        central = s.query(Group).filter_by(is_central=True).first()
        reward = s.query(Reward).filter_by(active=True, published=False).order_by(Reward.created_at.asc()).first()
        if not central:
            return
        if not reward:
            await notify_admins(context, "⚠️ Aucun lien récompense en attente.")
            return
        reward_id = reward.id
        url = reward.url
        mark_done(s, "reward_publish")
        s.commit()
    try:
        msg = await context.bot.send_message(central.chat_id, f"🎁 Récompense du jour :\n{url}")
        with db() as s:
            r = s.query(Reward).filter_by(id=reward_id).first()
            if r:
                r.published = True
                r.published_at = now_utc()
                r.message_id = msg.message_id
            s.commit()
    except Exception:
        pass


async def delete_reward_message(context, force=False):
    with db() as s:
        if not force and already_done(s, "reward_delete"):
            return
        if not force and not reward_delete_due():
            return
        central = s.query(Group).filter_by(is_central=True).first()
        rewards = s.query(Reward).filter(Reward.published == True, Reward.deleted_at == None, Reward.message_id != None).all()
        mark_done(s, "reward_delete")
        s.commit()
    if not central:
        return
    for r in rewards:
        try:
            await context.bot.delete_message(central.chat_id, int(r.message_id))
            with db() as s:
                rr = s.query(Reward).filter_by(id=r.id).first()
                if rr:
                    rr.deleted_at = now_utc()
                s.commit()
        except Exception:
            pass


async def admin_reward_reminder(context):
    with db() as s:
        pending = s.query(Reward).filter_by(active=True, published=False).count()
    await notify_admins(context, f"⏰ Rappel récompense. Liens en attente : {pending}")


async def open_new_session(context):
    with db() as s:
        central = s.query(Group).filter_by(is_central=True).first()
        users = s.query(User).filter_by(accepted=True, banned_forever=False).all()
    if central:
        await ensure_pinned_instruction(context, central.chat_id)
    for u in users:
        try:
            await context.bot.send_message(u.telegram_id, "Nouvelle session ouverte. Envoie ta preuve du jour avant 21h50.")
        except Exception:
            pass


async def catchup_jobs(context):
    if proof_cutoff_passed():
        await proof_and_bio_cutoff_check(context)
    if reward_publish_due() and is_reward_lock_time():
        await publish_reward(context)
    if reward_delete_due() and is_reward_lock_time():
        await delete_reward_message(context)
    with db() as s:
        central = s.query(Group).filter_by(is_central=True).first()
    if central:
        await ensure_pinned_instruction(context, central.chat_id)


async def boot_session_message(context):
    await catchup_jobs(context)
    await notify_admins(context, "✅ Bot démarré. Version complète corrigée.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))
    app.add_handler(CallbackQueryHandler(admin_callbacks))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, register_group), group=1)
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, admin_input), group=2)
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, user_proof), group=3)

    app.job_queue.run_once(boot_session_message, when=5)
    app.job_queue.run_repeating(scheduled_kicks, interval=180, first=30)
    app.job_queue.run_repeating(catchup_jobs, interval=300, first=60)

    for h in ADMIN_REWARD_REMINDER_HOURS:
        app.job_queue.run_daily(admin_reward_reminder, time=time(hour=h, minute=0))

    app.job_queue.run_daily(proof_and_bio_cutoff_check, time=time(hour=PROOF_KICK_HOUR, minute=PROOF_KICK_MINUTE))
    app.job_queue.run_daily(publish_reward, time=time(hour=REWARD_START_HOUR, minute=REWARD_START_MINUTE))
    app.job_queue.run_daily(delete_reward_message, time=time(hour=REWARD_DELETE_HOUR, minute=REWARD_DELETE_MINUTE))
    app.job_queue.run_daily(open_new_session, time=time(hour=LOCK_END_HOUR, minute=0))

    print("Bot complet corrigé démarré.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
