# Telegram Bot Production V4 corrigé

## Variables Railway obligatoires

```env
BOT_TOKEN=ton_token_botfather
ADMIN_IDS=ton_id_telegram
BOT_USERNAME=GrosChatVIP_bot
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

## Variables optionnelles

```env
PUBLIC_BIO_TAG=@antijavana
REQUIRE_BIO_TAG=true
KICK_AFTER_MINUTES=30
CONFIRM_AFTER_MINUTES=30
PROOF_KICK_HOUR=21
PROOF_KICK_MINUTE=50
REWARD_START_HOUR=22
REWARD_START_MINUTE=5
REWARD_DELETE_HOUR=0
REWARD_DELETE_MINUTE=45
LOCK_END_HOUR=1
ADMIN_REWARD_REMINDER_HOURS=12,18,21
MIN_USERNAME_REQUIRED=true
SUSPICIOUS_REQUIRES_ADMIN=true
```

## Tables utilisées

Toutes les tables commencent par `antijavana_bot_`.

## Commande SQL reset

```sql
DROP TABLE IF EXISTS antijavana_bot_join_requests CASCADE;
DROP TABLE IF EXISTS antijavana_bot_proofs CASCADE;
DROP TABLE IF EXISTS antijavana_bot_rewards CASCADE;
DROP TABLE IF EXISTS antijavana_bot_branch_content CASCADE;
DROP TABLE IF EXISTS antijavana_bot_users CASCADE;
DROP TABLE IF EXISTS antijavana_bot_groups CASCADE;
DROP TABLE IF EXISTS antijavana_bot_config CASCADE;
```

## Notes

Le bot doit être admin du groupe principal avec permission :
- approuver les demandes
- bannir les membres
- inviter via lien
- épingler les messages
- supprimer les messages


## Correctifs fixed3

- Corrige `There is no text in the message to edit` quand le bouton est sur une photo.
- Depuis un groupe, le bouton “Demander l’accès” renvoie d’abord vers le bot en privé.
- Ajoute `BOT_USERNAME`, par exemple `GrosChatVIP_bot`.
- Ajoute un délai de confirmation `CONFIRM_AFTER_MINUTES`.
- Si l’utilisateur choisit TikTok/Reddit/etc puis ne clique ni OUI ni NON, il est retiré après ce délai.


## Correctif fixed4 — message d'instruction

- Le message d'instruction n'est plus épinglé.
- Le bot n'envoie plus ce message en boucle.
- Quand quelqu'un entre dans le groupe principal :
  1. il supprime le précédent message d'instruction
  2. il envoie un nouveau message propre
- Les jobs automatiques ne recréent plus ce message.
