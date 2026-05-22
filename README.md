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


## V3 — demandes d’adhésion et bio

- Les liens créés par le bot utilisent maintenant `creates_join_request=True`.
- Entre 22h et 01h, les demandes d’adhésion sont refusées automatiquement, sans kick/ban définitif.
- À partir de 01h, les demandes peuvent être acceptées à nouveau.
- Le bot vérifie `PUBLIC_BIO_TAG` dans la bio publique quand Telegram rend la bio accessible au bot.
- Si la bio est inaccessible ou ne contient pas le tag, la demande est refusée proprement avec un message privé.
- Une nouvelle table est créée :
  - `antijavana_bot_join_requests`

Variables optionnelles supplémentaires :

```env
REQUIRE_BIO_TAG=true
PUBLIC_BIO_TAG=@antijavana
```

Important : pour que les demandes d’adhésion fonctionnent, le groupe principal doit autoriser les demandes d’adhésion via les liens d’invitation créés par le bot. Le bot crée déjà ces liens en mode demande.

## V4 — améliorations opérationnelles

- Kick des utilisateurs sans preuve avancé à 21h50.
- Vérification quotidienne de la bio avant récompense : si le tag requis est retiré, kick temporaire.
- Message d’instruction épinglé permanent, édité au lieu d’être supprimé/recréé.
- Jobs rattrapables après redémarrage Railway : contrôle preuves/bio, publication récompense, suppression récompense.
- Rappels admin multiples si aucun lien récompense n’est prêt.
- Récompense publiée vers 22h05 puis supprimée automatiquement à 00h45.
- Réduction des bans immédiats : non-clic/refus = kick temporaire la première fois, ban à la deuxième récidive.
- Anti multi-comptes limité par ce que Telegram expose : option pour mettre les comptes sans username en revue/refus.

Variables optionnelles :

```env
PROOF_KICK_HOUR=21
PROOF_KICK_MINUTE=50
REWARD_DELETE_HOUR=0
REWARD_DELETE_MINUTE=45
ADMIN_REWARD_REMINDER_HOURS=12,18,21
MIN_USERNAME_REQUIRED=true
SUSPICIOUS_REQUIRES_ADMIN=true
```

Note : Telegram Bot API ne donne pas l’âge réel d’un compte, donc on ne peut pas vérifier l’âge du compte automatiquement.
