
import os
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMemberUpdated, InputMediaPhoto
)
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError, Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ChatMemberHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("promo-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
TZ = ZoneInfo(os.getenv("TZ", "Europe/Paris"))
REQUIRED_BIO = os.getenv("REQUIRED_BIO", "@antijavana").lower()
DB_PATH = os.getenv("DB_PATH", "bot.db")

BRANCHES = ["tiktok", "leakmedia", "reddit", "discord"]
BRANCH_LABELS = {
    "tiktok": "TikTok",
    "leakmedia": "Leakmedia",
    "reddit": "Reddit",
    "discord": "Discord",
}

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS groups (
        chat_id INTEGER PRIMARY KEY,
        title TEXT,
        kind TEXT DEFAULT 'promo',
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TEXT,
        status TEXT DEFAULT 'joined',
        branch TEXT,
        confirmed INTEGER DEFAULT 0,
        last_proof_at TEXT,
        last_private_at TEXT
    );
    CREATE TABLE IF NOT EXISTS branch_content (
        branch TEXT PRIMARY KEY,
        text TEXT,
        photo_file_id TEXT
    );
    CREATE TABLE IF NOT EXISTS reward_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS proofs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        file_id TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'pending'
    );
    """)
    defaults = {
        "ad_text": "Si vous voulez recevoir 200 médias par jour, cliquez ci-dessous.",
        "ad_photo_file_id": "",
        "welcome_text": "Bonjour, vous êtes un vrai membre. Merci pour votre bio. Pour recevoir ici tous les jours de nouveaux médias, il faut publier le groupe sur TikTok, Leakmedia, Reddit ou Discord.",
        "private_intro": "Félicitations, vous pouvez choisir une plateforme ci-dessous.",
        "proof_reminder": "Envoyez votre capture d’écran de preuve avant 22h.",
        "central_chat_id": "",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    for b in BRANCHES:
        cur.execute("INSERT OR IGNORE INTO branch_content(branch,text,photo_file_id) VALUES(?,?,?)",
                    (b, f"Instructions pour {BRANCH_LABELS[b]} à configurer dans le panel admin.", ""))
    con.commit()
    con.close()

def get_setting(key: str, default: str = "") -> str:
    con = db()
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    con.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    con = db()
    con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    con.commit()
    con.close()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Message pub", callback_data="admin:set_ad"),
         InlineKeyboardButton("👋 Message accueil", callback_data="admin:set_welcome")],
        [InlineKeyboardButton("🖼 Contenus plateformes", callback_data="admin:branches"),
         InlineKeyboardButton("🔗 Lien récompense", callback_data="admin:set_reward")],
        [InlineKeyboardButton("📌 Publier pub", callback_data="admin:publish_ad"),
         InlineKeyboardButton("🎁 Publier récompense", callback_data="admin:publish_reward")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin:stats"),
         InlineKeyboardButton("⚙️ Groupes", callback_data="admin:groups")],
    ])

def join_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Je veux rejoindre", callback_data="join:start")]])

def interested_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Je suis intéressé", callback_data="flow:interested")]])

def branch_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TikTok", callback_data="branch:tiktok"),
         InlineKeyboardButton("Leakmedia", callback_data="branch:leakmedia")],
        [InlineKeyboardButton("Reddit", callback_data="branch:reddit"),
         InlineKeyboardButton("Discord", callback_data="branch:discord")],
    ])

def confirm_keyboard(branch: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ OUI", callback_data=f"confirm:yes:{branch}"),
         InlineKeyboardButton("❌ NON", callback_data=f"confirm:no:{branch}")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_admin(user.id):
        await update.effective_message.reply_text("Panel admin :", reply_markup=admin_keyboard())
    else:
        await update.effective_message.reply_text("Bienvenue. Utilise les boutons dans le groupe pour continuer.")

async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: ChatMemberUpdated = update.my_chat_member
    chat = m.chat
    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        con = db()
        con.execute("INSERT OR REPLACE INTO groups(chat_id,title,kind,created_at) VALUES(?,?,COALESCE((SELECT kind FROM groups WHERE chat_id=?),'promo'),?)",
                    (chat.id, chat.title or "", chat.id, datetime.now(TZ).isoformat()))
        con.commit(); con.close()
        log.info("Registered chat %s %s", chat.id, chat.title)

async def register_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        con = db()
        con.execute("INSERT OR IGNORE INTO groups(chat_id,title,kind,created_at) VALUES(?,?,?,?)",
                    (chat.id, chat.title or "", "promo", datetime.now(TZ).isoformat()))
        con.commit(); con.close()

async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("Accès refusé.")
        return
    data = q.data

    if data == "admin:stats":
        con = db()
        users = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        rows = con.execute("SELECT branch, COUNT(*) c FROM users WHERE branch IS NOT NULL GROUP BY branch").fetchall()
        proofs = con.execute("SELECT COUNT(*) c FROM proofs WHERE date(created_at)=date('now')").fetchone()["c"]
        con.close()
        lines = [f"👥 Utilisateurs: {users}", f"🧾 Preuves aujourd’hui: {proofs}", "", "Répartition:"]
        lines += [f"- {BRANCH_LABELS.get(r['branch'], r['branch'])}: {r['c']}" for r in rows] or ["Aucune branche."]
        await q.edit_message_text("\n".join(lines), reply_markup=admin_keyboard())
    elif data == "admin:groups":
        con = db()
        rows = con.execute("SELECT chat_id,title,kind FROM groups ORDER BY created_at DESC LIMIT 20").fetchall()
        con.close()
        kb = []
        text = "Groupes détectés:\n"
        for r in rows:
            text += f"\n{r['title']} — `{r['chat_id']}` — {r['kind']}"
            kb.append([InlineKeyboardButton(f"Central: {r['title'][:25]}", callback_data=f"setcentral:{r['chat_id']}")])
        kb.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:back")])
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("setcentral:"):
        chat_id = data.split(":", 1)[1]
        set_setting("central_chat_id", chat_id)
        con = db(); con.execute("UPDATE groups SET kind='central' WHERE chat_id=?", (int(chat_id),)); con.commit(); con.close()
        await q.edit_message_text("Groupe central enregistré.", reply_markup=admin_keyboard())
    elif data == "admin:branches":
        await q.edit_message_text("Choisis la plateforme à configurer :", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(BRANCH_LABELS[b], callback_data=f"admin:editbranch:{b}")] for b in BRANCHES
        ] + [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:back")]]))
    elif data.startswith("admin:editbranch:"):
        branch = data.split(":")[-1]
        context.user_data["admin_wait"] = f"branch:{branch}"
        await q.edit_message_text(f"Envoie maintenant la photo avec la légende/instructions pour {BRANCH_LABELS[branch]}.")
    elif data == "admin:set_ad":
        context.user_data["admin_wait"] = "ad"
        await q.edit_message_text("Envoie maintenant la photo de pub avec le texte en légende.")
    elif data == "admin:set_welcome":
        context.user_data["admin_wait"] = "welcome"
        await q.edit_message_text("Envoie maintenant le texte d’accueil du groupe central.")
    elif data == "admin:set_reward":
        context.user_data["admin_wait"] = "reward"
        await q.edit_message_text("Envoie maintenant le lien récompense à publier.")
    elif data == "admin:publish_ad":
        await publish_ad(context)
        await q.edit_message_text("Pub envoyée aux groupes promo détectés.", reply_markup=admin_keyboard())
    elif data == "admin:publish_reward":
        await publish_reward(context)
        await q.edit_message_text("Récompense publiée dans le groupe central.", reply_markup=admin_keyboard())
    elif data == "admin:back":
        await q.edit_message_text("Panel admin :", reply_markup=admin_keyboard())

async def admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    wait = context.user_data.get("admin_wait")
    if not wait:
        return
    msg = update.effective_message
    if wait == "ad":
        set_setting("ad_text", msg.caption or msg.text or "")
        if msg.photo:
            set_setting("ad_photo_file_id", msg.photo[-1].file_id)
        context.user_data.pop("admin_wait", None)
        await msg.reply_text("Pub enregistrée.", reply_markup=admin_keyboard())
    elif wait == "welcome":
        set_setting("welcome_text", msg.text or msg.caption or "")
        context.user_data.pop("admin_wait", None)
        await msg.reply_text("Message d’accueil enregistré.", reply_markup=admin_keyboard())
    elif wait == "reward":
        url = (msg.text or msg.caption or "").strip()
        con = db()
        con.execute("INSERT INTO reward_links(url,active,created_at) VALUES(?,?,?)", (url, 1, datetime.now(TZ).isoformat()))
        con.commit(); con.close()
        context.user_data.pop("admin_wait", None)
        await msg.reply_text("Lien récompense enregistré.", reply_markup=admin_keyboard())
    elif wait.startswith("branch:"):
        branch = wait.split(":")[1]
        text = msg.caption or msg.text or ""
        photo = msg.photo[-1].file_id if msg.photo else ""
        con = db()
        con.execute("UPDATE branch_content SET text=?, photo_file_id=? WHERE branch=?", (text, photo, branch))
        con.commit(); con.close()
        context.user_data.pop("admin_wait", None)
        await msg.reply_text(f"Contenu {BRANCH_LABELS[branch]} enregistré.", reply_markup=admin_keyboard())

async def publish_ad(context: ContextTypes.DEFAULT_TYPE):
    text = get_setting("ad_text")
    photo = get_setting("ad_photo_file_id")
    con = db()
    groups = con.execute("SELECT chat_id FROM groups WHERE kind='promo'").fetchall()
    con.close()
    for g in groups:
        try:
            if photo:
                await context.bot.send_photo(g["chat_id"], photo=photo, caption=text, reply_markup=join_keyboard())
            else:
                await context.bot.send_message(g["chat_id"], text, reply_markup=join_keyboard())
        except TelegramError as e:
            log.warning("publish_ad failed %s: %s", g["chat_id"], e)

async def publish_reward(context: ContextTypes.DEFAULT_TYPE):
    central = get_setting("central_chat_id")
    if not central:
        return
    con = db()
    row = con.execute("SELECT url FROM reward_links WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    if row:
        await context.bot.send_message(int(central), f"🎁 Récompense du jour :\n{row['url']}")

async def join_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    central = get_setting("central_chat_id")
    if central:
        await q.message.reply_text("Clique ici pour rejoindre le groupe central. Une fois dedans, suis les instructions.")
    else:
        await q.message.reply_text("Le groupe central n’est pas encore configuré.")

async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    central = get_setting("central_chat_id")
    if not central or str(chat.id) != str(central):
        return
    for member in update.message.new_chat_members:
        status = "joined"
        try:
            full = await context.bot.get_chat(member.id)
            bio = (full.bio or "").lower()
            if REQUIRED_BIO not in bio:
                status = "bio_missing"
                await chat.ban_member(member.id)
                await chat.unban_member(member.id)
                continue
        except TelegramError:
            # Telegram ne donne pas toujours la bio via Bot API.
            status = "bio_unknown"
        con = db()
        con.execute("""INSERT INTO users(user_id,username,first_name,joined_at,status)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET joined_at=excluded.joined_at,status=excluded.status""",
                    (member.id, member.username or "", member.first_name or "", datetime.now(TZ).isoformat(), status))
        con.commit(); con.close()
        await update.message.reply_text(get_setting("welcome_text"), reply_markup=interested_keyboard())
        context.job_queue.run_once(kick_if_not_confirmed, when=timedelta(hours=3), data={"chat_id": chat.id, "user_id": member.id}, name=f"kick_{member.id}")

async def flow_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "flow:interested":
        try:
            await context.bot.send_message(q.from_user.id, get_setting("private_intro"), reply_markup=branch_keyboard())
            con = db()
            con.execute("UPDATE users SET last_private_at=? WHERE user_id=?", (datetime.now(TZ).isoformat(), q.from_user.id))
            con.commit(); con.close()
            await q.message.reply_text("Je t’ai envoyé les choix en privé.")
        except Forbidden:
            await q.message.reply_text("Ouvre d’abord une conversation privée avec le bot puis reclique sur le bouton.")

def choose_balanced_branch(wanted: str) -> str:
    con = db()
    counts = {b: 0 for b in BRANCHES}
    for r in con.execute("SELECT branch, COUNT(*) c FROM users WHERE confirmed=1 AND branch IS NOT NULL GROUP BY branch"):
        counts[r["branch"]] = r["c"]
    con.close()
    min_count = min(counts.values())
    # autorise le choix demandé seulement s'il n'est pas en avance de plus d'1
    if counts[wanted] <= min_count + 1:
        return wanted
    return sorted(BRANCHES, key=lambda b: counts[b])[0]

async def branch_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    wanted = q.data.split(":")[1]
    branch = choose_balanced_branch(wanted)
    if branch != wanted:
        await q.message.reply_text(f"Pour garder une répartition équilibrée, je te propose plutôt : {BRANCH_LABELS[branch]}.")
    con = db()
    row = con.execute("SELECT text,photo_file_id FROM branch_content WHERE branch=?", (branch,)).fetchone()
    con.close()
    text = row["text"] if row else ""
    photo = row["photo_file_id"] if row else ""
    if photo:
        await q.message.reply_photo(photo=photo, caption=text, reply_markup=confirm_keyboard(branch))
    else:
        await q.message.reply_text(text or f"Instructions {BRANCH_LABELS[branch]}", reply_markup=confirm_keyboard(branch))

async def confirm_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, yesno, branch = q.data.split(":")
    uid = q.from_user.id
    central = get_setting("central_chat_id")
    if yesno == "yes":
        con = db()
        con.execute("""INSERT INTO users(user_id,username,first_name,joined_at,status,branch,confirmed)
                       VALUES(?,?,?,?,?,?,1)
                       ON CONFLICT(user_id) DO UPDATE SET status='confirmed', branch=?, confirmed=1""",
                    (uid, q.from_user.username or "", q.from_user.first_name or "", datetime.now(TZ).isoformat(), "confirmed", branch, branch))
        con.commit(); con.close()
        await q.message.reply_text("Parfait. Envoie chaque jour ta capture d’écran de preuve avant 22h.")
    else:
        con = db(); con.execute("UPDATE users SET status='refused', confirmed=0 WHERE user_id=?", (uid,)); con.commit(); con.close()
        await q.message.reply_text("D’accord. Tu seras retiré du groupe central.")
        if central:
            try:
                await context.bot.ban_chat_member(int(central), uid)
                await context.bot.unban_chat_member(int(central), uid)
            except TelegramError:
                pass

async def proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not user or not msg.photo:
        return
    con = db()
    row = con.execute("SELECT confirmed FROM users WHERE user_id=?", (user.id,)).fetchone()
    if row and row["confirmed"]:
        con.execute("INSERT INTO proofs(user_id,file_id,created_at,status) VALUES(?,?,?,?)",
                    (user.id, msg.photo[-1].file_id, datetime.now(TZ).isoformat(), "pending"))
        con.execute("UPDATE users SET last_proof_at=? WHERE user_id=?", (datetime.now(TZ).isoformat(), user.id))
        con.commit()
        await msg.reply_text("Preuve reçue ✅")
    con.close()

async def kick_if_not_confirmed(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    con = db()
    row = con.execute("SELECT confirmed FROM users WHERE user_id=?", (data["user_id"],)).fetchone()
    con.close()
    if not row or not row["confirmed"]:
        try:
            await context.bot.ban_chat_member(data["chat_id"], data["user_id"])
            await context.bot.unban_chat_member(data["chat_id"], data["user_id"])
        except TelegramError as e:
            log.warning("kick failed: %s", e)

async def daily_proof_check(context: ContextTypes.DEFAULT_TYPE):
    central = get_setting("central_chat_id")
    if not central:
        return
    now = datetime.now(TZ)
    today = now.date().isoformat()
    con = db()
    rows = con.execute("SELECT user_id,last_proof_at FROM users WHERE confirmed=1").fetchall()
    con.close()
    for r in rows:
        ok = r["last_proof_at"] and r["last_proof_at"].startswith(today)
        if not ok:
            try:
                await context.bot.ban_chat_member(int(central), int(r["user_id"]))
                await context.bot.unban_chat_member(int(central), int(r["user_id"]))
            except TelegramError as e:
                log.warning("daily kick failed: %s", e)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Missing BOT_TOKEN")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))
    app.add_handler(CallbackQueryHandler(admin_callbacks, pattern=r"^(admin:|setcentral:)"))
    app.add_handler(CallbackQueryHandler(join_flow, pattern=r"^join:"))
    app.add_handler(CallbackQueryHandler(flow_callbacks, pattern=r"^flow:"))
    app.add_handler(CallbackQueryHandler(branch_callbacks, pattern=r"^branch:"))
    app.add_handler(CallbackQueryHandler(confirm_callbacks, pattern=r"^confirm:"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, proof_handler))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO), admin_input))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, register_group_message))

    app.job_queue.run_daily(daily_proof_check, time=time(hour=22, minute=0, tzinfo=TZ), name="daily_proof_check")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
