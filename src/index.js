import "dotenv/config";
import express from "express";
import cron from "node-cron";
import { Telegraf } from "telegraf";
import {
  initDb,
  pool,
  markFree,
  markPremium,
  getStats,
  setSetting,
  getSetting,
  getUsersBySegment,
  getRecentLogs,
  addLog
} from "./db.js";
import {
  teaserCaption,
  freeMessage,
  premiumMessage,
  alreadyFreeMessage,
  alreadyPremiumMessage
} from "./messages.js";
import {
  teaserKeyboard,
  freeUpsellKeyboard,
  adminKeyboard
} from "./keyboards.js";

const BOT_TOKEN = process.env.BOT_TOKEN;
const GROUP_ID = process.env.GROUP_ID;
const TEASER_PHOTO_URL = process.env.TEASER_PHOTO_URL;
const ADMIN_IDS = (process.env.ADMIN_IDS || "")
  .split(",")
  .map(x => Number(x.trim()))
  .filter(Boolean);

if (!BOT_TOKEN) throw new Error("BOT_TOKEN manquant");
if (!GROUP_ID) console.warn("⚠️ GROUP_ID manquant");
if (!TEASER_PHOTO_URL) console.warn("⚠️ TEASER_PHOTO_URL manquant");

const bot = new Telegraf(BOT_TOKEN);

function isAdmin(ctx) {
  return ADMIN_IDS.includes(ctx.from?.id);
}

async function safeReply(ctx, text, extra = {}) {
  try {
    return await ctx.reply(text, extra);
  } catch (err) {
    console.error("reply error:", err.message);
  }
}

async function publishTeaser() {
  if (!GROUP_ID) throw new Error("GROUP_ID manquant");
  if (!TEASER_PHOTO_URL) throw new Error("TEASER_PHOTO_URL manquant");

  const sent = await bot.telegram.sendPhoto(
    GROUP_ID,
    TEASER_PHOTO_URL,
    {
      caption: teaserCaption,
      parse_mode: undefined,
      ...teaserKeyboard()
    }
  );

  await setSetting("last_pub_message_id", String(sent.message_id));
  return sent;
}

async function renderAdminPanel(ctx, edit = false) {
  const stats = await getStats();

  const text = `🛠 PANEL ADMIN

📊 Statistiques
👥 Total utilisateurs : ${stats.total}
🎁 Intéressés VIP Gratuit : ${stats.free}
🔥 Intéressés VIP Premium : ${stats.premium}
🔁 Gratuit → Premium : ${stats.both}

📢 Auto-pub 20 min : ${stats.autoPub?.toUpperCase() || "OFF"}`;

  const keyboard = adminKeyboard(stats.autoPub);

  if (edit && ctx.updateType === "callback_query") {
    return ctx.editMessageText(text, keyboard).catch(() => ctx.reply(text, keyboard));
  }

  return ctx.reply(text, keyboard);
}

async function checkBotAdmin() {
  if (!GROUP_ID) return { ok: false, text: "GROUP_ID manquant" };

  const me = await bot.telegram.getMe();
  const member = await bot.telegram.getChatMember(GROUP_ID, me.id);

  const isAdminStatus = ["administrator", "creator"].includes(member.status);

  return {
    ok: isAdminStatus,
    text: isAdminStatus ? "Bot admin du groupe" : `Bot non admin. Status: ${member.status}`
  };
}

async function healthCheck() {
  const checks = [];

  try {
    const me = await bot.telegram.getMe();
    checks.push(`🟢 Bot connecté : @${me.username}`);
  } catch (e) {
    checks.push(`🔴 Bot Telegram KO : ${e.message}`);
  }

  try {
    const chat = await bot.telegram.getChat(GROUP_ID);
    checks.push(`🟢 Groupe connecté : ${chat.title || GROUP_ID}`);
  } catch (e) {
    checks.push(`🔴 Groupe KO : ${e.message}`);
  }

  try {
    const admin = await checkBotAdmin();
    checks.push(`${admin.ok ? "🟢" : "🔴"} Permissions : ${admin.text}`);
  } catch (e) {
    checks.push(`🔴 Permissions KO : ${e.message}`);
  }

  try {
    await pool.query("SELECT 1");
    checks.push("🟢 PostgreSQL connecté");
  } catch (e) {
    checks.push(`🔴 PostgreSQL KO : ${e.message}`);
  }

  try {
    const stats = await getStats();
    checks.push(`🟢 DB lisible : ${stats.total} utilisateur(s)`);
    checks.push(`🟢 Auto-pub : ${stats.autoPub?.toUpperCase() || "OFF"}`);
  } catch (e) {
    checks.push(`🔴 Lecture stats KO : ${e.message}`);
  }

  const uptimeHours = Math.floor(process.uptime() / 3600);
  const uptimeMinutes = Math.floor((process.uptime() % 3600) / 60);
  checks.push(`⏱ Uptime : ${uptimeHours}h ${uptimeMinutes}min`);

  const hasError = checks.some(x => x.startsWith("🔴"));

  return `${hasError ? "🔴 ERREURS DÉTECTÉES" : "🟢 SYSTÈME OPÉRATIONNEL"}

${checks.join("\n")}`;
}

