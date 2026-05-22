import os
import random
from datetime import datetime, timedelta, time

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, Boolean,
    DateTime, text as sql_text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ChatMemberHandler, ContextTypes, filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

PUBLIC_BIO_TAG = os.getenv("PUBLIC_BIO_TAG", "@antijavana").strip()
KICK_AFTER_MINUTES = int(os.getenv("KICK_AFTER_MINUTES", "30"))
PROOF_DEADLINE_HOUR = int(os.getenv("PROOF_DEADLINE_HOUR", "22"))
REWARD_START_HOUR = int(os.getenv("REWARD_START_HOUR", "22"))
LOCK_END_HOUR = int(os.getenv("LOCK_END_HOUR", "1"))
ADMIN_REWARD_REMINDER_HOUR = int(os.getenv("ADMIN_REWARD_REMINDER_HOUR", "18"))

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
BRANCH_LABELS = {
    "tiktok": "TikTok",
    "leakmedia": "Leakmedia",
    "reddit": "Reddit",
    "discord": "Discord",
}


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
    proof_miss_count = Column(Integer, default=0)
    banned_forever = Column(Boolean, default=False)
    banned_reason = Column(Text, nullable=True)
    last_private_notice_at = Column(DateTime, nullable=True)
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


Base.metadata.create_all(engine)


def migrate():
    # Safe migrations for users who already deployed the previous prefixed version.
    statements = [
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS proof_miss_count INTEGER DEFAULT 0",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS banned_forever BOOLEAN DEFAULT FALSE",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS banned_reason TEXT",
        "ALTER TABLE antijavana_bot_users ADD COLUMN IF NOT EXISTS last_private_notice_at TIMESTAMP",
        "ALTER TABLE antijavana_bot_proofs ADD COLUMN IF NOT EXISTS session_date VARCHAR(20)",
    ]
    with engine.begin() as conn:
        for st in statements:
            conn.execute(sql_text(st))


migrate()


def db():
    return SessionLocal()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def now_utc():
    return datetime.utcnow()


def today_key():
    return now_utc().strftime("%Y-%m-%d")


def is_reward_lock_time(dt=None) -> bool:
    # Locked daily from 22:00 to 01:00 UTC/server time.
    dt = dt or now_utc()
    h = dt.hour
    return h >= REWARD_START_HOUR or h < LOCK_END_HOUR


def get_config(session, key: str, default: str = "") -> str:
    row = session.get(Config, key)
    return row.value if row and row.value is not None else default


def set_config(session, key: str, value: str):
    row = session.get(Config, key)
    if not row:
        session.add(Config(key=key, value=value))
    else:
        row.value = value


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Gestion groupes", callback_data="admin:groups")],
        [InlineKeyboardButton("🧲 Publicité", callback_data="admin:ad")],
        [InlineKeyboardButton("🌐 Plateformes", callback_data="admin:platforms")],
        [InlineKeyboardButton("🎁 Récompenses", callback_data="admin:rewards")],
        [InlineKeyboardButton("✅ Preuves", callback_data="admin:proofs")],
        [InlineKeyboardButton("📊 Statistiques", callback_data="admin:stats")],
    ])


def back_main():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")]])


def groups_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Choisir groupe principal", callback_data="groups:choose_central")],
        [InlineKeyboardButton("📢 Choisir groupes publicité", callback_data="groups:promo_list")],
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
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Je veux rejoindre", callback_data="user:join")]])


def central_instruction_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Je suis intéressé", callback_data="user:interested")]])


def platform_choice_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="user_branch:tiktok"), InlineKeyboardButton("Leakmedia", callback_data="user_branch:leakmedia")],
        [InlineKeyboardButton("Reddit", callback_data="user_branch:reddit"), InlineKeyboardButton("Discord", callback_data="user_branch:discord")],
    ])


def confirm_buttons(branch):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ OUI", callback_data=f"user_confirm:yes:{branch}"),
         InlineKeyboardButton("❌ NON", callback_data=f"user_confirm:no:{branch}")]
    ])


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

    await update.message.reply_text("🎉 Bienvenue en privé.\n\nChoisis une plateforme :", reply_markup=platform_choice_buttons())


