import { Markup } from "telegraf";

const BOT_USERNAME = process.env.BOT_USERNAME || "GrosChatVIP_bot";

export function teaserKeyboard() {
  return Markup.inlineKeyboard([
    [Markup.button.url("🎁 VIP Gratuit", `https://t.me/${BOT_USERNAME}?start=free`)],
    [Markup.button.url("🔥 VIP Premium (+80 000 médias)", `https://t.me/${BOT_USERNAME}?start=premium`)]
  ]);
}

export function freeUpsellKeyboard() {
  return Markup.inlineKeyboard([
    [Markup.button.callback("🔥 Je suis intéressé par le VIP Premium", "interest_premium")]
  ]);
}

export function adminKeyboard(autoPub = "off") {
  const autoLabel = autoPub === "on" ? "🔁 Auto-pub 20 min : ON" : "🔁 Auto-pub 20 min : OFF";

  return Markup.inlineKeyboard([
    [Markup.button.callback("📊 Actualiser stats", "admin_stats")],
    [Markup.button.callback("🚀 Publier teaser maintenant", "admin_publish_once")],
    [Markup.button.callback(autoLabel, "admin_toggle_autopub")],
    [Markup.button.callback("📢 Broadcast Premium", "admin_broadcast_premium")],
    [Markup.button.callback("🎁 Broadcast Gratuit", "admin_broadcast_free")],
    [Markup.button.callback("👥 Broadcast Tous", "admin_broadcast_all")],
    [Markup.button.callback("📜 Logs récents", "admin_logs")],
    [Markup.button.callback("ℹ️ Vérification système", "admin_health")],
    [Markup.button.callback("🗑 Supprimer dernière pub", "admin_delete_last")]
  ]);
}
