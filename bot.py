import os
import random
from datetime import datetime, timedelta, time
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, Boolean,
    DateTime, UniqueConstraint, func
)
from sqlalchemy.orm import declarative_base, sessionmaker
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ChatMemberHandler, ContextTypes, filters
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

PUBLIC_BIO_TAG = os.getenv("PUBLIC_BIO_TAG", "@antijavana").strip()
PROOF_DEADLINE_HOUR = int(os.getenv("PROOF_DEADLINE_HOUR", "22"))
REWARD_START_HOUR = int(os.getenv("REWARD_START_HOUR", "22"))
REWARD_END_HOUR = int(os.getenv("REWARD_END_HOUR", "1"))
KICK_AFTER_HOURS = int(os.getenv("KICK_AFTER_HOURS", "3"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN manquant")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS manquant")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquant. Ajoute PostgreSQL Railway et mets DATABASE_URL=${{Postgres.DATABASE_URL}}")

# Railway fournit parfois postgres://, psycopg attend postgresql+psycopg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class Config(Base):
    __tablename__ = "config"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)
    kind = Column(String(50), default="promo")  # promo ou central
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
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
    created_at = Column(DateTime, default=datetime.utcnow)


class BranchContent(Base):
    __tablename__ = "branch_content"
    id = Column(Integer, primary_key=True)
    branch = Column(String(50), unique=True, nullable=False)
    instructions = Column(Text, nullable=True)
    photo_file_id = Column(String(255), nullable=True)


class Reward(Base):
    __tablename__ = "rewards"
    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    active = Column(Boolean, default=True)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Proof(Base):
    __tablename__ = "proofs"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    file_id = Column(String(255), nullable=True)
    caption = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)

BRANCHES = ["tiktok", "leakmedia", "reddit", "discord"]


def db():
    return SessionLocal()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_config(session, key: str, default: str = "") -> str:
    row = session.get(Config, key)
    return row.value if row and row.value is not None else default


def set_config(session, key: str, value: str):
    row = session.get(Config, key)
    if not row:
        row = Config(key=key, value=value)
        session.add(row)
    else:
        row.value = value


def admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Groupes détectés", callback_data="admin:groups")],
        [InlineKeyboardButton("🎯 Définir groupe central", callback_data="admin:set_central_help")],
        [InlineKeyboardButton("📝 Texte publicité", callback_data="admin:set_ad_text")],
        [InlineKeyboardButton("🖼 Photo publicité", callback_data="admin:set_ad_photo")],
        [InlineKeyboardButton("🌐 Instructions plateformes", callback_data="admin:branches")],
        [InlineKeyboardButton("🎁 Ajouter lien récompense", callback_data="admin:set_reward")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin:stats")],
    ])


def join_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Je veux rejoindre", callback_data="join:start")]
    ])


def central_instruction_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Je suis intéressé", callback_data="flow:interested")]
    ])


def platform_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="branch:tiktok"), InlineKeyboardButton("Leakmedia", callback_data="branch:leakmedia")],
        [InlineKeyboardButton("Reddit", callback_data="branch:reddit"), InlineKeyboardButton("Discord", callback_data="branch:discord")],
    ])


def confirm_buttons(branch: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ OUI", callback_data=f"confirm:yes:{branch}"),
         InlineKeyboardButton("❌ NON", callback_data=f"confirm:no:{branch}")]
    ])


def choose_balanced_branch(session, requested: str) -> str:
    counts = {
        b: session.query(User).filter(User.branch == b, User.accepted == True).count()
        for b in BRANCHES
    }
    min_count = min(counts.values()) if counts else 0
    if counts.get(requested, 0) <= min_count + 1:
        return requested
    candidates = [b for b, c in counts.items() if c == min_count]
    return random.choice(candidates)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    if is_admin(user.id):
        await update.message.reply_text(
            "🛠 Panel admin\n\nChoisis une action :",
            reply_markup=admin_panel()
        )
        return

    with db() as s:
        u = s.query(User).filter_by(telegram_id=user.id).first()
        if not u:
            u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
            s.add(u)
        u.redirected_private = True
        s.commit()

    await update.message.reply_text(
        "🎉 Félicitations, tu es arrivé en privé.\n\nChoisis où tu veux publier :",
        reply_markup=platform_buttons()
    )