async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        if not g:
            g = Group(chat_id=chat.id, title=chat.title, is_promo=False, is_active=True)
            s.add(g)
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


async def delete_previous_central_instruction(context, central_chat_id: int):
    with db() as s:
        old_id = get_config(s, "central_instruction_message_id", "")
    if old_id:
        try:
            await context.bot.delete_message(central_chat_id, int(old_id))
        except Exception:
            pass


async def send_unique_central_instruction(context, central_chat_id: int, member_name: str = ""):
    await delete_previous_central_instruction(context, central_chat_id)
    text = (
        f"Bonjour {member_name}.\n\n"
        f"Pour rester ici et participer à la session du jour, continue en privé avec le bot.\n\n"
        f"Tu as {KICK_AFTER_MINUTES} minutes pour cliquer."
    )
    msg = await context.bot.send_message(
        central_chat_id,
        text,
        reply_markup=central_instruction_buttons()
    )
    with db() as s:
        set_config(s, "central_instruction_message_id", str(msg.message_id))
        s.commit()


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

            # Nobody joins during reward window 22h-01h.
            if is_reward_lock_time():
                u.banned_forever = True
                u.banned_reason = "Tentative de rejoindre pendant la fenêtre récompense 22h-01h"
                s.commit()
                try:
                    await context.bot.send_message(member.id, "Le groupe est fermé entre 22h et 01h. Tu ne peux pas rejoindre pendant la distribution.")
                except Exception:
                    pass
                await kick_from_central(context, member.id, permanent=True)
                continue

            u.joined_central_at = now_utc()
            u.pending_kick_until = now_utc() + timedelta(minutes=KICK_AFTER_MINUTES)
            s.commit()

        await send_unique_central_instruction(context, chat.id, member.first_name or "")


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    data = q.data or ""

    if data.startswith(("admin:", "groups:", "ad:", "platform", "reward")):
        if not is_admin(user.id):
            await q.edit_message_text("Accès refusé.")
            return
        await handle_admin(q, context, data)
        return

    await handle_user_callback(q, context, data)


