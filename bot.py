
import os
from datetime import datetime, timedelta, time, UTC

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date, text as sql_text
from sqlalchemy.orm import declarative_base, sessionmaker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip().lstrip("@")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

PUBLIC_BIO_TAG = os.getenv("PUBLIC_BIO_TAG", "@antijavana").strip()
MAIN_CHANNEL = os.getenv("MAIN_CHANNEL", "@antijavana").strip()

INVITE_EXPIRE_MINUTES = int(os.getenv("INVITE_EXPIRE_MINUTES", "10"))
PROOF_KICK_HOUR = int(os.getenv("PROOF_KICK_HOUR", "21"))
PROOF_KICK_MINUTE = int(os.getenv("PROOF_KICK_MINUTE", "50"))
REWARD_HOUR = int(os.getenv("REWARD_HOUR", "22"))
REWARD_MINUTE = int(os.getenv("REWARD_MINUTE", "5"))
REWARD_DELETE_AFTER_HOURS = int(os.getenv("REWARD_DELETE_AFTER_HOURS", "2"))
REWARD_LOCK_EXTRA_MINUTES = int(os.getenv("REWARD_LOCK_EXTRA_MINUTES", "5"))
ADMIN_REWARD_REMINDER_HOURS = [int(x.strip()) for x in os.getenv("ADMIN_REWARD_REMINDER_HOURS", "12,18,21").split(",") if x.strip().isdigit()]
REQUIRE_CHANNEL_JOIN = os.getenv("REQUIRE_CHANNEL_JOIN", "true").lower() == "true"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN manquant")
if not BOT_USERNAME:
    raise RuntimeError("BOT_USERNAME manquant")
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

BRANCHES = ["tiktok", "reddit", "discord", "leakmedia"]
BRANCH_LABELS = {"tiktok": "TikTok", "reddit": "Reddit", "discord": "Discord", "leakmedia": "Leakmedia"}


class Config(Base):
    __tablename__ = "ajv2_config"
    key = Column(String(100), primary_key=True)
    value = Column(Text)


class User(Base):
    __tablename__ = "ajv2_users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    bio_declared = Column(Boolean, default=False)
    channel_verified = Column(Boolean, default=False)
    branch = Column(String(50))
    waiting_first_proof = Column(Boolean, default=False)
    validated = Column(Boolean, default=False)
    joined_main = Column(Boolean, default=False)
    proof_miss_count = Column(Integer, default=0)
    banned = Column(Boolean, default=False)
    banned_reason = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class PromoGroup(Base):
    __tablename__ = "ajv2_promo_groups"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class BranchContent(Base):
    __tablename__ = "ajv2_branch_content"
    id = Column(Integer, primary_key=True)
    branch = Column(String(50), unique=True, nullable=False)
    instructions = Column(Text)
    photo_file_id = Column(String(255))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class Proof(Base):
    __tablename__ = "ajv2_proofs"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)
    file_id = Column(String(255), nullable=False)
    proof_date = Column(Date, index=True, nullable=False)
    kind = Column(String(50), default="daily")
    status = Column(String(50), default="pending")  # pending / accepted / refused
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class AdminProofMessage(Base):
    __tablename__ = "ajv2_admin_proof_messages"
    id = Column(Integer, primary_key=True)
    proof_id = Column(Integer, index=True, nullable=False)
    admin_id = Column(BigInteger, index=True, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class Reward(Base):
    __tablename__ = "ajv2_rewards"
    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    published = Column(Boolean, default=False)
    message_id = Column(BigInteger)
    published_at = Column(DateTime)
    deleted_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))


Base.metadata.create_all(engine)


