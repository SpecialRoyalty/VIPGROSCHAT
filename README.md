# Telegram Railway Bot — Production PostgreSQL

## Variables Railway obligatoires

```env
BOT_TOKEN=ton_token_botfather
ADMIN_IDS=123456789
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

## Variables optionnelles

```env
PUBLIC_BIO_TAG=@antijavana
PROOF_DEADLINE_HOUR=22
REWARD_START_HOUR=22
REWARD_END_HOUR=1
KICK_AFTER_HOURS=3
```

## Installation Railway

1. Crée un projet Railway.
2. Ajoute un service PostgreSQL Railway.
3. Ajoute ce code comme service bot.
4. Dans Variables du service bot, ajoute :
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `DATABASE_URL` en référence au PostgreSQL Railway : `${{Postgres.DATABASE_URL}}`
5. Déploie.
6. Va sur Telegram, ouvre le bot, envoie `/start`.

## Permissions Telegram nécessaires

Dans les groupes, le bot doit être admin avec :
- bannir des membres
- inviter via lien
- gérer les messages, optionnel

## Important

La Bot API Telegram ne garantit pas l'accès à la bio publique de tous les utilisateurs.
Le bot prévoit donc un champ `PUBLIC_BIO_TAG` et une logique de validation côté workflow, mais Telegram peut limiter cette vérification automatiquement.