async def handle_admin(q, context, data):
    if data == "admin:main":
        await q.edit_message_text("🛠 Panel admin", reply_markup=main_menu())
        return

    if data == "admin:groups":
        await q.edit_message_text("📣 Gestion des groupes", reply_markup=groups_menu())
        return

    if data == "admin:ad":
        await q.edit_message_text("🧲 Gestion publicité", reply_markup=ad_menu())
        return

    if data == "admin:platforms":
        await q.edit_message_text("🌐 Configuration des plateformes", reply_markup=platform_menu())
        return

    if data == "admin:rewards":
        await q.edit_message_text("🎁 Récompenses", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ajouter lien récompense", callback_data="reward:add")],
            [InlineKeyboardButton("📋 Voir liens en attente", callback_data="reward:list")],
            [InlineKeyboardButton("⬅️ Menu principal", callback_data="admin:main")]
        ]))
        return

    if data == "admin:proofs":
        session = today_key()
        with db() as s:
            pending = s.query(Proof).filter_by(session_date=session, status="pending").count()
            accepted = s.query(User).filter_by(accepted=True, banned_forever=False).count()
        await q.edit_message_text(
            f"✅ Preuves session {session}\n\nUtilisateurs actifs : {accepted}\nPreuves reçues/en attente : {pending}",
            reply_markup=back_main()
        )
        return

    if data == "admin:stats":
        with db() as s:
            users = s.query(User).count()
            accepted = s.query(User).filter_by(accepted=True, banned_forever=False).count()
            banned = s.query(User).filter_by(banned_forever=True).count()
            groups = s.query(Group).count()
            promos = s.query(Group).filter_by(is_promo=True, is_active=True).count()
            counts = {b: s.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
        txt = f"📊 Statistiques\n\nUtilisateurs : {users}\nActifs : {accepted}\nBannis définitifs : {banned}\nGroupes détectés : {groups}\nGroupes pub actifs : {promos}\n\n"
        txt += "\n".join(f"{BRANCH_LABELS[b]} : {c}" for b, c in counts.items())
        await q.edit_message_text(txt, reply_markup=back_main())
        return

    if data == "groups:choose_central":
        with db() as s:
            groups = s.query(Group).order_by(Group.updated_at.desc()).limit(30).all()
        if not groups:
            await q.edit_message_text("Aucun groupe détecté. Ajoute le bot dans un groupe puis envoie un message dedans.", reply_markup=groups_menu())
            return
        buttons = [[InlineKeyboardButton(("⭐ " if g.is_central else "") + (g.title or str(g.chat_id)), callback_data=f"groups:set_central:{g.chat_id}")] for g in groups]
        buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:groups")])
        await q.edit_message_text("Choisis le groupe principal :", reply_markup=InlineKeyboardMarkup(buttons))
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
        await q.edit_message_text("✅ Groupe principal enregistré.", reply_markup=groups_menu())
        return

    if data == "groups:promo_list":
        with db() as s:
            groups = s.query(Group).order_by(Group.updated_at.desc()).limit(30).all()
        buttons = []
        for g in groups:
            if g.is_central:
                label = f"⭐ Principal — {g.title or g.chat_id}"
                cb = "noop"
            else:
                mark = "✅" if g.is_promo and g.is_active else "⬜"
                label = f"{mark} {g.title or g.chat_id}"
                cb = f"groups:toggle_promo:{g.chat_id}"
            buttons.append([InlineKeyboardButton(label, callback_data=cb)])
        buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:groups")])
        await q.edit_message_text("Coche/décoche les groupes publicité actifs :", reply_markup=InlineKeyboardMarkup(buttons))
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
        txt = "📋 Configuration groupes\n\n"
        txt += f"⭐ Principal : {central.title if central else 'non défini'}\n\n"
        txt += "📢 Groupes publicité actifs :\n"
        txt += "\n".join(f"- {g.title or g.chat_id}" for g in promos) if promos else "Aucun"
        txt += f"\n\n🔒 Groupe fermé chaque jour de {REWARD_START_HOUR}h à {LOCK_END_HOUR}h."
        await q.edit_message_text(txt, reply_markup=groups_menu())
        return

    if data == "ad:set_text":
        context.user_data["admin_waiting"] = "ad_text"
        await q.edit_message_text("✍️ Envoie le texte de publicité.")
        return

    if data == "ad:set_photo":
        context.user_data["admin_waiting"] = "ad_photo"
        await q.edit_message_text("🖼 Envoie la photo de publicité.")
        return

    if data == "ad:preview":
        await send_ad_preview(q.message.chat_id, context, edit_message=q)
        return

    if data == "ad:publish_all":
        await publish_ad_to_promos(q, context)
        return

    if data.startswith("platform:") and data != "platform:balance":
        branch = data.split(":")[-1]
        with db() as s:
            row = s.query(BranchContent).filter_by(branch=branch).first()
            complete = bool(row and row.is_complete)
        await q.edit_message_text(
            f"🌐 {BRANCH_LABELS[branch]}\n\nStatut : {'✅ complet' if complete else '⚠️ incomplet'}\n\nConfigure le texte puis la photo.",
            reply_markup=platform_edit_menu(branch)
        )
        return

    if data == "platform:balance":
        with db() as s:
            counts = {b: s.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
        txt = "📊 Répartition actuelle\n\n" + "\n".join(f"{BRANCH_LABELS[b]} : {c}" for b, c in counts.items())
        await q.edit_message_text(txt, reply_markup=platform_menu())
        return

    if data.startswith("platform_text:"):
        branch = data.split(":")[-1]
        context.user_data["admin_waiting"] = f"platform_text:{branch}"
        await q.edit_message_text(f"1️⃣ Texte — {BRANCH_LABELS[branch]}\n\nEnvoie les instructions.")
        return

    if data.startswith("platform_photo:"):
        branch = data.split(":")[-1]
        context.user_data["admin_waiting"] = f"platform_photo:{branch}"
        await q.edit_message_text(f"2️⃣ Photo — {BRANCH_LABELS[branch]}\n\nEnvoie la photo associée.")
        return

    if data.startswith("platform_preview:"):
        branch = data.split(":")[-1]
        await send_platform_preview(q.message.chat_id, context, branch)
        await q.message.reply_text("Menu :", reply_markup=platform_edit_menu(branch))
        return

    if data.startswith("platform_complete:"):
        branch = data.split(":")[-1]
        with db() as s:
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row or not row.instructions or not row.photo_file_id:
                await q.edit_message_text("⚠️ Il manque le texte ou la photo.", reply_markup=platform_edit_menu(branch))
                return
            row.is_complete = True
            row.updated_at = now_utc()
            s.commit()
        await q.edit_message_text(f"✅ {BRANCH_LABELS[branch]} est complet.", reply_markup=platform_menu())
        return

    if data == "reward:add":
        context.user_data["admin_waiting"] = "reward_url"
        await q.edit_message_text("🎁 Envoie le lien récompense à ajouter.")
        return

    if data == "reward:list":
        with db() as s:
            rewards = s.query(Reward).filter_by(published=False).order_by(Reward.created_at.asc()).limit(10).all()
        txt = "🎁 Liens en attente\n\n"
        txt += "\n".join(f"{r.id}. {r.url}" for r in rewards) if rewards else "Aucun lien en attente."
        await q.edit_message_text(txt, reply_markup=back_main())
        return


async def handle_user_callback(q, context, data):
    user = q.from_user

    if data == "user:join":
        if is_reward_lock_time():
            await q.edit_message_text("Le groupe est fermé entre 22h et 01h. Reviens après 01h.")
            return

        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u and u.banned_forever:
                await q.edit_message_text("Accès refusé.")
                return
            central = s.query(Group).filter_by(is_central=True).first()
        if not central:
            await q.edit_message_text("Le groupe principal n’est pas encore configuré.")
            return
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=central.chat_id,
                member_limit=1,
                creates_join_request=False
            )
            await q.edit_message_text("Clique ici pour rejoindre :", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Rejoindre le groupe", url=invite.invite_link)]
            ]))
        except Exception as e:
            await q.edit_message_text(f"Erreur invitation. Vérifie que le bot est admin.\n{e}")
        return

    if data == "user:interested":
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u and u.banned_forever:
                await q.edit_message_text("Accès refusé.")
                return
        try:
            await context.bot.send_message(user.id, "🎉 Félicitations.\n\nChoisis une plateforme :", reply_markup=platform_choice_buttons())
            with db() as s:
                u = s.query(User).filter_by(telegram_id=user.id).first()
                if not u:
                    u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                    s.add(u)
                u.redirected_private = True
                s.commit()
            await q.edit_message_text("Je t’ai envoyé les choix en privé.")
        except Exception:
            await q.edit_message_text("Ouvre d’abord le bot en privé puis clique sur /start.")
        return

    if data.startswith("user_branch:"):
        requested = data.split(":")[-1]
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if u and u.banned_forever:
                await q.edit_message_text("Accès refusé.")
                return
            branch = choose_balanced_branch(s, requested)
            row = s.query(BranchContent).filter_by(branch=branch).first()
            instructions = row.instructions if row and row.instructions else f"Instructions pour {BRANCH_LABELS[branch]}."
            photo = row.photo_file_id if row else None

        txt = f"Plateforme attribuée : {BRANCH_LABELS[branch]}\n\n{instructions}\n\nConfirmes-tu ?"
        if photo:
            await q.message.reply_photo(photo=photo, caption=txt, reply_markup=confirm_buttons(branch))
            await q.delete_message()
        else:
            await q.edit_message_text(txt, reply_markup=confirm_buttons(branch))
        return

    if data.startswith("user_confirm:"):
        _, ans, branch = data.split(":")
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if not u:
                u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                s.add(u)

            if u.banned_forever:
                s.commit()
                await q.edit_message_text("Accès refusé.")
                return

            if ans == "yes":
                u.branch = branch
                u.accepted = True
                u.redirected_private = True
                u.pending_kick_until = None
                s.commit()
                await q.edit_message_text("✅ Validé.\n\nEnvoie ta capture d’écran de preuve chaque jour avant 22h.")
            else:
                u.accepted = False
                u.banned_forever = True
                u.banned_reason = "A cliqué NON à la confirmation"
                s.commit()
                await q.edit_message_text("❌ Refus enregistré. Accès bloqué.")
                await kick_from_central(context, user.id, permanent=True)
        return


