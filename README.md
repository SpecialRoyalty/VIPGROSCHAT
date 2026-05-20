# Telegram VIP Teaser Bot

Bot Telegram avec :
- publication teaser texte + photo + boutons
- panel admin par boutons Telegram
- stats gratuit / premium
- anti double clic
- logs admin
- auto-pub toutes les 20 minutes ON/OFF
- vérification système
- broadcast ciblé premium / gratuit / tous
- PostgreSQL compatible Railway

## Installation Railway

1. Crée un bot avec @BotFather
2. Ajoute le bot dans ton groupe Telegram
3. Mets le bot admin du groupe
4. Sur Railway :
   - New Project
   - Deploy from GitHub ou upload ce dossier
   - Ajoute PostgreSQL
   - Ajoute les variables d'environnement

## Variables Railway

BOT_TOKEN=token du bot  
ADMIN_IDS=ton_id_telegram  
GROUP_ID=id du groupe Telegram  
DATABASE_URL=URL PostgreSQL Railway  
TEASER_PHOTO_URL=lien direct vers ton image  
PORT=3000

## Trouver ton Telegram ID

Écris à @userinfobot sur Telegram.

## Trouver le GROUP_ID

Ajoute temporairement le bot dans le groupe, envoie un message dans le groupe, puis regarde les logs Railway.  
Le bot affichera le chat id quand il reçoit un message.

## Commandes

/admin : ouvrir le panel admin  
/start : message user simple
