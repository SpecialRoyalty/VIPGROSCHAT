# Telegram Bot Production V4 corrigé

## Variables Railway obligatoires

```env
BOT_TOKEN=ton_token_botfather
ADMIN_IDS=ton_id_telegram
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

## Variables optionnelles

```env
PUBLIC_BIO_TAG=@antijavana
REQUIRE_BIO_TAG=true
KICK_AFTER_MINUTES=30
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