def choose_balanced_branch(session, requested):
    counts = {b: session.query(User).filter_by(branch=b, accepted=True, banned_forever=False).count() for b in BRANCHES}
    min_count = min(counts.values()) if counts else 0
    if counts.get(requested, 0) <= min_count + 1:
        return requested
    candidates = [b for b, c in counts.items() if c == min_count]
    return random.choice(candidates)


async def send_ad_preview(chat_id, context, edit_message=None):
    with db() as s:
        text = get_config(s, "ad_text", "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous.")
        photo = get_config(s, "ad_photo", "")

    if edit_message:
        await edit_message.message.reply_text("👀 Aperçu publicité :")
    if photo:
        await context.bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=user_join_button())
    else:
        await context.bot.send_message(chat_id, text=text, reply_markup=user_join_button())


async def publish_ad_to_promos(q, context):
    if is_reward_lock_time():
        await q.edit_message_text("🔒 Publication bloquée entre 22h et 01h.", reply_markup=groups_menu())
        return

    with db() as s:
        promos = s.query(Group).filter_by(is_promo=True, is_active=True).all()
        text = get_config(s, "ad_text", "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous.")
        photo = get_config(s, "ad_photo", "")

    ok, fail = 0, 0
    for g in promos:
        try:
            if photo:
                await context.bot.send_photo(g.chat_id, photo=photo, caption=text, reply_markup=user_join_button())
            else:
                await context.bot.send_message(g.chat_id, text, reply_markup=user_join_button())
            ok += 1
        except Exception:
            fail += 1

    await q.edit_message_text(f"🚀 Publication terminée.\n\nEnvoyé : {ok}\nÉchecs : {fail}", reply_markup=groups_menu())


