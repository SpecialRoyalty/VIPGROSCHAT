# Telegram Bot V2 Final

## Variables Railway obligatoires

```env
BOT_TOKEN=
BOT_USERNAME=
ADMIN_IDS=
DATABASE_URL=
```

## Variables optionnelles

```env
PUBLIC_BIO_TAG=@antijavana
MAIN_CHANNEL=@antijavana
INVITE_EXPIRE_MINUTES=10
PROOF_KICK_HOUR=21
PROOF_KICK_MINUTE=50
REWARD_HOUR=22
REWARD_MINUTE=5
REWARD_DELETE_AFTER_HOURS=2
REWARD_LOCK_EXTRA_MINUTES=5
ADMIN_REWARD_REMINDER_HOURS=12,18,21
REQUIRE_CHANNEL_JOIN=true
```

## Tables créées

- ajv2_config
- ajv2_users
- ajv2_promo_groups
- ajv2_branch_content
- ajv2_proofs
- ajv2_rewards

## Commandes admin

Dans le groupe principal :
```text
/setmain
```

Dans chaque groupe publicité :
```text
/addpromo
```

En privé :
```text
/start
```

## Flow utilisateur

1. Pub dans un groupe partenaire.
2. Bouton Commencer ouvre le bot en privé.
3. Question bio publique avec @antijavana.
4. Vérification canal @antijavana.
5. Choix plateforme.
6. Instructions + photo.
7. Capture d’écran.
8. Lien unique vers groupe principal, 1 usage, 10 minutes.
9. Preuve quotidienne avant 21h50.
10. Récompense publiée le soir et supprimée 2h après.

## Sécurités

- Accès groupe après preuve initiale.
- Lien unique 10 min / 1 usage.
- Rejoindre bloqué pendant période récompense.
- Récompense publiée seulement s’il y a des utilisateurs validés dans le groupe.
- Rappels admin si lien manquant.
- Suppression automatique de la récompense 2h après.
- 1er oubli preuve = kick.
- 2e oubli preuve = ban.


## Mise à jour publicité

Dans le panel admin :
- 🧲 Publicité
- Modifier texte pub
- Modifier photo pub
- Aperçu pub
- Publier publicité

Le bouton de pub est : `🔥 Je suis intéressé`.

## Vérification canal

Pour que `MAIN_CHANNEL=@antijavana` soit vérifié correctement, ajoute le bot comme admin du canal.
Sinon Telegram peut empêcher le bot de voir les membres.

Si tu veux désactiver la vérification canal temporairement :

```env
REQUIRE_CHANNEL_JOIN=false
```
