# StreamPartner — Audit Phase 1

> Phase 1 du plan de migration vers une architecture Backend REST + Frontends modernes.
> Date : 2026-07-07 (mis à jour le 2026-07-28)
> Statut : Toutes les phases terminées. 2FA authentification (TOTP + Email + WhatsApp) implémentée. Portage Flutter terminé.

---

## 1. Objectif de la migration

Transformer le monolithe Django actuel en **backend REST unique** (DRF, Djoser, JWT) consommé par plusieurs frontends :

- `web-user` (Next.js) — remplace la partie utilisateur (landing, auth, dashboard, paiement)
- `web-admin` (Next.js) — remplace le custom admin de l'app `dashboard`
- `mobile-admin` (Expo SDK 57 / React Native) — client mobile admin avec notifications push temps réel
- `mobile-admin` (Flutter) — portage planifié (voir `prompt.md` à la racine du workspace)

Pendant toute la migration :
- **100 % de la logique métier est conservée** (aucun comportement fonctionnel modifié) ;
- les templates Django et les vues HTML existantes sont **conservés** jusqu'à remplacement complet par les frontends ;
- la compatibilité du projet actuel n'est jamais cassée.

---

## 2. État actuel du projet

Après le nettoyage préalable (retrait de Twilio/Lygos/PawaPay, code mort, dépendances inutilisées, correction du bug `SECRET_KEY`/`DJANGO_KEY`), `manage.py check` passe sans erreur.

Le projet est maintenant organisé en **4 repos Git séparés** (voir `docs/development.md §0`) :

```
streampartner/                  (workspace local — clone des 4 repos)
├── backend/                    API Django REST + Celery + push notifications
├── web-user/                   Frontend utilisateur Next.js
├── web-admin/                  Frontend admin Next.js
├── mobile-admin/               App mobile admin (Expo SDK 57 / React Native)
├── docs/                       Documentation projet
├── prompt.md                   Prompt de portage Flutter (1008 lignes)
└── stream-v2.1/                Monolithe Django original (référence, non utilisé)
```

---

## 3. Stack technique actuelle (backend)

| Couche | Technologies |
|---|---|
| Framework | Django 6.0, Python 3.12/3.13 |
| Tâches asynchrones | Celery + Celery Beat (broker Redis) |
| DB | SQLite (local), PostgreSQL (prod Railway) |
| Stockage média | AWS S3 (`django-storages`) |
| Fichiers statiques | WhiteNoise |
| Email | Anymail + Resend |
| PDF | WeasyPrint + matplotlib (rapports analytiques) |
| SEO | django-meta, sitemaps, robots.txt |
| Gestionnaire de paquets | `uv` (Astral) |
| Déploiement | Docker (alpine), Railway |

Frontend actuel (à remplacer) : Tailwind v4 + DaisyUI, HTMX, Alpine.js, django-cotton, Phosphor Icons, GSAP / Motion One, AOS.

---

## 4. Architecture actuelle (8 apps Django)

```
config/        settings, celery, urls racines (API uniquement — HTML supprimé en Phase 8)
core/          Platform, PriceTier, Review, Faq
               services (SubscriptionAccessService, ReviewService)
               utils (calculate_price, calculate_expiration, get_all_prices)
users/         User custom (phone_number = identifiant, email optionnel)
               auth + password reset (via email ou admin)
               signals (admin login alert — async via Celery)
products/      Account, Profile, Card, AccountMarker, EncryptedCharField
               signals (access change notifications)
payments/      Order, Subscription, PaymentProof, GiftCode, PaymentNumber,
               SubscriptionProfileHistory, SubscriptionMarker
               services (PaymentCompletionService, ProfileAssignmentService)
               tasks (update_remaining_days, check_expiring_subscriptions, delete_stale_orders)
dashboard/     Notification, Message (modèles bulk messaging)
               tasks (rapports PDF hebdo/mensuel)
               report.py (WeasyPrint + matplotlib)
notifications/ App dédiée — découplage payments → dashboard
               models: PushToken, PushNotification
               services.py: 15 fonctions notify_* (email + push en parallèle)
               push_service.py: send_push_to_user, send_push_to_admins
               tasks.py: send_email_task, send_push_notification_task, send_push_to_admins_task,
                        check_expiring_cards_task, notify_admin_login_task
               templates: 15 templates d'emails HTML
api/           REST API (DRF) — serializers + views + URLs
               3 groupes: /v1/public/*, /v1/user/*, /v1/admin/*
```

### Couplages problématiques identifiés (à corriger en Phase 2)