def migrate():
    stmts = [
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS bio_declared BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS channel_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS waiting_first_proof BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS validated BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS joined_main BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS proof_miss_count INTEGER DEFAULT 0",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ajv2_users ADD COLUMN IF NOT EXISTS banned_reason TEXT",
        "ALTER TABLE ajv2_rewards ADD COLUMN IF NOT EXISTS message_id BIGINT",
        "ALTER TABLE ajv2_rewards ADD COLUMN IF NOT EXISTS published_at TIMESTAMP",
        "ALTER TABLE ajv2_rewards ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
        "ALTER TABLE ajv2_proofs ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending'",
        """CREATE TABLE IF NOT EXISTS ajv2_admin_proof_messages (
            id SERIAL PRIMARY KEY,
            proof_id INTEGER NOT NULL,
            admin_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(sql_text(stmt))


migrate()


def db():
    return SessionLocal()


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def today():
    return now().date()


def is_admin(uid):
    return uid in ADMIN_IDS


def get_config(s, key, default=""):
    row = s.get(Config, key)
    return row.value if row and row.value is not None else default


def set_config(s, key, value):
    row = s.get(Config, key)
    if row:
        row.value = str(value)
    else:
        s.add(Config(key=key, value=str(value)))


def job_done(s, name):
    return get_config(s, f"job:{name}:{today().isoformat()}", "") == "1"


def mark_job(s, name):
    set_config(s, f"job:{name}:{today().isoformat()}", "1")


def get_user(s, tg_user):
    u = s.query(User).filter_by(telegram_id=tg_user.id).first()
    if not u:
        u = User(telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name)
        s.add(u)
    else:
        u.username = tg_user.username
        u.first_name = tg_user.first_name
        u.updated_at = now()
    return u


def reward_start_dt():
    n = now()
    return n.replace(hour=REWARD_HOUR, minute=REWARD_MINUTE, second=0, microsecond=0)


def reward_lock_active():
    start = reward_start_dt()
    end = start + timedelta(hours=REWARD_DELETE_AFTER_HOURS, minutes=REWARD_LOCK_EXTRA_MINUTES)
    n = now()
    if end.date() != n.date():
        return n >= start or n <= end
    return start <= n <= end


def proof_cutoff_passed():
    n = now()
    return (n.hour, n.minute) >= (PROOF_KICK_HOUR, PROOF_KICK_MINUTE)


def reward_due():
    n = now()
    return (n.hour, n.minute) >= (REWARD_HOUR, REWARD_MINUTE)


def bot_url():
    return f"https://t.me/{BOT_USERNAME}"


def start_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Commencer", url=bot_url())]])


def bio_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Oui", callback_data="bio:yes"), InlineKeyboardButton("❌ Non", callback_data="bio:no")]])


def channel_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Ouvrir le canal", url=f"https://t.me/{MAIN_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("✅ Je follow le canal", callback_data="channel:check")],
    ])


def branch_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="branch:tiktok"), InlineKeyboardButton("Reddit", callback_data="branch:reddit")],
        [InlineKeyboardButton("Discord", callback_data="branch:discord"), InlineKeyboardButton("Leakmedia", callback_data="branch:leakmedia")],
    ])


def published_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ J’ai publié", callback_data="proof:ready")]])


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Groupes publicité", callback_data="admin:groups")],
        [InlineKeyboardButton("🧲 Publicité", callback_data="admin:ad")],
        [InlineKeyboardButton("🌐 Plateformes", callback_data="admin:platforms")],
        [InlineKeyboardButton("🎁 Ajouter récompense", callback_data="admin:reward")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin:stats")],
    ])


def admin_platform_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="admbranch:tiktok"), InlineKeyboardButton("Reddit", callback_data="admbranch:reddit")],
        [InlineKeyboardButton("Discord", callback_data="admbranch:discord"), InlineKeyboardButton("Leakmedia", callback_data="admbranch:leakmedia")],
        [InlineKeyboardButton("⬅️ Menu", callback_data="admin:menu")]
    ])


async def notify_admins(context, text):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, text)
        except Exception:
            pass


async def is_channel_member(context, user_id):
    if not REQUIRE_CHANNEL_JOIN:
        return True
    try:
        m = await context.bot.get_chat_member(MAIN_CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False


def branch_loads(session):
    """Compte les utilisateurs validés ou en attente de preuve par branche."""
    loads = {}
    for b in BRANCHES:
        loads[b] = session.query(User).filter(
            User.branch == b,
            User.banned == False,
            (User.validated == True) | (User.waiting_first_proof == True)
        ).count()
    return loads


def choose_balanced_branch(session, requested):
    loads = branch_loads(session)
    min_load = min(loads.values()) if loads else 0
    requested_load = loads.get(requested, 0)

    # Si la branche demandée a plus d'1 utilisateur d'écart avec la moins remplie,
    # on attribue automatiquement une branche plus faible.
    if requested_load <= min_load + 1:
        return requested

    candidates = [b for b, c in loads.items() if c == min_load]
    return candidates[0] if candidates else requested


async def delete_admin_proof_messages(context, proof_id):
    with db() as s:
        rows = s.query(AdminProofMessage).filter_by(proof_id=proof_id).all()
        copies = [(r.admin_id, r.message_id) for r in rows]

    for admin_id, message_id in copies:
        try:
            await context.bot.delete_message(chat_id=admin_id, message_id=message_id)
        except Exception:
            pass

    with db() as s:
        s.query(AdminProofMessage).filter_by(proof_id=proof_id).delete()
        s.commit()


async def send_proof_to_admins(context, proof_id):
    with db() as s:
        proof = s.query(Proof).filter_by(id=proof_id).first()
        user = s.query(User).filter_by(telegram_id=proof.telegram_id).first() if proof else None
        if not proof or not user:
            return

    caption = (
        f"📸 Nouvelle preuve à valider\n\n"
        f"Type : {proof.kind}\n"
        f"Branche : {user.branch or 'non définie'}\n"
        f"User ID : {user.telegram_id}\n"
        f"Username : @{user.username or 'aucun'}\n"
        f"Nom : {user.first_name or ''}"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accepter", callback_data=f"proofadmin:accept:{proof_id}"),
            InlineKeyboardButton("❌ Refuser", callback_data=f"proofadmin:refuse:{proof_id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            msg = await context.bot.send_photo(admin_id, photo=proof.file_id, caption=caption, reply_markup=kb)
            with db() as s:
                s.add(AdminProofMessage(proof_id=proof_id, admin_id=admin_id, message_id=msg.message_id))
                s.commit()
        except Exception:
            pass


async def safe_edit(q, text, reply_markup=None):
    try:
        await q.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await q.message.reply_text(text, reply_markup=reply_markup)
        except Exception:
            pass


async def send_platform_content(context, chat_id, branch):
    with db() as s:
        row = s.query(BranchContent).filter_by(branch=branch).first()
    instructions = row.instructions if row and row.instructions else f"Instructions pour {BRANCH_LABELS[branch]}."
    photo = row.photo_file_id if row else None
    text = f"📌 {BRANCH_LABELS[branch]}\n\n{instructions}\n\nQuand tu as publié, clique sur le bouton puis envoie ta capture d’écran."
    if photo:
        await context.bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=published_button())
    else:
        await context.bot.send_message(chat_id, text, reply_markup=published_button())


async def send_invite(context, user_id):
    if reward_lock_active():
        await context.bot.send_message(user_id, "🔒 Les accès sont fermés pendant la période de récompense. Réessaie après la distribution.")
        return

    with db() as s:
        main_group = get_config(s, "main_group_id", "")

    if not main_group:
        await context.bot.send_message(user_id, "Le groupe principal n’est pas encore configuré.")
        return

    expire = now() + timedelta(minutes=INVITE_EXPIRE_MINUTES)
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=int(main_group),
            member_limit=1,
            expire_date=expire
        )
        await context.bot.send_message(
            user_id,
            f"✅ Validé.\n\nVoici ton lien unique :\n{invite.invite_link}\n\nIl expire dans {INVITE_EXPIRE_MINUTES} minutes et fonctionne 1 seule fois."
        )
    except Exception as e:
        await context.bot.send_message(user_id, f"Erreur création lien : {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type != ChatType.PRIVATE:
        return

    if is_admin(user.id):
        await update.message.reply_text("🛠 Panel admin", reply_markup=admin_menu())
        return

    with db() as s:
        u = get_user(s, user)
        if u.banned:
            s.commit()
            await update.message.reply_text("Accès refusé.")
            return
        s.commit()

    await update.message.reply_text(
        f"Bienvenue.\n\nPour accéder au groupe, ta bio publique doit contenir {PUBLIC_BIO_TAG}.\n\nTa bio est-elle publique et contient-elle {PUBLIC_BIO_TAG} ?",
        reply_markup=bio_buttons()
    )


async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not is_admin(user.id):
        return

    cmd = update.message.text.split()[0]

    with db() as s:
        if cmd == "/setmain":
            set_config(s, "main_group_id", str(chat.id))
            s.commit()
            await update.message.reply_text("✅ Groupe principal enregistré.")
            return

        if cmd == "/addpromo":
            g = s.query(PromoGroup).filter_by(chat_id=chat.id).first()
            if not g:
                s.add(PromoGroup(chat_id=chat.id, title=chat.title, active=True))
            else:
                g.active = True
                g.title = chat.title
            s.commit()
            await update.message.reply_text("✅ Groupe publicité ajouté.")
            return

        if cmd == "/panel":
            await update.message.reply_text("🛠 Panel admin", reply_markup=admin_menu())
            return


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    data = q.data or ""

    if data.startswith("admin:") or data.startswith("admbranch:") or data.startswith("ad:") or data.startswith("proofadmin:"):
        if not is_admin(user.id):
            await safe_edit(q, "Accès refusé.")
            return
        await admin_callback(q, context, data)
        return

    with db() as s:
        u = get_user(s, user)
        if u.banned:
            s.commit()
            await safe_edit(q, "Accès refusé.")
            return
        s.commit()

    if data == "bio:no":
        await safe_edit(q, f"Ajoute {PUBLIC_BIO_TAG} dans ta bio publique puis recommence avec /start.")
        return

    if data == "bio:yes":
        with db() as s:
            u = get_user(s, user)
            u.bio_declared = True
            s.commit()
        await safe_edit(q, f"Étape suivante : suis-tu le canal {MAIN_CHANNEL} ?", reply_markup=channel_buttons())
        return

    if data == "channel:check":
        ok = await is_channel_member(context, user.id)
        if not ok:
            await safe_edit(q, f"Je ne vois pas encore ton abonnement au canal {MAIN_CHANNEL}. Rejoins le canal puis réessaie.", reply_markup=channel_buttons())
            return
        with db() as s:
            u = get_user(s, user)
            u.channel_verified = True
            s.commit()
        await safe_edit(q, "Choisis une plateforme pour publier :", reply_markup=branch_buttons())
        return

    if data.startswith("branch:"):
        requested = data.split(":")[1]
        with db() as s:
            u = get_user(s, user)

            # Une branche est verrouillée dès qu'elle est attribuée.
            # L'utilisateur ne peut changer que si un admin refuse sa preuve.
            if u.branch and (u.waiting_first_proof or u.validated):
                locked = u.branch
                s.commit()
                await safe_edit(
                    q,
                    f"Tu as déjà une branche attribuée : {BRANCH_LABELS.get(locked, locked)}.\n\n"
                    "Envoie ta preuve ou attends la décision admin."
                )
                return

            branch = choose_balanced_branch(s, requested)
            u.branch = branch
            u.waiting_first_proof = True
            s.commit()

        if branch != requested:
            await safe_edit(
                q,
                f"Pour garder les groupes équilibrés, ta branche attribuée est : {BRANCH_LABELS[branch]}.\n\nJe t’envoie les instructions."
            )
        else:
            await safe_edit(q, "Je t’envoie les instructions.")

        await send_platform_content(context, user.id, branch)
        return

    if data == "proof:ready":
        await safe_edit(q, "Envoie maintenant ta capture d’écran ici dans le bot.")
        return


async def admin_callback(q, context, data):
    if data.startswith("proofadmin:"):
        _, action, proof_id_raw = data.split(":")
        proof_id = int(proof_id_raw)

        with db() as s:
            proof = s.query(Proof).filter_by(id=proof_id).first()
            if not proof:
                await safe_edit(q, "Preuve introuvable.")
                return

            u = s.query(User).filter_by(telegram_id=proof.telegram_id).first()
            if not u:
                await safe_edit(q, "Utilisateur introuvable.")
                return

            if proof.status != "pending":
                await delete_admin_proof_messages(context, proof_id)
                try:
                    await q.message.delete()
                except Exception:
                    pass
                return

            if action == "accept":
                proof.status = "accepted"
                u.proof_miss_count = 0

                if proof.kind == "first":
                    u.waiting_first_proof = False
                    u.validated = True

                s.commit()

                await delete_admin_proof_messages(context, proof_id)
                try:
                    await context.bot.send_message(u.telegram_id, "✅ Ta preuve a été acceptée.")
                except Exception:
                    pass

                if proof.kind == "first":
                    await send_invite(context, u.telegram_id)
                return

            if action == "refuse":
                proof.status = "refused"

                # Refus première preuve : l'utilisateur doit recommencer.
                # On libère la branche pour qu'il repasse par le parcours.
                if proof.kind == "first":
                    u.waiting_first_proof = False
                    u.validated = False
                    u.branch = None

                s.commit()

                await delete_admin_proof_messages(context, proof_id)
                try:
                    await context.bot.send_message(
                        u.telegram_id,
                        "❌ Ta preuve a été refusée. Tu dois recommencer le parcours avec /start."
                    )
                except Exception:
                    pass
                return

    if data == "admin:menu":
        await safe_edit(q, "🛠 Panel admin", reply_markup=admin_menu())
        return

    if data == "admin:groups":
        with db() as s:
            main = get_config(s, "main_group_id", "non défini")
            groups = s.query(PromoGroup).filter_by(active=True).all()
        txt = f"Groupe principal : {main}\n\nGroupes pub actifs :\n"
        txt += "\n".join([f"- {g.title or g.chat_id}" for g in groups]) if groups else "Aucun"
        txt += "\n\nCommandes : /setmain dans le groupe principal, /addpromo dans un groupe pub."
        await safe_edit(q, txt, reply_markup=admin_menu())
        return

    if data == "admin:ad":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Modifier texte pub", callback_data="ad:set_text")],
            [InlineKeyboardButton("🖼 Modifier photo pub", callback_data="ad:set_photo")],
            [InlineKeyboardButton("👀 Aperçu pub", callback_data="ad:preview")],
            [InlineKeyboardButton("🚀 Publier publicité", callback_data="ad:publish")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="admin:menu")]
        ])
        await safe_edit(q, "🧲 Gestion publicité", reply_markup=kb)
        return

    if data == "ad:set_text":
        context.user_data["admin_waiting"] = "ad_text"
        await safe_edit(q, "Envoie maintenant le texte de publicité.")
        return

    if data == "ad:set_photo":
        context.user_data["admin_waiting"] = "ad_photo"
        await safe_edit(q, "Envoie maintenant la photo de publicité.")
        return

    if data == "ad:preview":
        await send_ad_preview(context, q.message.chat_id)
        return

    if data == "ad:publish":
        await publish_ad(context)
        await safe_edit(q, "✅ Publicité publiée dans les groupes actifs.", reply_markup=admin_menu())
        return

    if data == "admin:platforms":
        await safe_edit(q, "Choisis une plateforme à configurer :", reply_markup=admin_platform_buttons())
        return

    if data.startswith("admbranch:"):
        branch = data.split(":")[1]
        context.user_data["admin_waiting"] = f"branch_text:{branch}"
        await safe_edit(q, f"Envoie le texte d’instructions pour {BRANCH_LABELS[branch]}. Ensuite, tu pourras envoyer la photo.")
        return

    if data == "admin:reward":
        context.user_data["admin_waiting"] = "reward"
        await safe_edit(q, "Envoie maintenant le lien récompense à publier ce soir.")
        return

    if data == "admin:stats":
        with db() as s:
            users = s.query(User).count()
            valid = s.query(User).filter_by(validated=True, banned=False).count()
            joined = s.query(User).filter_by(validated=True, banned=False, joined_main=True).count()
            rewards = s.query(Reward).filter_by(published=False).count()
            proofs = s.query(Proof).filter_by(proof_date=today()).count()
        await safe_edit(q, f"Utilisateurs : {users}\nValidés : {valid}\nDans groupe : {joined}\nPreuves aujourd’hui : {proofs}\nRécompenses en attente : {rewards}", reply_markup=admin_menu())
        return


async def admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    waiting = context.user_data.get("admin_waiting")
    if not waiting:
        return

    with db() as s:
        if waiting == "ad_text" and update.message.text:
            set_config(s, "ad_text", update.message.text)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Texte publicité enregistré.", reply_markup=admin_menu())
            return

        if waiting == "ad_photo" and update.message.photo:
            set_config(s, "ad_photo", update.message.photo[-1].file_id)
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Photo publicité enregistrée.", reply_markup=admin_menu())
            return

        if waiting == "reward" and update.message.text:
            s.add(Reward(url=update.message.text.strip()))
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Lien récompense ajouté.", reply_markup=admin_menu())
            return

        if waiting.startswith("branch_text:") and update.message.text:
            branch = waiting.split(":")[1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.instructions = update.message.text
            s.commit()
            context.user_data["admin_waiting"] = f"branch_photo:{branch}"
            await update.message.reply_text("✅ Texte enregistré. Envoie maintenant la photo pour cette plateforme.")
            return

        if waiting.startswith("branch_photo:") and update.message.photo:
            branch = waiting.split(":")[1]
            row = s.query(BranchContent).filter_by(branch=branch).first()
            if not row:
                row = BranchContent(branch=branch)
                s.add(row)
            row.photo_file_id = update.message.photo[-1].file_id
            s.commit()
            context.user_data.pop("admin_waiting", None)
            await update.message.reply_text("✅ Photo enregistrée.", reply_markup=admin_menu())
            return


async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id) or not update.message.photo:
        return

    with db() as s:
        u = get_user(s, user)
        if u.banned:
            s.commit()
            return

        kind = "first" if u.waiting_first_proof and not u.validated else "daily"

        proof = Proof(
            telegram_id=user.id,
            file_id=update.message.photo[-1].file_id,
            proof_date=today(),
            kind=kind,
            status="pending"
        )
        s.add(proof)
        s.flush()
        proof_id = proof.id
        s.commit()

    await update.message.reply_text("✅ Preuve reçue. Elle est envoyée aux admins pour validation.")
    await send_proof_to_admins(context, proof_id)


async def main_group_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not update.message or not update.message.new_chat_members:
        return

    with db() as s:
        main_id = get_config(s, "main_group_id", "")

    if not main_id or str(chat.id) != str(main_id):
        return

    for member in update.message.new_chat_members:
        with db() as s:
            u = s.query(User).filter_by(telegram_id=member.id).first()
            allowed = bool(u and u.validated and not u.banned and not reward_lock_active())
            if allowed:
                u.joined_main = True
                s.commit()
                continue
            s.commit()

        try:
            await context.bot.ban_chat_member(chat.id, member.id)
            await context.bot.unban_chat_member(chat.id, member.id)
        except Exception:
            pass


async def send_ad_preview(context, chat_id):
    with db() as s:
        text = get_config(s, "ad_text", "Recevez les médias du jour. Cliquez ci-dessous pour commencer.")
        photo = get_config(s, "ad_photo", "")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Je suis intéressé", url=bot_url())]])
    if photo:
        await context.bot.send_photo(chat_id, photo=photo, caption=text, reply_markup=kb)
    else:
        await context.bot.send_message(chat_id, text, reply_markup=kb)


async def publish_ad(context):
    with db() as s:
        groups = s.query(PromoGroup).filter_by(active=True).all()
        text = get_config(s, "ad_text", "Recevez les médias du jour. Cliquez ci-dessous pour commencer.")
        photo = get_config(s, "ad_photo", "")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Je suis intéressé", url=bot_url())]])
    for g in groups:
        try:
            if photo:
                await context.bot.send_photo(g.chat_id, photo=photo, caption=text, reply_markup=kb)
            else:
                await context.bot.send_message(g.chat_id, text, reply_markup=kb)
        except Exception:
            pass


async def proof_deadline_job(context):
    with db() as s:
        if job_done(s, "proof_deadline") or not proof_cutoff_passed():
            return
        users = s.query(User).filter_by(validated=True, banned=False, joined_main=True).all()
        main_id = get_config(s, "main_group_id", "")
        mark_job(s, "proof_deadline")
        s.commit()

    kicked = 0
    banned = 0

    for u in users:
        with db() as s:
            has = s.query(Proof).filter_by(telegram_id=u.telegram_id, proof_date=today(), status="accepted").first()
            uu = s.query(User).filter_by(telegram_id=u.telegram_id).first()
            if has or not uu:
                continue
            uu.joined_main = False
            uu.validated = False
            uu.proof_miss_count = (uu.proof_miss_count or 0) + 1
            permanent = uu.proof_miss_count >= 2
            if permanent:
                uu.banned = True
                uu.banned_reason = "Deux absences de preuve"
                banned += 1
            else:
                kicked += 1
            s.commit()

        try:
            await context.bot.ban_chat_member(int(main_id), u.telegram_id)
            if not permanent:
                await context.bot.unban_chat_member(int(main_id), u.telegram_id)
        except Exception:
            pass

    await notify_admins(context, f"Contrôle preuves terminé. Kick: {kicked}, bans: {banned}")


async def reward_job(context):
    with db() as s:
        if job_done(s, "reward_publish") or not reward_due():
            return
        main_id = get_config(s, "main_group_id", "")
        valid_count = s.query(User).filter_by(validated=True, banned=False, joined_main=True).count()
        reward = s.query(Reward).filter_by(published=False).order_by(Reward.created_at.asc()).first()

        if not main_id:
            return

        if valid_count <= 0:
            await notify_admins(context, "⚠️ Récompense non publiée : aucun utilisateur validé dans le groupe.")
            mark_job(s, "reward_publish")
            s.commit()
            return

        if not reward:
            await notify_admins(context, "⚠️ Aucun lien récompense ajouté alors qu’il y a des utilisateurs validés.")
            return

        rid = reward.id
        url = reward.url
        mark_job(s, "reward_publish")
        s.commit()

    try:
        msg = await context.bot.send_message(int(main_id), f"🎁 Récompense du jour :\n{url}")
        with db() as s:
            r = s.query(Reward).filter_by(id=rid).first()
            if r:
                r.published = True
                r.published_at = now()
                r.message_id = msg.message_id
            s.commit()
        await notify_admins(context, "✅ Récompense publiée. Elle sera supprimée automatiquement dans 2h.")
    except Exception as e:
        await notify_admins(context, f"Erreur publication récompense : {e}")


async def reward_delete_job(context):
    with db() as s:
        main_id = get_config(s, "main_group_id", "")
        rows = s.query(Reward).filter(Reward.published == True, Reward.deleted_at == None, Reward.message_id != None).all()

    if not main_id:
        return

    for r in rows:
        if not r.published_at:
            continue
        if now() < r.published_at + timedelta(hours=REWARD_DELETE_AFTER_HOURS):
            continue
        try:
            await context.bot.delete_message(int(main_id), int(r.message_id))
            with db() as s:
                rr = s.query(Reward).filter_by(id=r.id).first()
                if rr:
                    rr.deleted_at = now()
                s.commit()
        except Exception:
            pass


async def reward_reminder_job(context):
    with db() as s:
        valid_count = s.query(User).filter_by(validated=True, banned=False, joined_main=True).count()
        pending = s.query(Reward).filter_by(published=False).count()
    if valid_count > 0 and pending == 0:
        await notify_admins(context, f"⏰ Rappel : {valid_count} utilisateurs validés, mais aucun lien récompense en attente.")


async def catchup(context):
    await proof_deadline_job(context)
    await reward_job(context)
    await reward_delete_job(context)


async def boot(context):
    await catchup(context)
    await notify_admins(context, "✅ Bot V2 final démarré.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["setmain", "addpromo", "panel"], admin_commands))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, main_group_join))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, receive_proof), group=1)
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & filters.ChatType.PRIVATE, admin_input), group=2)

    app.job_queue.run_once(boot, when=5)
    app.job_queue.run_repeating(catchup, interval=300, first=60)
    app.job_queue.run_daily(proof_deadline_job, time=time(hour=PROOF_KICK_HOUR, minute=PROOF_KICK_MINUTE))
    app.job_queue.run_daily(reward_job, time=time(hour=REWARD_HOUR, minute=REWARD_MINUTE))
    app.job_queue.run_repeating(reward_delete_job, interval=300, first=120)

    for h in ADMIN_REWARD_REMINDER_HOURS:
        app.job_queue.run_daily(reward_reminder_job, time=time(hour=h, minute=0))

    print("Bot V2 final started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