async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        if not g:
            g = Group(chat_id=chat.id, title=chat.title, kind="promo")
            s.add(g)
        else:
            g.title = chat.title
        s.commit()


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu: ChatMemberUpdated = update.my_chat_member
    chat = cmu.chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        return
    with db() as s:
        g = s.query(Group).filter_by(chat_id=chat.id).first()
        if not g:
            g = Group(chat_id=chat.id, title=chat.title, kind="promo")
            s.add(g)
        else:
            g.title = chat.title
        s.commit()


async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    with db() as s:
        central_id = int(get_config(s, "central_chat_id", "0") or "0")
        is_central = chat.id == central_id

        for member in update.message.new_chat_members:
            u = s.query(User).filter_by(telegram_id=member.id).first()
            if not u:
                u = User(telegram_id=member.id, username=member.username, first_name=member.first_name)
                s.add(u)
            if is_central:
                u.joined_central_at = datetime.utcnow()
                u.pending_kick_until = datetime.utcnow() + timedelta(hours=KICK_AFTER_HOURS)
                await update.message.reply_text(
                    f"Bonjour {member.first_name or ''}, bienvenue.\n\n"
                    f"Pour rester ici et recevoir les médias, tu dois continuer en privé avec le bot.",
                    reply_markup=central_instruction_buttons()
                )
        s.commit()


async def ad_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    with db() as s:
        ad_text = get_config(
            s,
            "ad_text",
            "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous."
        )
        ad_photo = get_config(s, "ad_photo", "")

    if ad_photo:
        await update.message.reply_photo(photo=ad_photo, caption=ad_text, reply_markup=join_button())
    else:
        await update.message.reply_text(ad_text, reply_markup=join_button())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    data = q.data or ""

    if data.startswith("admin:"):
        if not is_admin(user.id):
            await q.edit_message_text("Accès refusé.")
            return
        await handle_admin_callback(q, context, data)
        return

    if data == "join:start":
        with db() as s:
            central_id = int(get_config(s, "central_chat_id", "0") or "0")
        if not central_id:
            await q.edit_message_text("Le groupe central n’est pas encore configuré.")
            return
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=central_id,
                member_limit=1,
                creates_join_request=False
            )
            await q.edit_message_text("Clique ici pour rejoindre le groupe central :", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Rejoindre", url=invite.invite_link)]
            ]))
        except Exception as e:
            await q.edit_message_text(f"Impossible de créer le lien d’invitation. Vérifie que le bot est admin.\nErreur: {e}")
        return

    if data == "flow:interested":
        await q.edit_message_text("Écris au bot en privé puis appuie sur /start pour continuer.")
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="🎉 Félicitations.\n\nChoisis une plateforme :",
                reply_markup=platform_buttons()
            )
            with db() as s:
                u = s.query(User).filter_by(telegram_id=user.id).first()
                if not u:
                    u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                    s.add(u)
                u.redirected_private = True
                s.commit()
        except Exception:
            pass
        return

    if data.startswith("branch:"):
        requested = data.split(":", 1)[1]
        with db() as s:
            final_branch = choose_balanced_branch(s, requested)
            row = s.query(BranchContent).filter_by(branch=final_branch).first()
            instructions = row.instructions if row and row.instructions else f"Instructions pour {final_branch}."
            photo = row.photo_file_id if row else None

        txt = f"Plateforme attribuée : {final_branch.upper()}\n\n{instructions}\n\nConfirmes-tu que tu acceptes cette branche ?"
        if photo:
            await q.message.reply_photo(photo=photo, caption=txt, reply_markup=confirm_buttons(final_branch))
            await q.delete_message()
        else:
            await q.edit_message_text(txt, reply_markup=confirm_buttons(final_branch))
        return

    if data.startswith("confirm:"):
        _, ans, branch = data.split(":")
        with db() as s:
            u = s.query(User).filter_by(telegram_id=user.id).first()
            if not u:
                u = User(telegram_id=user.id, username=user.username, first_name=user.first_name)
                s.add(u)
            if ans == "yes":
                u.branch = branch
                u.accepted = True
                u.redirected_private = True
                u.pending_kick_until = None
                s.commit()
                await q.edit_message_text(
                    "✅ Validé.\n\nEnvoie ta capture d’écran de preuve chaque jour avant 22h."
                )
            else:
                u.accepted = False
                s.commit()
                await q.edit_message_text("❌ Refus enregistré. Tu peux être retiré du groupe central.")
                await kick_from_central(context, user.id)
        return


