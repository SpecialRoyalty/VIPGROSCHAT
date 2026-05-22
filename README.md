# Telegram Railway Bot Pro — PostgreSQL

Version plus propre avec tables isolées `antijavana_bot_*`, sans conflit avec une base PostgreSQL déjà utilisée :
- panel admin 100% boutons
- groupes détectés automatiquement
- choix clair du groupe principal
- activation/désactivation des groupes publicité
- publication pub dans tous les groupes promo actifs
- configuration des plateformes en 2 étapes : texte puis photo
- aperçu avant validation
- PostgreSQL Railway persistant
- kick automatique après délai
- preuves quotidiennes
- récompenses publiées par le bot

## Variables Railway obligatoires

```env
BOT_TOKEN=ton_token_botfather
ADMIN_IDS=123456789
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

## Variables optionnelles

```env
PUBLIC_BIO_TAG=@antijavana
KICK_AFTER_HOURS=3
PROOF_DEADLINE_HOUR=22
REWARD_START_HOUR=22
```

## Déploiement

1. Crée un projet Railway.
2. Ajoute PostgreSQL.
3. Ajoute ce service bot.
4. Mets les variables.
5. Déploie.
6. Va sur Telegram → `/start`.

## Permissions Telegram

Le bot doit être admin dans les groupes avec :
- bannir des membres
- inviter via lien
- envoyer messages
- gérer les messages si besoin

## Note importante

Telegram ne donne pas toujours accès à la bio publique d’un utilisateur via la Bot API.
La vérification `@antijavana` peut donc nécessiter une validation manuelle ou un système de preuve.


## Tables créées par cette version

Cette version utilise uniquement des tables avec le préfixe :

```text
antijavana_bot_
```

Tables utilisées :
- antijavana_bot_config
- antijavana_bot_groups
- antijavana_bot_users
- antijavana_bot_branch_content
- antijavana_bot_rewards
- antijavana_bot_proofs

Elle ne touche pas à tes anciennes tables comme :
- participants
- settings
- messages
- reward_links
- referrals
- etc.


## V2 — logique ajoutée

- Délai d'action après arrivée dans le groupe principal : 30 minutes par défaut.
- Le message d'instruction dans le groupe principal est unique : le bot supprime le précédent avant d'envoyer le nouveau.
- Si un utilisateur ne clique pas sur “Je suis intéressé” sous 30 minutes : kick + ban définitif.
- Si un utilisateur clique NON : kick + ban définitif.
- De 22h à 01h : aucun nouvel utilisateur ne peut rejoindre pour profiter de la récompense.
- À 22h : les utilisateurs sans preuve du jour sont kick.
- Première absence de preuve : retour autorisé une seule fois.
- Deuxième absence de preuve : ban définitif.
- Le bot rappelle chaque jour aux admins d’ajouter un lien récompense.
- Le lien récompense est publié automatiquement vers 22h05.
- À 01h : nouvelle session de preuves.
- Au démarrage du bot : message admin indiquant que la session est active.

## Variables optionnelles V2

```env
KICK_AFTER_MINUTES=30
PROOF_DEADLINE_HOUR=22
REWARD_START_HOUR=22
LOCK_END_HOUR=1
ADMIN_REWARD_REMINDER_HOUR=18
```