async function broadcastSegment(ctx, segment) {
  const labels = {
    premium: "VIP Premium",
    free: "VIP Gratuit",
    all: "Tous"
  };

  const users = await getUsersBySegment(segment);
  let ok = 0;
  let fail = 0;

  const text = `🚀 Le VIP arrive bientôt.

L’ouverture approche. Tu seras informé en priorité dès que le groupe sera disponible.

📦 +80 000 médias
📈 +500 nouveaux médias/jour
💰 Prix prévu : entre 10€ et 20€`;

  await ctx.reply(`📢 Broadcast ${labels[segment]} lancé vers ${users.length} utilisateur(s).`);

  for (const userId of users) {
    try {
      await bot.telegram.sendMessage(userId, text);
      ok++;
      await new Promise(resolve => setTimeout(resolve, 80));
    } catch (e) {
      fail++;
    }
  }

  await ctx.reply(`✅ Broadcast terminé.

Envoyés : ${ok}
Échecs : ${fail}`);
}

bot.start(async ctx => {
  await safeReply(ctx, "Bienvenue 👋\nLe VIP arrive bientôt. Surveille le groupe pour le teaser.");
});

bot.command("admin", async ctx => {
  if (!isAdmin(ctx)) return safeReply(ctx, "⛔ Accès refusé.");
  await renderAdminPanel(ctx);
});

bot.on("message", async ctx => {
  if (ctx.chat?.id) {
    console.log("Message reçu dans chat:", ctx.chat.id, ctx.chat.title || ctx.chat.type);
  }
});

bot.action("interest_free", async ctx => {
  await ctx.answerCbQuery().catch(() => {});
  const result = await markFree(ctx);

  if (result.already) {
    return ctx.reply(alreadyFreeMessage, freeUpsellKeyboard());
  }

  if (result.realPosition > 50) {
    return ctx.reply(
      `🎁 Tu es actuellement ${result.position}e sur la liste d’attente du VIP Gratuit.

Les 50 premières places gratuites sont déjà très demandées.

🔥 Tu peux rejoindre la liste prioritaire VIP Premium pour être prévenu en premier.`,
      freeUpsellKeyboard()
    );
  }

  return ctx.reply(freeMessage(result.position), freeUpsellKeyboard());
});

bot.action("interest_premium", async ctx => {
  await ctx.answerCbQuery().catch(() => {});
  const result = await markPremium(ctx);

  if (result.already) {
    return ctx.reply(alreadyPremiumMessage);
  }

  return ctx.reply(premiumMessage);
});

bot.action("admin_stats", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});
  await renderAdminPanel(ctx, true);
});

bot.action("admin_publish_once", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery("Publication...");
  try {
    await checkBotAdmin();
    await publishTeaser();
    await addLog(ctx, "ADMIN_PUBLISH_ONCE");
    await ctx.reply("✅ Teaser publié dans le groupe.");
  } catch (e) {
    await ctx.reply(`❌ Publication impossible : ${e.message}`);
  }
});

bot.action("admin_toggle_autopub", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});

  const current = await getSetting("auto_pub");
  const next = current === "on" ? "off" : "on";
  await setSetting("auto_pub", next);
  await addLog(ctx, `ADMIN_AUTO_PUB_${next.toUpperCase()}`);

  await renderAdminPanel(ctx, true);
});

bot.action("admin_broadcast_premium", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});
  await broadcastSegment(ctx, "premium");
});

bot.action("admin_broadcast_free", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});
  await broadcastSegment(ctx, "free");
});

bot.action("admin_broadcast_all", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});
  await broadcastSegment(ctx, "all");
});

bot.action("admin_logs", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});

  const logs = await getRecentLogs(10);

  if (!logs.length) return ctx.reply("📜 Aucun log pour le moment.");

  const text = logs.map(l => {
    const user = l.username ? `@${l.username}` : l.telegram_id || "unknown";
    return `• ${user} — ${l.action} — ${new Date(l.created_at).toLocaleString("fr-FR")}`;
  }).join("\n");

  await ctx.reply(`📜 Logs récents\n\n${text}`);
});

bot.action("admin_health", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});
  const text = await healthCheck();
  await ctx.reply(text);
});

bot.action("admin_delete_last", async ctx => {
  if (!isAdmin(ctx)) return ctx.answerCbQuery("Accès refusé");
  await ctx.answerCbQuery().catch(() => {});

  const lastId = await getSetting("last_pub_message_id");
  if (!lastId) return ctx.reply("ℹ️ Aucune dernière publication enregistrée.");

  try {
    await bot.telegram.deleteMessage(GROUP_ID, Number(lastId));
    await setSetting("last_pub_message_id", "");
    await addLog(ctx, "ADMIN_DELETE_LAST_PUB");
    await ctx.reply("🗑 Dernière pub supprimée.");
  } catch (e) {
    await ctx.reply(`❌ Impossible de supprimer : ${e.message}`);
  }
});

cron.schedule("*/20 * * * *", async () => {
  try {
    const autoPub = await getSetting("auto_pub");
    if (autoPub !== "on") return;

    await publishTeaser();
    console.log("✅ Auto-pub publiée");
  } catch (e) {
    console.error("❌ Auto-pub erreur:", e.message);
  }
});

const app = express();

app.get("/", (_, res) => {
  res.send("VIP teaser bot is running.");
});

app.get("/health", async (_, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

async function main() {
  await initDb();

  const port = Number(process.env.PORT || 3000);
  app.listen(port, () => console.log(`HTTP server running on ${port}`));

  await bot.launch();
  console.log("🤖 Bot lancé");

  process.once("SIGINT", () => bot.stop("SIGINT"));
  process.once("SIGTERM", () => bot.stop("SIGTERM"));
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