async def handle_admin_callback(q, context, data):
    if data == "admin:groups":
        with db() as s:
            groups = s.query(Group).order_by(Group.created_at.desc()).limit(20).all()
        if not groups:
            await q.edit_message_text("Aucun groupe détecté.", reply_markup=admin_panel())
            return
        rows = []
        for g in groups:
            rows.append([InlineKeyboardButton(f"{g.title or g.chat_id} — {g.kind}", callback_data=f"admin:central:{g.chat_id}")])
        rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:back")])
        await q.edit_message_text(
            "Groupes détectés.\nClique sur un groupe pour le définir comme central :",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    if data.startswith("admin:central:"):
        chat_id = data.split(":")[-1]
        with db() as s:
            for g in s.query(Group).all():
                g.kind = "central" if str(g.chat_id) == chat_id else g.kind
            set_config(s, "central_chat_id", chat_id)
            s.commit()
        await q.edit_message_text(f"✅ Groupe central défini : `{chat_id}`", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_panel())
        return

    if data == "admin:set_central_help":
        await q.edit_message_text("Va dans 📣 Groupes détectés, puis clique sur le groupe central.", reply_markup=admin_panel())
        return

    if data == "admin:set_ad_text":
        context.user_data["admin_waiting"] = "ad_text"
        await q.edit_message_text("Envoie maintenant le nouveau texte de publicité.")
        return

    if data == "admin:set_ad_photo":
        context.user_data["admin_waiting"] = "ad_photo"
        await q.edit_message_text("Envoie maintenant la photo de publicité.")
        return

    if data == "admin:branches":
        await q.edit_message_text("Choisis la plateforme à configurer :", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("TikTok", callback_data="admin:branch:tiktok"), InlineKeyboardButton("Leakmedia", callback_data="admin:branch:leakmedia")],
            [InlineKeyboardButton("Reddit", callback_data="admin:branch:reddit"), InlineKeyboardButton("Discord", callback_data="admin:branch:discord")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="admin:back")]
        ]))
        return

    if data.startswith("admin:branch:"):
        branch = data.split(":")[-1]
        context.user_data["admin_waiting"] = f"branch_text:{branch}"
        await q.edit_message_text(f"Envoie les instructions texte pour {branch.upper()}.\nEnsuite tu pourras envoyer une photo avec /photo_{branch}.")
        return

    if data == "admin:set_reward":
        context.user_data["admin_waiting"] = "reward"
        await q.edit_message_text("Envoie le lien GoFile/récompense à publier.")
        return

    if data == "admin:stats":
        with db() as s:
            total = s.query(User).count()
            accepted = s.query(User).filter(User.accepted == True).count()
            branch_counts = {b: s.query(User).filter(User.branch == b, User.accepted == True).count() for b in BRANCHES}
            proofs = s.query(Proof).filter(Proof.created_at >= datetime.utcnow().date()).count()
        text = f"📊 Stats\n\nUtilisateurs: {total}\nAcceptés: {accepted}\nPreuves aujourd’hui: {proofs}\n\n"
        text += "\n".join([f"{b}: {c}" for b, c in branch_counts.items()])
        await q.edit_message_text(text, reply_markup=admin_panel())
        return

    if data == "admin:back":
        await q.edit_message_text("🛠 Panel admin", reply_markup=admin_panel())