async def send_platform_preview(chat_id, context, branch):
    with db() as s:
        row = s.query(BranchContent).filter_by(branch=branch).first()
    if not row:
        await context.bot.send_message(chat_id, f"Aucun contenu configuré pour {BRANCH_LABELS[branch]}.")
        return
    txt = f"👀 Aperçu {BRANCH_LABELS[branch]}\n\n{row.instructions or 'Texte manquant'}"
    if row.photo_file_id:
        await context.bot.send_photo(chat_id, photo=row.photo_file_id, caption=txt)
    else:
        await context.bot.send_message(chat_id, txt + "\n\nPhoto manquante.")


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
            row.updated_at = now_utc()
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text(f"✅ Texte {BRANCH_LABELS[branch]} enregistré.\n\nPasse à la photo.", reply_markup=platform_edit_menu(branch))
            return

        if waiting.startswith("platform_photo:") and update.message.photo:
            branch = waiting.split(":")[-1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.photo_file_id = update.message.photo[-1].file_id
            row.is_complete = False
            row.updated_at = now_utc()
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text(f"✅ Photo {BRANCH_LABELS[branch]} enregistrée.\n\nVérifie l’aperçu puis marque comme complet.", reply_markup=platform_edit_menu(branch))
            return

        if waiting == "reward_url" and update.message.text:
            s.add(Reward(url=update.message.text.strip()))
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Lien récompense ajouté.", reply_markup=main_menu())
            return


async def user_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or is_admin(user.id):
        return
    if not update.message or not update.message.photo:
        return

    with db() as s:
        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u or not u.accepted or u.banned_forever:
            return

        s.add(Proof(
            user_id=user.id,
            file_id=update.message.photo[-1].file_id,
            caption=update.message.caption,
            session_date=today_key()
        ))
        u.last_proof_at = now_utc()
        s.commit()

    await update.message.reply_text("✅ Preuve reçue pour la session du jour.")


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
        expired = s.query(User).filter(
            User.pending_kick_until != None,
            User.pending_kick_until <= now,
            User.accepted == False,
            User.banned_forever == False
        ).all()
        ids = []
        for u in expired:
            u.banned_forever = True
            u.banned_reason = "N’a pas cliqué sur Je suis intéressé sous 30 minutes"
            u.pending_kick_until = None
            ids.append(u.telegram_id)
        s.commit()

    for uid in ids:
        try:
            await context.bot.send_message(uid, "Tu n’as pas validé dans le délai. Accès bloqué.")
        except Exception:
            pass
        await kick_from_central(context, uid, permanent=True)


async def proof_deadline_check(context):
    # At 22:00, kick users without proof. They may return once only.
    session = today_key()
    with db() as s:
        active = s.query(User).filter_by(accepted=True, banned_forever=False).all()
        central = s.query(Group).filter_by(is_central=True).first()

        to_kick_temp = []
        to_ban_perm = []

        for u in active:
            has_proof = s.query(Proof).filter_by(user_id=u.telegram_id, session_date=session).first()
            if has_proof:
                continue

            u.accepted = False
            u.branch = None
            u.pending_kick_until = None
            u.proof_miss_count = (u.proof_miss_count or 0) + 1

            if u.proof_miss_count >= 2:
                u.banned_forever = True
                u.banned_reason = "Deuxième absence de preuve avant 22h"
                to_ban_perm.append(u.telegram_id)
            else:
                to_kick_temp.append(u.telegram_id)

        s.commit()

    for uid in to_kick_temp:
        try:
            await context.bot.send_message(
                uid,
                "Tu n’as pas envoyé ta preuve avant 22h. Tu as été retiré du groupe. Tu peux revenir une seule fois et refaire le processus."
            )
        except Exception:
            pass
        await kick_from_central(context, uid, permanent=False)

    for uid in to_ban_perm:
        try:
            await context.bot.send_message(
                uid,
                "Tu n’as pas envoyé ta preuve une deuxième fois. Accès définitivement bloqué."
            )
        except Exception:
            pass
        await kick_from_central(context, uid, permanent=True)


async def publish_reward(context):
    # Reward is published once daily in 22h-01h window, then next session starts after 01h.
    with db() as s:
        central = s.query(Group).filter_by(is_central=True).first()
        reward = s.query(Reward).filter_by(active=True, published=False).order_by(Reward.created_at.asc()).first()
        if not central or not reward:
            return
        url = reward.url
        reward.published = True
        s.commit()

    try:
        await context.bot.send_message(central.chat_id, f"🎁 Récompense du jour :\n{url}")
    except Exception:
        pass


async def admin_reward_reminder(context):
    with db() as s:
        pending = s.query(Reward).filter_by(active=True, published=False).count()
    msg = f"⏰ Rappel quotidien : ajoute un nouveau lien récompense pour ce soir.\nLiens en attente : {pending}"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, msg)
        except Exception:
            pass


