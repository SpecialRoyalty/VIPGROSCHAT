
# Telegram Railway Promo Bot

Bot Telegram en Python avec :
- panel admin 100% boutons
- détection automatique des groupes où le bot est ajouté
- configuration pub/photo/instructions/lien récompense depuis Telegram
- groupe central configurable depuis le panel
- choix TikTok / Leakmedia / Reddit / Discord avec répartition équilibrée
- confirmation OUI/NON
- kick après 3h si l'utilisateur ne confirme pas
- demande/preuve quotidienne avant 22h
- publication de la récompense dans le groupe central

## Variables Railway obligatoires

- `BOT_TOKEN` : token donné par @BotFather
- `ADMIN_IDS` : ton id Telegram numérique, ex: `123456789`
- `TZ` : optionnel, par défaut `Europe/Paris`
- `REQUIRED_BIO` : optionnel, par défaut `@antijavana`

Tu n’as pas besoin de mettre les chat_id des groupes en variable. Le bot les détecte automatiquement quand il est ajouté dans les groupes ou quand un message y est envoyé.

## Installation Railway

1. Mets ces fichiers dans un repo GitHub.
2. Sur Railway : New Project -> Deploy from GitHub.
3. Ajoute les variables `BOT_TOKEN` et `ADMIN_IDS`.
4. Déploie.
5. Ajoute le bot dans tes groupes avec les droits admin :
   - supprimer/bannir des membres
   - envoyer messages
   - lire messages de service
6. Lance `/start` en privé avec le bot.
7. Va dans `Groupes`, choisis le groupe central.
8. Configure les textes/photos/liens depuis le panel.

## Important

Telegram ne donne pas toujours la bio publique d’un utilisateur via la Bot API. Le code essaie de vérifier `REQUIRED_BIO`, mais si Telegram ne retourne pas la bio, l’utilisateur passe en `bio_unknown`. Si tu veux un contrôle strict à 100%, il faut ajouter une validation admin manuelle ou demander une preuve.