async def admin_text_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        # preuves utilisateurs
        if update.message and update.message.photo:
            with db() as s:
                proof = Proof(
                    user_id=user.id,
                    file_id=update.message.photo[-1].file_id,
                    caption=update.message.caption
                )
                s.add(proof)
                u = s.query(User).filter_by(telegram_id=user.id).first()
                if u:
                    u.last_proof_at = datetime.utcnow()
                s.commit()
            await update.message.reply_text("✅ Preuve reçue.")
        return

    waiting = context.user_data.get("admin_waiting")
    if not waiting:
        return

    with db() as s:
        if waiting == "ad_text" and update.message.text:
            set_config(s, "ad_text", update.message.text)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Texte publicité enregistré.", reply_markup=admin_panel())
            return

        if waiting == "ad_photo" and update.message.photo:
            set_config(s, "ad_photo", update.message.photo[-1].file_id)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Photo publicité enregistrée.", reply_markup=admin_panel())
            return

        if waiting == "reward" and update.message.text:
            s.add(Reward(url=update.message.text.strip()))
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Récompense ajoutée.", reply_markup=admin_panel())
            return

        if waiting.startswith("branch_text:") and update.message.text:
            branch = waiting.split(":")[-1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.instructions = update.message.text
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text(f"✅ Instructions {branch} enregistrées.\nPour ajouter la photo, envoie /photo_{branch}.", reply_markup=admin_panel())
            return


async def branch_photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    cmd = update.message.text.split()[0].replace("/", "")
    if not cmd.startswith("photo_"):
        return
    branch = cmd.replace("photo_", "")
    if branch not in BRANCHES:
        return
    context.user_data["admin_waiting"] = f"branch_photo:{branch}"
    await update.message.reply_text(f"Envoie maintenant la photo pour {branch.upper()}.")


async def branch_photo_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    waiting = context.user_data.get("admin_waiting", "")
    if not waiting.startswith("branch_photo:") or not update.message.photo:
        return
    branch = waiting.split(":")[-1]
    with db() as s:
        row = s.query(BranchContent).filter_by(branch=branch).first()
        if not row:
            row = BranchContent(branch=branch)
            s.add(row)
        row.photo_file_id = update.message.photo[-1].file_id
        s.commit()
    context.user_data.pop("admin_waiting", None)
    await update.message.reply_text(f"✅ Photo {branch} enregistrée.", reply_markup=admin_panel())


async def kick_from_central(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    with db() as s:
        central_id = int(get_config(s, "central_chat_id", "0") or "0")
    if not central_id:
        return
    try:
        await context.bot.ban_chat_member(chat_id=central_id, user_id=user_id)
        await context.bot.unban_chat_member(chat_id=central_id, user_id=user_id)
    except Exception:
        pass


async def scheduled_checks(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    with db() as s:
        expired = s.query(User).filter(
            User.pending_kick_until != None,
            User.pending_kick_until <= now,
            User.accepted == False
        ).all()
        ids = [u.telegram_id for u in expired]
        for u in expired:
            u.pending_kick_until = None
        s.commit()

    for uid in ids:
        await kick_from_central(context, uid)


async def daily_proof_warning(context: ContextTypes.DEFAULT_TYPE):
    # Message de rappel aux acceptés qui n'ont pas envoyé de preuve aujourd'hui
    today = datetime.utcnow().date()
    with db() as s:
        users = s.query(User).filter(User.accepted == True).all()
    for u in users:
        if not u.last_proof_at or u.last_proof_at.date() < today:
            try:
                await context.bot.send_message(u.telegram_id, "⏰ Rappel : envoie ta preuve avant 22h.")
            except Exception:
                pass


async def publish_reward(context: ContextTypes.DEFAULT_TYPE):
    with db() as s:
        central_id = int(get_config(s, "central_chat_id", "0") or "0")
        reward = s.query(Reward).filter(Reward.active == True, Reward.published == False).order_by(Reward.created_at.asc()).first()
        if not central_id or not reward:
            return
        url = reward.url
        reward.published = True
        s.commit()

    try:
        await context.bot.send_message(central_id, f"🎁 Récompense du jour :\n{url}")
    except Exception:
        pass


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ad", ad_command))
    app.add_handler(CommandHandler(["photo_tiktok", "photo_leakmedia", "photo_reddit", "photo_discord"], branch_photo_command))

    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.PHOTO, branch_photo_receive), group=1)
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, admin_text_or_photo), group=2)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, register_group), group=3)

    app.job_queue.run_repeating(scheduled_checks, interval=300, first=30)
    app.job_queue.run_daily(daily_proof_warning, time=time(hour=PROOF_DEADLINE_HOUR - 1, minute=0))
    app.job_queue.run_daily(publish_reward, time=time(hour=REWARD_START_HOUR, minute=0))

    print("Bot production PostgreSQL démarré.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