- `payments/notifications.py` importe `dashboard.tasks.send_notification_task` → **couplage inverse** (payments dépend de dashboard).
- `dashboard/tasks.py` contient de l'envoi email générique + métier payments + rapports dashboard → **responsabilités mélangées**.
- Logique métier dans des `save()` de modèles (`Account`, `Profile`) et dans des vues (`ReviewView` bonus +7j, `HomeView` masquage des accès) → **manque de séparation**.

---

## 5. Cartographie des règles métier À CONSERVER

> Aucune de ces règles ne doit être modifiée pendant le refactoring ni la migration API.

### 5.1 Authentification & utilisateurs

- `User` custom, **`phone_number` = identifiant unique** (pas d'username), `country_code` séparé.
- **Email optionnel**, configuré post-inscription via `EmailSetupView`.
- Login = `phone_number` + mot de passe.
- Password reset : génération d'un token + envoi par **email** (si l'utilisateur en a un) ; sinon envoi du lien à l'**admin** (`REPORT_RECIPIENT_EMAIL`).
- Alerte admin par email à chaque **connexion admin** (avec IP + géolocalisation via ip-api.com).

### 5.2 Pricing (calcul automatique, jamais confiance au frontend)

Basé sur `PriceTier.base_price` (prix mensuel) :

```
1 mois  = base
3 mois  = 3 × base − 500
6 mois  = 2 × (3 mois) − 1000
1 an    = 2 × (6 mois) − 2000
```

- Plateformes avec **sous-catégories** (ex : Netflix Mobile / Essentiel / Premium), chacune son `base_price` + `category_description`.
- Types de compte : `mutual` (mutualisé) / `personal` (personnel).
- Prix **recalculé côté serveur** dans `calculate_price()` à chaque création de commande.

### 5.3 Commandes & paiements (Mobile Money manuel)

- `PurchaseInitView` : crée `Order` en `pending_payment`, prix recalculé serveur, `GiftCode` validé.
- `ManualPaymentView` : l'utilisateur upload 1 à 2 captures (`PaymentProof`) → Order `pending_validation`.
- Admin : `validate_proof` (activation + attribution profil) / `validate_proof_only` (sans activation) / `reject_proof` (notif rejet).
- Fallback numéros MTN/Orange via settings si aucun `PaymentNumber` actif en base.
- Annulation possible si Order non `completed` (supprime proofs + order, décrémente `total_orders`).

### 5.4 Activation abonnement (`PaymentCompletionService`)

- `process_completed_payment` : Order → `completed`, crée/étend `Subscription`, attribue `Profile`, notifie.
- `process_validate_payment` : valide sans activer (renouvellements / prolongements).
- `GiftCode` : re-vérifie la validité avant application, incrémente `used_count`, ajoute `days` au delta.
- `_create_subscription` :
  - si `renewal_from` → étend l'expiration existante (start = `order.purchase_date` = ancienne expiration),
  - sinon → crée une nouvelle `Subscription`.

### 5.5 Attribution profil (`ProfileAssignmentService.assign_profile`)

- Cherche un `Profile` du compte : bonne **plateforme** + bon **type** + `account.status='activate'`.
- Le compte doit avoir `available_places > 0` (`place − used_places`, où `used_places` = subscriptions actives liées).
- Le profil doit avoir **< 2 subscriptions actives**.
- Verrou transactionnel.

### 5.6 Renouvellement / prolongement

- `RenewalInitView` : nouvelle Order liée (`renewal_from=sub`), `purchase_date` = ancienne `expiration_date`.
- `motif` = `renewal` si sub expirée, `extension` sinon.
- Prolonge l'expiration (ne crée pas de nouvelle sub).
- `admin_renew_subscription` : renouvellement admin sans paiement (Order `completed` directement).

### 5.7 Masquage des accès par plateforme (`HomeView`) — SÉCURITÉ côté backend

- **Spotify / Apple Music** : seul le **profil principal** (premier créé, `Min(id)` du compte) voit email/password ; les autres profils voient des champs vides.
- **Surfshark** : tout masqué (email, password, profile_num, profile_pin).
- **Onoff** : géré via le type.
- Subs **expirées ET déliées** : exclues de l'affichage.
- Subs expirées mais **toujours liées à un profil** : affichées (status `expired`).

### 5.8 Cycle de vie automatique (Celery Beat)