async def open_new_session(context):
    # At 01:00, reset the central instruction message and tell active users the new proof session started.
    with db() as s:
        set_config(s, "central_instruction_message_id", "")
        users = s.query(User).filter_by(accepted=True, banned_forever=False).all()
        s.commit()
    for u in users:
        try:
            await context.bot.send_message(u.telegram_id, "Nouvelle session ouverte. Envoie ta preuve du jour avant 22h.")
        except Exception:
            pass


async def boot_session_message(context):
    # t=0 after deploy: notify admins that the proof session is active.
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                "✅ Bot démarré. Session de preuves active. Les utilisateurs devront envoyer leur capture avant 22h."
            )
        except Exception:
            pass


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))
    app.add_handler(CallbackQueryHandler(admin_callbacks))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, register_group), group=1)
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, admin_input), group=2)
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, user_proof), group=3)

    app.job_queue.run_once(boot_session_message, when=5)
    app.job_queue.run_repeating(scheduled_kicks, interval=120, first=30)

    app.job_queue.run_daily(admin_reward_reminder, time=time(hour=ADMIN_REWARD_REMINDER_HOUR, minute=0))
    app.job_queue.run_daily(proof_deadline_check, time=time(hour=PROOF_DEADLINE_HOUR, minute=0))
    app.job_queue.run_daily(publish_reward, time=time(hour=REWARD_START_HOUR, minute=5))
    app.job_queue.run_daily(open_new_session, time=time(hour=LOCK_END_HOUR, minute=0))

    print("Bot V2 PostgreSQL démarré avec tables isolées antijavana_bot_*. Lock 22h-01h, preuves quotidiennes, bans.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