| Schedule | Tâche | Module | Rôle |
|---|---|---|---|
| 00:00 quotidien | `update_remaining_days` | `payments.tasks` | MAJ `remaining_day` des comptes |
| 00:15 quotidien | `delete_stale_pending_orders_task` | `payments.tasks` | Supprime les orders `pending_payment` > 24h |
| 00:30 quotidien | `check_expiring_cards_task` | `notifications.tasks` | Auto-expire les cartes (`status→inactif`) |
| 08:00 quotidien | `check_expiring_subscriptions_task` | `payments.tasks` | Notifs J-3 / J / expiration (email + push) |
| Lundi 08:00 | `send_report_email_task` | `dashboard.tasks` | Rapport PDF hebdomadaire |
| Fin de mois 23:30 | `send_report_email_end_of_month_task` | `dashboard.tasks` | Rapport PDF mensuel (si dernier jour du mois) |

Tâches push (event-driven, pas dans le beat schedule) :
- `send_push_notification_task` (`notifications.tasks`) — appelée par chaque `notify_*`
- `send_push_to_admins_task` (`notifications.tasks`) — appelée par les `notify_*` admin

### 5.9 Bonus avis

- Premier avis d'un user ayant une sub active → **+7 jours** sur un abonnement actif **aléatoire**.
- Si la sub choisie n'a plus de profil, re-attribution via `SubscriptionProfileHistory` (dernier profil délié).
- Un seul avis par user (`OneToOneField`).

### 5.10 Notifications email + push (asynchrones, Celery → Resend + Expo Push)

Les 15 événements `notify_*` envoient **email ET push en parallèle** :

Achat · validation · activation (avec accès) · renouvellement · prolongement · expiration J-3 / J / J+1 · déliaison profil · màj accès · rejet preuve · reset password · bulk messaging · alerte admin connexion · notif admin nouvel achat.

**Email** : `send_email_task` → Resend (Anymail)
**Push** : `send_push_notification_task` / `send_push_to_admins_task` → Expo Push API → `PushNotification.objects.create()` (historique avec `is_read`, `data` pour deep linking)

### 5.11 Comptes & profils (règles `save`)

- `Account` : `max_profile=1` si `personal` ; `end_date = start_date + month_count` (relativedelta) ; `remaining_day` auto ; si email/password modifiés → notif (email + push) de tous les users actifs liés.
- `Profile` : `add_profile` refuse si `>= max_profile` (`ValidationError`) ; si `code`/`number` modifiés → notif des users liés.
- `SubscriptionProfileHistory` : trace chaque déliaison (numéro, code, account, plateforme, dates).
- `SubscriptionMarker` : tags nom + couleur (M2M).

### 5.12 SEO & divers

- Sitemaps (static + landing), robots.txt, django-meta (OG / Twitter).
- Rapports PDF admin (WeasyPrint + charts matplotlib base64).

---

## 6. Volume à migrer

| Périmètre | Volume |
|---|---|
| Templates HTML à reproduire | 64 (core 21, dashboard 17, theme 16, users 7, payments 3) |
| Vues Django à traduire en endpoints | ~50 (dashboard ~30, core ~5, payments ~6, users ~6) |
| Modèles à sérialiser | ~15 |
| Tâches Celery à conserver | 10 |
| Templates d'email à conserver | 14 |
| **Tests existants** | **Quasi nuls** (seul `payments/tests.py` a 64 lignes sur `PaymentNumber`) → à construire |

---

## 7. Dette technique ciblée par le refactoring (Phase 2)

| # | Problème | Localisation | Action prévue |
|---|---|---|---|
| 1 | Vue monolithique 1380 lignes | `dashboard/views.py` | Découper en ViewSets / services |
| 2 | `HomeView` 378 lignes, logique de masquage intégrée | `core/views.py` | Extraire `SubscriptionAccessService` |
| 3 | Couplage inverse payments → dashboard | `payments/notifications.py` | Créer une app `notifications` |
| 4 | Tâches Celery éparpillées | `dashboard/tasks.py` | `notifications/tasks.py` (générique) + `payments/tasks.py` (métier) + `dashboard/tasks.py` (rapports/bulk) |
| 5 | Logique dans `save()` (notif, compteurs) | `products/models.py` | Extraire vers signals / services |
| 6 | Bonus +7j dans la vue | `core/views.py:ReviewView` | Extraire vers service |
| 7 | Fautes de frappe `chanel` / `quewed` | `dashboard/models.py` | Renommer + migration `RenameField` |
| 8 | Appel HTTP synchrone au login | `users/signals.py` (ip-api) | Déporter en tâche Celery |
| 9 | Pas de couche service | (sauf `payments`) | Généraliser `services/` par app |
| 10 | Formulaires Django | `users/forms`, `dashboard/forms` | Remplacés par serializers DRF (Phase 3+) |

---

## 8. Risques & points d'attention pour la migration API

1. **Auth par téléphone** : Djoser est conçu pour l'email par défaut → serializers custom requis (`LOGIN_FIELD='phone_number'`, user serializer custom). L'email reste optionnel. **Décision : on garde `phone_number` comme identifiant principal.**
2. **JWT vs sessions** : passage à JWT (SimpleJWT), plus de CSRF côté API.
3. **Upload preuves** : multipart via API (DRF `MultiPartParser`).
4. **Masquage des accès** : doit rester **côté backend** dans les serializers (ne jamais exposer email/password si la plateforme le masque).
5. **Double routing** pendant la migration : URLs HTML existantes + URLs API (`/api/v1/...`), namespaces séparés, pas de collision.
6. **Templates conservés** : ne pas supprimer pendant la migration.
7. **Construire les tests** : base quasi nulle → créer une suite de tests à chaque étape pour verrouiller le métier avant refactor.
8. **Monorepo / git history** : déplacement `v3/` → `backend/` effectué (historique préservé via rename detection).

---

## 9. Découpage prévisionnel des endpoints (par groupe)

### `/api/v1/public/*` — sans authentification

- `auth/users/` (register), `auth/jwt/create|refresh|verify`, `auth/password/reset`
- `platforms/`, `platforms/{id}/pricing`, `reviews/`, `faqs/`
- `pages/{cgu|cgv|ml|pc}` (contenu légal)

### `/api/v1/user/*` — JWT, ressources propres uniquement

- `profile/` (me, update email), `profile/email-setup`
- `dashboard/` (subscriptions masqués, orders, pending_orders, notifications d'expiration)
- `orders/` (create = purchase_init, cancel), `orders/{id}/renewal`
- `payments/manual/{order_id}` (upload proof), `gift-code/verify`
- `reviews/` (submit, bonus géré côté backend)
- `subscriptions/{id}/` (read)
- `device/register/` (enregistrer push token), `device/unregister/` (supprimer push token)
- `notifications/` (liste push notifications, filtre is_read/type, pagination)
- `notifications/{id}/mark_read/` (marquer comme lu), `notifications/mark_all_read/` (tout lire)
- `notifications/unread_count/` (nombre non lues)

### `/api/v1/admin/*` — JWT + `is_superuser`

- `dashboard/stats`, `dashboard/charts`
- `users/` (CRUD + import/export CSV), `orders/`, `proofs/` (validate / reject / validate-only), `subscriptions/` (CRUD + change-profile + unlink + renew + markers + history + toggle/mark-expired)
- `accounts/` (CRUD + renew + mark/unmark markers), `profiles/` (CRUD), `platforms/` (CRUD + price-tiers), `faqs/`, `reviews/`, `giftcodes/` (toggle), `payment-numbers/` (toggle)
- `cards/` (CRUD + search), `account-markers/` (CRUD)
- `messaging/notifications`, `messaging/messages` (CRUD + send)
- `reports/weekly`, `reports/monthly` (PDF)
- `download-image` (utilitaire)

---

## 10. Plan d'exécution du refactoring (Phase 2)

Ordre validé — **toutes les étapes sont terminées** :

1. ✅ **Réorganisation monorepo** (`v3/` → `backend/`) + init structure `web-user/`, `web-admin/`
2. ✅ **Renommage** `chanel`→`channel` et `quewed`→`queued` + migration `RenameField`
3. ✅ **Création app `notifications`** (découplage) : `tasks.py` (générique) + `services.py` (fonctions `notify_*`)
4. ✅ **Recréer `payments/tasks.py`** (métier) + nettoyer `dashboard/tasks.py` (rapports/bulk) + `users` (signals/tasks)
5. ✅ **Extraction services** : `SubscriptionAccessService` (masquage), `ReviewService` (bonus), logique des `save()` → signals
6. ✅ **Découpage `dashboard/views.py`** (1382 lignes) → package `dashboard/views/` (12 modules par ressource)
7. ✅ **Base de tests** (pytest-django) : 16 tests verrouillent pricing, masquage accès, bonus avis
8. ✅ **Appel HTTP ip-api déporté en tâche Celery** (`notify_admin_login_task`) — le login n'est plus ralenti

---

## 11. Décisions prises (validées)

| Question | Décision |
|---|---|
| Q1 — Monorepo & git | **A** : nouveau repo git à la racine `streampartner/`, `v3/` intégrée dans `backend/` (historique préservé) |
| Q2 — Authentification | On garde **`phone_number`** comme identifiant principal (pas de migration vers email). Djoser configuré avec un serializer custom. Email reste optionnel. |
| Q3 — Tests | **pytest-django** (framework de tests) |
| Q4 — Documentation | Audit matérialisé dans `streampartner/docs/audit.md` (ce fichier) |
| Q5 — Ordre Phase 2 | Ordre validé (cf. §10) |

---

## 12. Phases de travail

```
Phase 1  — Audit                ✅
Phase 2  — Refactoring          ✅ (8/8 étapes)
Phase 3  — API publique         ✅ (9 endpoints)
Phase 4  — API utilisateur      ✅ (18 endpoints, 36 tests)
Phase 5  — API admin            ✅ (~40 endpoints, 58 tests)
Phase 6  — Web User (Next.js)   ✅ (14 routes, build passes)
Phase 7  — Web Admin (Next.js)  ✅ (14 routes, build passes)
Phase 8  — Nettoyage            ✅ (HTML frontend supprimé)
Phase 9  — Mobile Admin (Expo)  ✅ (SDK 57, 16 routes, push notifications)
Phase 10 — Push Notifications   ✅ (PushToken, PushNotification, 15 events, 6 endpoints, 10 tests)
Phase 11 — Flutter Port         ✅ (14 étapes, 24 tests, 0 errors)
Phase 12 — 2FA Authentication   ✅ (TOTP + Email OTP + WhatsApp OTP, 22 tests)
```

**Total tests backend : 126** (pytest-django, dont 22 tests 2FA).

Aucune phase ne commence sans validation explicite de la précédente.

---

## 13. Bilan des phases 3-7

### Phase 3 — API publique (`/api/v1/public/*`)

9 endpoints sans authentification :
- `auth/users/` (Djoser register), `auth/jwt/create|refresh|verify` (SimpleJWT)
- `auth/password/reset` (reset par email ou fallback admin)
- `platforms/`, `platforms/{id}/pricing` (catalogue read-only)
- `reviews/` (avis publics read-only)
- `faqs/` (FAQ read-only)

13 tests pytest-django.

### Phase 4 — API utilisateur (`/api/v1/user/*`)

18 endpoints JWT (ressources propres uniquement) :
- `profile/` (me, update email), `profile/email-setup`
- `dashboard/` (subscriptions masquées, orders, pending_orders, notifications d'expiration)
- `orders/` (create = purchase_init, cancel), `orders/{id}/renewal`
- `payments/manual/{order_id}` (upload proof multipart)
- `gift-code/verify`
- `reviews/` (submit + bonus géré côté backend)
- `subscriptions/{id}/` (read)
- `device/register/` + `device/unregister/` (push tokens)
- `notifications/` + `notifications/{id}/mark_read/` + `notifications/mark_all_read/` + `notifications/unread_count/`

36 tests pytest-django (26 originaux + 10 push).

### Phase 5 — API admin (`/api/v1/admin/*`)

~30 endpoints JWT + `is_superuser` :
- `dashboard/` (stats + chart data + download-image)
- `users/` (CRUD + CSV import/export + filtres q/status/email/country)
- `orders/` (CRUD + filtres)
- `proofs/` (CRUD + validate/validate_only/reject)
- `subscriptions/` (CRUD + change_profile/unlink_profile/renew/mark/unmark/profile_history/mark_expired/toggle_expiry)
- `accounts/` (CRUD + renew + mark/unmark markers)
- `profiles/` (CRUD)
- `platforms/` (CRUD), `price-tiers/` (CRUD)
- `faqs/` (CRUD), `reviews/` (list)
- `giftcodes/` (CRUD + toggle), `payment-numbers/` (CRUD + toggle)
- `messaging/notifications/` (CRUD + send), `messaging/messages/` (CRUD + send)
- `cards/` (CRUD + search), `account-markers/` (CRUD)

58 tests pytest-django (cumulé admin).

### Phase 6 — Web User (Next.js)

14 routes, build passes :
- Landing (`/`), Login (`/login`), Register (`/register`), Password reset (`/password-reset`)
- Dashboard (`/dashboard`), Payment (`/payment/[orderId]`)
- Legal : CGU (`/cgu`), CGV (`/cgv`), ML (`/ml`), PC (`/pc`)
- Composants : PhoneInput custom (241 pays, drapeaux emoji), Navbar glass, Loader GSAP, ReviewCard
- Stack : Next.js + TypeScript + Tailwind v4 + DaisyUI + Zustand + TanStack Query

### Phase 7 — Web Admin (Next.js)

14 routes, build passes :
- Login (`/login`), Dashboard (`/`), Users, Orders, Proofs, Subscriptions, Inventory, Content, Reviews, Giftcodes, Payment Numbers, Cards, Messaging
- Composants : AdminLayout (sidebar collapsible localStorage), SearchableSelect (dropdown custom avec recherche auto si >=10 options), toggles CSS, modals glass-panel
- Stack : Next.js + TypeScript + Tailwind v4 + DaisyUI + Zustand + TanStack Query + ApexCharts + Phosphor Icons

### Phase 9 — Mobile Admin (Expo SDK 57)

16 routes, build passes (EAS Build Android) :
- Login, Dashboard, Analytics, Management (hub), Edit (hub)
- Users, Orders, Proofs, Subscriptions, Inventory, Cards, Giftcodes, Payment Numbers, Messaging, Content, Reviews
- Notifications (centre de notifications push), Settings
- Composants : BottomSheet (Modal-based), ActionSheet, FilterSheet, SearchBar (debounce), ToggleSwitch (Reanimated), SkeletonCard, Pagination, FilterPill, HubScreen, ConfirmDialog, StatusBadge
- Stack : Expo SDK 57 + React Native 0.86 + React 19.2 + TypeScript + expo-router + Zustand + TanStack Query + expo-notifications + expo-secure-store + Ionicons
- EAS Build : 3 profiles (development, preview, production), projectId `bca6c750`
- Design : Dark theme, cards (pas de tables), action sheets, bottom sheets, safe area, skeleton loading, error states, pull-to-refresh, haptics
- Gestionnaire de paquets : `bun`

### Phase 10 — Push Notifications Temps Réel

- Modèles : `PushToken` (multi-appareils), `PushNotification` (historique avec is_read, data JSON pour deep linking)
- Service : `push_service.py` — `send_push_to_user`, `send_push_to_admins`
- Tâches Celery : `send_push_notification_task`, `send_push_to_admins_task`
- 15 événements `notify_*` envoient push en parallèle des emails
- 6 endpoints API `/user/` : device register/unregister, notifications list, mark_read, mark_all_read, unread_count
- Deep linking : payload `{screen, type, resource_id}`
- Mobile : expo-notifications, auto-register au login, centre de notifications, badge non lues
- 10 tests backend
- Provider actuel : Expo Push. FCM planifié pour Flutter.

### Phase 12 — 2FA Authentication (TOTP + Email + WhatsApp)

- **User model** : `twofa_enabled`, `twofa_method` (totp/email/whatsapp), `twofa_secret`, `twofa_recovery_codes` (JSON, hashed SHA-256)
- **TwoFACode model** : OTP temporaires (code, method, expires_at 5min, verified) avec indexes
- **TwoFAService** (`users/twofa_service.py`) :
  - TOTP : génération secret (`pyotp`), QR code base64 (`qrcode`), vérification avec `valid_window=1`
  - OTP email/whatsapp : code 6 chiffres, envoi via Resend (email) ou Whatomate (WhatsApp)
  - Recovery codes : 10 codes hex 16 chars, hashés SHA-256, single-use
  - 2FA token : UUID cached 5min (échange contre JWT après vérification)
- **Login flow modifié** :
  - `POST /auth/jwt/create/` → si 2FA activé, retourne `{2fa_required: true, twofa_token, method}` au lieu du JWT
  - `POST /auth/jwt/2fa-verify/` → échange `twofa_token + code` contre `{access, refresh}`
  - Support recovery codes (16 chars) en fallback
- **Admin endpoints** (`/api/v1/admin/2fa/`) :
  - `GET status/` — état 2FA (enabled, method, has_recovery_codes)
  - `POST setup/` — initie la configuration (QR code TOTP ou envoi OTP email/whatsapp)
  - `POST verify-setup/` — valide le code et active 2FA + génère recovery codes
  - `POST disable/` — désactive 2FA (confirmation par mot de passe)
  - `POST regenerate-recovery/` — régénère 10 nouveaux recovery codes
- **Frontend web-admin** :
  - Login 2-step : credentials → code 2FA (adapté selon méthode)
  - Page Paramètres (`/settings`) : activation/désactivation, choix méthode, QR code, recovery codes
  - Hooks : `use2FAStatus`, `use2FASetup`, `use2FAVerifySetup`, `use2FADisable`, `use2FARegenerateRecovery`
- **Env vars** : `WHATOMATE_API_KEY`, `WHATOMATE_BASE_URL`, `WHATOMATE_TEMPLATE_NAME`
- **22 tests** backend (login flow, OTP/recovery/wrong/expired verification, admin CRUD)

---

## 14. Nouvelles fonctionnalités

### 14.1 Cartes de Paiement (Card)

- Modèle `Card` avec `EncryptedCharField` (chiffrement Fernet) pour le numéro de carte
- Propriétés : `formatted_numero` (groupes de 4), `masked_numero` (last 4 only)
- Champs : `numero` (chiffré), `nom`, `cvv`, `telephone`, `expiration_date`, `status` (actif/inactif)
- `Account.card` : ForeignKey vers `Card` (SET_NULL)
- API CRUD complète : `/api/v1/admin/cards/` + search
- Frontend : page dédiée avec toggle reveal/mask, toggle status, modal création/édition
- Tâche Celery : `check_expiring_cards_task` (quotidienne 00:30) — auto-expire les cartes

### 14.2 Marqueurs de Comptes (AccountMarker)

- Modèle `AccountMarker` (name, color)
- `Account.markers` : ManyToManyField
- API : `/admin/accounts/<id>/mark/` + `/unmark/` + `/admin/account-markers/` CRUD
- Frontend inventory : badges colorés sous le nom de plateforme, bouton "Marquer", modal avec chip + color picker
- Dépendance : `cryptography>=49.0.0` (Fernet)

### 14.3 Notifications Push (PushToken + PushNotification)

- Modèle `PushToken` : stockage multi-appareils (user FK, token unique, platform ios/android, is_active)
- Modèle `PushNotification` : historique (user FK, title, body, data JSON, notification_type, is_read, read_at)
- `push_service.py` : `send_push_to_user`, `send_push_to_admins` (Expo Push API + stockage historique)
- 15 événements `notify_*` envoient push en parallèle des emails
- Deep linking : `data = {screen, type, resource_id}` → le client navigue vers l'écran concerné
- 6 endpoints `/user/` : register/unregister token, list/mark_read/mark_all_read/unread_count
- Provider actuel : Expo Push. FCM planifié pour Flutter (champ `provider` + `firebase-admin`)

### 14.4 Authentification 2FA (Two-Factor Authentication)

- **3 méthodes** : TOTP (Google Authenticator/Authy), Email OTP (Resend), WhatsApp OTP (Whatomate)
- **Login flow** : `jwt/create` gate → si 2FA activé, retourne `twofa_token` au lieu du JWT → `jwt/2fa-verify` échange token+code contre JWT
- **Recovery codes** : 10 codes de récupération hashés SHA-256, single-use, régénérables
- **Admin management** : 5 endpoints `/admin/2fa/` (status, setup, verify-setup, disable, regenerate-recovery)
- **Frontend** : login 2-step + page Paramètres avec QR code et gestion recovery codes
- **Dépendances** : `pyotp` (TOTP), `qrcode` (QR code base64), `cryptography` (déjà pour Card.numero)

---

## 15. Corrections appliquées

### Série 1 (8 corrections) — `b2aa500` + `feb6c43`

1. Chart plateformes populaires : vraies données (platform_labels + platform_data)
2. Section utilisateurs : filtre pays dropdown custom + 241 pays dans modal
3. Tous les selects natifs modals → SearchableSelect custom (recherche si >=10)
4. Abonnements : tri par date d'achat descendant
5. Inventory : pagination + noms utilisateurs profils occupés (vert si marker)
6. Avis : suppression action de suppression (raison d'éthique)
7. Sidebar : fix lien "Numéros de Paiement" non actif
8. Messagerie : modal d'envoi avec sélection d'utilisateurs individuels

### Série 2 (4 corrections) — `85f219e`

1. Chart : retiré filtre `status='completed'` + limite `[:5]` (total 12 au lieu de 9)
2. Status comptes : toggle switch CSS au lieu de badge statique
3. Status cartes : toggle switch CSS + cartes inactives masquées du modal compte
4. Modal messagerie : ajout champ canal, users avec email seulement, UI conforme au template Django

### Série 3 (1 correction) — `fe9f90d`

1. Modal messagerie : `sendToAll=false` par défaut (liste utilisateurs visible à l'ouverture)

---

## 16. Architecture finale

### 16.1 Workspace (4 repos Git séparés)

```
streampartner/                  Workspace local (clone des 4 repos)
├── backend/                    API Django REST + Celery + push notifications
│   ├── config/                 Settings, Celery, URLs racines
│   ├── core/                   Platform, PriceTier, Review, Faq + services
│   ├── users/                  User custom (phone_number = identifiant)
│   ├── products/               Account, Profile, Card, AccountMarker + signals
│   ├── payments/               Order, Subscription, PaymentProof, GiftCode, etc. + services
│   ├── dashboard/              Notification, Message + tasks (rapports PDF)
│   ├── notifications/          PushToken, PushNotification, push_service, 15 notify_* + email templates
│   ├── api/                    REST API (serializers + views + URLs — 3 groupes)
│   ├── tests/                  pytest-django (126 tests)
│   └── manage.py
├── web-user/                   Frontend utilisateur (Next.js, 14 routes)
├── web-admin/                  Frontend admin (Next.js, 14 routes)
├── mobile-admin/               App mobile admin (Expo SDK 57, 16 routes, EAS Build)
├── docs/                       Documentation
│   ├── audit.md                Audit + suivi des phases
│   ├── api.md                  Documentation API complète
│   ├── architecture.md         Architecture
│   └── development.md          Guide de développement
├── prompt.md                   Prompt de portage Flutter (1008 lignes)
└── stream-v2.1/                Monolithe Django original (référence)
```

### 16.2 Stack technique finale

| Couche | Technologies |
|---|---|
| Backend | Django 6.0, Python 3.12, DRF, SimpleJWT, Djoser |
| Tâches | Celery + Celery Beat (Redis ou LocMem fallback) |
| DB | SQLite (dev), PostgreSQL (prod) |
| Stockage | AWS S3 (django-storages) |
| Email | Anymail + Resend |
| Push | Expo Push Notifications (15 events, FCM planifié pour Flutter) |
| PDF | WeasyPrint + matplotlib |
| Chiffrement | cryptography (Fernet) pour Card.numero |
| 2FA | pyotp (TOTP) + qrcode (QR code) + Whatomate (WhatsApp OTP) |
| Web frontends | Next.js 16, TypeScript, Tailwind v4, DaisyUI, Zustand, TanStack Query |
| Mobile admin | Expo SDK 57, React Native 0.86, React 19.2, TypeScript, expo-router, Zustand, TanStack Query, expo-notifications |
| Icons | Phosphor Icons (web), Ionicons (mobile) |
| Charts | ApexCharts (web), View-based donut + bar charts (mobile) |
| Mobile build | EAS Build (3 profiles: development, preview, production) |
| Tests | pytest-django (126 tests backend) |

### 16.3 Règles métier — additions

#### Cards (§5.13)

- `Card.numero` chiffré au repos via Fernet (clé dérivée de `FERNET_KEY` ou `SECRET_KEY`)
- `formatted_numero` : numéro groupé par 4 (ex: `1234 5678 9012 3456`)
- `masked_numero` : masque tout sauf les 4 derniers (ex: `**** **** **** 3456`)
- Auto-expiration : `check_expiring_cards_task` (00:30 quotidien) → `status='inactif'` si `expiration_date + 1 mois <= today`
- Cartes inactives masquées du SearchableSelect dans le modal de création de compte

#### Account Markers (§5.14)

- `AccountMarker` : tags nommés + colorés (get-or-create par name+color)
- `Account.markers` : M2M, un compte peut avoir plusieurs marqueurs
- Marqueurs affichés sous le nom de plateforme dans la table inventory (avec bouton X pour retirer)

#### Push Notifications (§5.15)

- `PushToken` : un token par appareil, multi-appareils par utilisateur (user FK, token unique, platform, is_active)
- `PushNotification` : historique par utilisateur (title, body, data JSON, notification_type, is_read, read_at)
- Enregistrement : au login, le client enregistre son token via `POST /user/device/register/`
- Désenregistrement : au logout, le client désactive son token via `POST /user/device/unregister/`
- Envoi : les 15 fonctions `notify_*` appelent `_push_user` ou `_push_admins` en parallèle de l'email
- Admins : `send_push_to_admins` cible `is_staff=True OR is_superuser=True`
- Deep linking : `data = {screen, type, resource_id}` → le client navigue vers `/{screen}`
- Types : `order`, `subscription`, `payment`, `user`, `system`
- Synchronisation : une notification marquée comme lue sur un appareil est lue sur tous (stockage centralisé côté backend)
- Provider actuel : Expo Push Notifications. FCM planifié (champ `provider` + `firebase-admin`)

#### Celery Beat — schedule complet (§5.8 mis à jour)

| Schedule | Tâche | Rôle |
|---|---|---|
| 00:00 quotidien | `update_remaining_days` | MAJ `remaining_day` des comptes |
| 00:15 quotidien | `delete_stale_pending_orders_task` | Supprime orders `pending_payment` > 24h |
| 00:30 quotidien | `check_expiring_cards_task` | Auto-expire les cartes |
| 08:00 quotidien | `check_expiring_subscriptions_task` | Notifs J-3 / J / expiration |
| Lundi 08:00 | `send_report_email_task` | Rapport PDF hebdomadaire |
| Fin de mois 23:30 | `send_report_email_end_of_month_task` | Rapport PDF mensuel |
