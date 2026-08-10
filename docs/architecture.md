# StreamPartner — Architecture

> Document décrivant l'architecture, les apps Django, les modèles, les services et les flux principaux.

---

## 1. Structure du workspace (4 repos Git séparés)

```
streampartner/                  Workspace local (clone des 4 repos)
├── backend/                      Application Django (REST API + Celery)
│   ├── config/                   Settings, Celery config, URLs racines
│   │   ├── settings.py           Configuration principale (env-based)
│   │   ├── celery.py             Celery app + beat schedule (6 tâches)
│   │   └── urls.py               URLs racines (API + admin Django)
│   ├── core/                     Plateformes, pricing, reviews, FAQ
│   │   ├── models.py             Platform, PriceTier, Review, Faq
│   │   ├── services.py           SubscriptionAccessService, ReviewService
│   │   └── utils.py              calculate_price, calculate_expiration, platform_choices
│   ├── users/                    Utilisateurs (auth par phone_number)
│   │   ├── models.py             User custom (phone_number = LOGIN_FIELD)
│   │   ├── signals.py            notify_admin_login_task (async, IP + géoloc)
│   │   └── utils.py              get_location_info (ip-api)
│   ├── products/                 Comptes, profils, cartes, marqueurs
│   │   ├── models.py             Account, Profile, Card, AccountMarker, EncryptedCharField
│   │   └── signals.py            Access change notifications (email/password/code/number)
│   ├── payments/                 Commandes, abonnements, preuves, codes cadeaux
│   │   ├── models.py             Order, Subscription, PaymentProof, GiftCode,
│   │   │                         PaymentNumber, SubscriptionMarker, SubscriptionProfileHistory
│   │   ├── services.py           PaymentCompletionService, ProfileAssignmentService
│   │   └── tasks.py              update_remaining_days, check_expiring_subscriptions, delete_stale_orders
│   ├── dashboard/                Interface admin (modèles + tâches rapports)
│   │   ├── models.py             Notification, Message
│   │   ├── tasks.py              send_report_email_task, send_report_email_end_of_month_task
│   │   └── report.py             Génération PDF (WeasyPrint + matplotlib)
│   ├── notifications/            App dédiée (découplage payments → dashboard)
│   │   ├── models.py             PushToken, PushNotification
│   │   ├── services.py           15 notify_* functions (email + push en parallèle)
│   │   ├── push_service.py       send_push_to_user, send_push_to_admins (Expo Push API)
│   │   ├── tasks.py              send_email_task, send_push_notification_task,
│   │   │                         send_push_to_admins_task, send_access_update_notification,
│   │   │                         send_rejection_proof_email, send_password_reset_link_task,
│   │   │                         notify_admin_login_task, check_expiring_cards_task,
│   │   │                         send_bulk_notification_task, send_bulk_message_task
│   │   └── templates/            15 templates d'emails HTML
│   ├── api/                      REST API (DRF)
│   │   ├── urls.py               Router principal (/v1/public, /v1/user, /v1/admin)
│   │   ├── urls_public.py        Endpoints publics
│   │   ├── urls_user.py          Endpoints utilisateur
│   │   ├── urls_admin.py         Endpoints admin (16 viewsets)
│   │   ├── serializers/          Serializers DRF (auth, public, user, admin)
│   │   └── views/                Views DRF (public, user, admin)
│   ├── tests/                    pytest-django (104 tests)
│   │   ├── conftest.py           Fixtures + LocMemCache + CELERY_TASK_ALWAYS_EAGER
│   │   ├── test_api_public.py
│   │   ├── test_api_user.py
│   │   ├── test_api_admin.py
│   │   ├── test_pricing.py
│   │   ├── test_review_bonus.py
│   │   └── test_subscription_access.py
│   ├── pyproject.toml            Dépendances (uv)
│   └── manage.py
├── web-user/                     Frontend utilisateur (Next.js)
│   ├── app/                      14 routes (landing, login, register, dashboard, payment, legal)
│   ├── components/               Navbar, PhoneInput, Loader, ReviewCard, etc.
│   ├── lib/                      countries.ts, hooks.ts, api.ts, auth-store.ts
│   ├── app/globals.css           Tailwind v4 + @layer components + keyframes
│   └── package.json
├── web-admin/                    Frontend admin (Next.js)
│   ├── app/(admin)/              14 routes (dashboard, users, orders, proofs, subscriptions,
│   │                             inventory, content, reviews, giftcodes, payment-numbers,
│   │                             cards, messaging)
│   ├── components/               admin-layout, searchable-select, providers
│   ├── lib/                      hooks.ts, api.ts, auth-store.ts, countries.ts
│   └── package.json
├── mobile-admin/               App mobile admin (Expo SDK 57 / React Native)
│   ├── app/                    16 routes (login, dashboard, analytics, management, edit,
│   │                           users, orders, proofs, subscriptions, inventory, cards,
│   │                           giftcodes, payment-numbers, messaging, content, reviews,
│   │                           notifications, settings)
│   ├── src/core/               Network (Dio+JWT), theme, components (20+), notifications (push)
│   ├── src/data/               Models TS (20+), repositories (16)
│   ├── src/presentation/       Zustand auth store, TanStack Query hooks (40+)
│   ├── eas.json                EAS Build (3 profiles: development, preview, production)
│   ├── app.json                Expo config (projectId bca6c750)
│   └── package.json            bun (gestionnaire de paquets)
├── docs/                         Documentation
│   ├── audit.md                  Audit Phase 1 + suivi des phases
│   ├── api.md                    Documentation API complète
│   ├── architecture.md           Ce fichier
│   └── development.md            Guide de développement
├── prompt.md                     Prompt de portage Flutter (1008 lignes)
└── stream-v2.1/                  Monolithe Django original (référence)
```

---

## 2. Apps Django — responsabilités

| App | Responsabilités | Modèles |
|---|---|---|
| `config` | Settings, Celery, URLs racines | — |
| `core` | Catalogue (plateformes, pricing), reviews, FAQ, services d'accès | Platform, PriceTier, Review, Faq |
| `users` | Utilisateurs custom, auth par phone_number, signals login admin | User |
| `products` | Comptes sources, profils, cartes (chiffrées), marqueurs, signals access change | Account, Profile, Card, AccountMarker |
| `payments` | Commandes, abonnements, preuves de paiement, codes cadeaux, numéros de paiement, services | Order, Subscription, PaymentProof, GiftCode, PaymentNumber, SubscriptionMarker, SubscriptionProfileHistory |
| `dashboard` | Modèles Notification + Message, tâches de rapports PDF | Notification, Message |
| `notifications` | App dédiée — tâches Celery + services d'envoi d'emails + push notifications + templates d'emails | PushToken, PushNotification |
| `api` | REST API (DRF) — serializers, views, URLs pour 3 groupes d'endpoints | — |

---

## 3. Modèles — relations principales

```
User (phone_number = identifiant)
 ├── Order (commande)
 │    ├── platform, duration, type, price (recalculé serveur)
 │    ├── status (pending_payment → pending_validation → completed/failed)
 │    ├── motif (purchase, renewal, extension)
 │    └── renewal_from → Subscription (si renouvellement)
 │
 ├── Subscription (abonnement)
 │    ├── order → Order
 │    ├── profile → Profile (nullable, peut être délié)
 │    ├── status (active, expired)
 │    ├── expiration_date
 │    └── markers ↔ SubscriptionMarker (M2M)
 │
 └── Review (avis, OneToOne — 1 par user)
      └── stars, comment → bonus +7j si 1er avis avec sub active

Account (compte source)
 ├── platform, email, password, type (mutual/personal)
 ├── card → Card (FK, nullable)
 ├── markers ↔ AccountMarker (M2M)
 ├── place (max abonnements liés)
 ├── start_date, end_date, month_count, remaining_day
 └── status (activate, desactivate)

Profile (profil client)
 ├── account → Account (FK)
 ├── number, code (PIN)
 └── place (1 ou 2)

Card (carte de paiement)
 ├── numero (EncryptedCharField — Fernet)
 ├── nom, cvv, telephone, expiration_date
 └── status (actif, inactif)

SubscriptionMarker (marqueur d'abonnement)
 └── name, color

AccountMarker (marqueur de compte)
 └── name, color

PaymentProof (preuve de paiement)
 ├── order → Order
 ├── image, image2 (uploads S3)
 ├── validated, validated_by, validated_at
 └── rejected, rejection_reason

GiftCode (code cadeau)
 └── code, days, platform, usage_limit, used_count, status

PaymentNumber (numéro de paiement Mobile Money)
 └── provider, number, name, is_active

Notification (notification admin → users)
 └── title, message, type, channel, image, queued

Message (message admin → users)
 └── subject, message, type, channel, queued

SubscriptionProfileHistory (historique de déliaison profil)
  └── subscription, profile_number, profile_code, account_number, platform, linked_at, unlinked_at

PushToken (token push multi-appareils)
  ├── user → User (FK)
  ├── token (unique, Expo push token)
  ├── platform (ios/android)
  ├── is_active
  └── created_at, updated_at

PushNotification (historique des notifications push)
  ├── user → User (FK)
  ├── title, body
  ├── data (JSON: {screen, type, resource_id} pour deep linking)
  ├── notification_type (order/subscription/payment/user/system)
  ├── is_read, read_at
  └── created_at
```

---

## 4. Services

### PaymentCompletionService (`payments/services.py`)

Orchestre l'activation d'un abonnement après validation d'une preuve de paiement :

1. `process_completed_payment(order)` : Order → `completed`, crée/étend `Subscription`, attribue `Profile`, notifie
2. `process_validate_payment(order)` : valide sans activer (renouvellements/prolongements)
3. `_create_subscription(order)` :
   - Si `renewal_from` → étend l'expiration existante (start = `order.purchase_date` = ancienne expiration)
   - Sinon → crée une nouvelle `Subscription`

### ProfileAssignmentService (`payments/services.py`)

Attribue un profil à un abonnement :

1. Cherche un `Profile` du compte : bonne **plateforme** + bon **type** + `account.status='activate'`
2. Le compte doit avoir `available_places > 0`
3. Le profil doit avoir **< 2 subscriptions actives**
4. Verrou transactionnel

### SubscriptionAccessService (`core/services.py`)

Masquage des accès par plateforme (sécurité côté backend) :

- **Spotify / Apple Music** : seul le profil principal (`Min(id)`) voit email/password
- **Surfshark** : tout masqué
- **Onoff** : géré par type
- Subs expirées + déliées : exclues
- Subs expirées + liées : affichées (status `expired`)

### ReviewService (`core/services.py`)

Bonus avis : premier avis d'un user avec sub active → +7 jours sur un abonnement actif aléatoire. Si la sub choisie n'a plus de profil, re-attribution via `SubscriptionProfileHistory`.

### PushService (`notifications/push_service.py`)

Envoie des notifications push via l'API Expo Push et stocke l'historique :
- `send_push_to_user(user_id, title, body, data, notification_type)` : envoie à tous les appareils actifs d'un utilisateur + crée un `PushNotification`
- `send_push_to_admins(title, body, data, notification_type)` : envoie à tous les admins (`is_staff OR is_superuser`)
- `deactivate_token(token)` : désactive un token (au logout)
- `remove_token(token)` : supprime un token

Toutes les fonctions `notify_*` dans `services.py` appellent `_push_user` ou `_push_admins` en parallèle de l'email. Le payload `data` contient `{screen, type, resource_id}` pour le deep linking côté mobile.

---

## 5. Signals

### `products/signals.py`

- `capture_account_access` (pre_save) : capture les anciennes valeurs d'email/password
- `notify_account_access_change` (post_save) : si email/password modifiés → `send_access_update_notification` (Celery task)
- `capture_profile_access` (pre_save) : capture les anciennes valeurs de code/number
- `notify_profile_access_change` (post_save) : si code/number modifiés → notification

### `users/signals.py`

- `notify_admin_login_task` : au login admin, déporte l'appel HTTP à ip-api.com en tâche Celery (le login n'est pas ralenti)

---

## 6. Frontend web-user (Next.js)

### Stack

Next.js 16 + TypeScript + Tailwind v4 + DaisyUI + Zustand (auth store) + TanStack Query (data fetching)

### Routes (14)

| Route | Description |
|---|---|
| `/` | Landing page (hero, pricing, avis, FAQ) |
| `/login` | Connexion (phone_number + password) |
| `/register` | Inscription (PhoneInput custom 241 pays) |
| `/password-reset` | Reset mot de passe |
| `/dashboard` | Dashboard utilisateur (abonnements masqués, commandes) |
| `/payment/[orderId]` | Upload preuve de paiement (Mobile Money) |
| `/cgu` | Conditions générales d'utilisation |
| `/cgv` | Conditions générales de vente |
| `/ml` | Mentions légales |
| `/pc` | Politique de confidentialité |

### Composants clés

- `PhoneInput` : dropdown custom 241 pays (ISO 3166-1 + dial codes + drapeaux emoji), auto-détection IP
- `Navbar` : glass effect au scroll (style inline pour fix intermittent HMR), mobile menu avec click-outside
- `Loader` : import statique GSAP + Motion One, `onComplete` avec `opacity=1`
- `ReviewCard` : `h-full flex flex-col` + `line-clamp-4`

---

## 7. Frontend web-admin (Next.js)

### Stack

Next.js 16 + TypeScript + Tailwind v4 + DaisyUI + Zustand + TanStack Query + ApexCharts + Phosphor Icons (npm)

### Routes (14)

| Route | Description |
|---|---|
| `/login` | Connexion admin |
| `/` | Vue d'ensemble (KPIs, charts, dernières commandes) |
| `/users` | Gestion utilisateurs (filtres, CRUD, CSV) |
| `/orders` | Gestion commandes (filtres, CRUD) |
| `/proofs` | Preuves de paiement (validate/reject) |
| `/subscriptions` | Abonnements (7 actions par ligne, 4 modals) |
| `/inventory` | Comptes & profils (toggle status, marker badges, pagination) |
| `/content` | FAQ (card grid) |
| `/reviews` | Avis (lecture seule, pas de suppression) |
| `/giftcodes` | Codes cadeaux (toggle switch) |
| `/payment-numbers` | Numéros de paiement (toggle switch) |
| `/cards` | Cartes de paiement (toggle status, reveal/mask numéro) |
| `/messaging` | Messagerie (notifications + messages, modal envoi avec sélection users) |

### Composants clés

- `AdminLayout` : sidebar collapsible (persisté localStorage), title dynamique par route
- `SearchableSelect` : dropdown custom avec recherche auto si >=10 options, click-outside, focus clavier
- Toggle switches CSS (status comptes, status cartes, giftcodes, payment numbers)
- Modals `glass-panel` avec backdrop blur

---

## 8. Frontend mobile-admin (Expo SDK 57 / React Native)

### Stack

Expo SDK 57 + React Native 0.86 + React 19.2 + TypeScript + expo-router + Zustand + TanStack Query + expo-notifications + expo-secure-store + Ionicons. Gestionnaire de paquets : `bun`.

### Routes (16)

| Route | Description |
|---|---|
| `/login` | Connexion admin (phone + password, show/hide, admin gate) |
| `/(tabs)/dashboard` | KPIs + donut plateformes + dernières commandes |
| `/(tabs)/analytics` | Charts avec sélecteurs type + période |
| `/(tabs)/management` | Hub → proofs, subscriptions, users, reviews |
| `/(tabs)/edit` | Hub → orders, inventory, giftcodes, payment-numbers, cards, messaging, FAQ |
| `/users` | Liste avec recherche + filtres + ActionSheet |
| `/orders` | Liste + filtres + création (BottomSheet) |
| `/proofs` | 3 tabs + image viewer + validate/reject |
| `/subscriptions` | Tabs actifs/expirés + filtres + actions (renew, unlink, mark) |
| `/inventory` | Tabs comptes/profils + toggle status + markers + collapsible |
| `/cards` | Reveal/mask + toggle status + création |
| `/giftcodes` | Toggle + création |
| `/payment-numbers` | Toggle + création |
| `/messaging` | Tabs notif/msg + send + création |
| `/content` | FAQ CRUD |
| `/reviews` | Lecture seule (overview + filtre étoiles) |
| `/notifications` | Centre de notifications push (tabs lus/non-lus, mark read, deep linking) |
| `/settings` | Profil + config + déconnexion |

### Composants clés

- `BottomSheet` : Modal-based bottom sheet (KeyboardAvoidingView + ScrollView)
- `ActionSheet` : Bottom sheet pour les actions d'un item (⋮)
- `FilterSheet` : Bottom sheet pour les filtres groupés
- `SearchBar` : debounce intégré + bouton clear (Ionicons)
- `ToggleSwitch` : animation Reanimated + haptics
- `SkeletonCard` / `SkeletonList` : skeleton loading
- `Pagination` / `FilterPill` / `HubScreen` : composants partagés
- `ConfirmDialog` : dialog de confirmation (Ionicons)
- `StatusBadge` : badge coloré par statut

### Push notifications

- `expo-notifications` : enregistrement automatique du token au login, désenregistrement au logout
- Deep linking : `addNotificationResponseListener` → `router.push(data.screen)`
- Centre de notifications : tabs (Tous/Non lues/Lues), mark read on tap, badge non lues dans le header
- `useUnreadNotificationsCount` : poll toutes les 30s

### EAS Build

- 3 profiles : `development` (dev client), `preview` (APK test), `production` (release)
- `projectId` : `bca6c750-f6b4-4be2-a714-841c85cd3fb9`
- `appVersionSource: remote`
- `EXPO_PUBLIC_API_URL` injecté par profile

### Portage Flutter

Un prompt complet de portage vers Flutter (1008 lignes) est disponible à la racine du workspace : `prompt.md`. Il couvre la stack Flutter (Riverpod + Dio + go_router + FCM + freezed), l'architecture, tous les modèles, endpoints, écrans, tests, et la configuration Firebase.

---

## 9. Flux de paiement complet

```
1. Utilisateur sélectionne plateforme + durée
   → POST /api/v1/user/orders/ (purchase_init)
   → Order créé en status=pending_payment, prix recalculé serveur

2. Utilisateur upload preuve de paiement (capture Mobile Money)
   → POST /api/v1/user/payments/manual/{order_id}/ (multipart)
   → PaymentProof créé, Order → status=pending_validation

3. Admin valide la preuve
   → POST /api/v1/admin/proofs/{id}/validate/
   → PaymentCompletionService.process_completed_payment(order)
     → Order → status=completed
     → Subscription créée ou étendue
     → ProfileAssignmentService.assign_profile() (si pas renewal)
     → Notifications email + push envoyées (activation + accès)
```

## 10. Flux de renouvellement

```
1. Utilisateur initie un renouvellement
   → POST /api/v1/user/orders/{id}/renewal/
   → Nouvelle Order créée avec renewal_from=sub, motif=renewal/extension
   → purchase_date = ancienne expiration_date

2. Upload preuve + admin validation (même flux que paiement)
   → PaymentCompletionService._create_subscription(order)
     → Si renewal_from → étend l'expiration existante (pas de nouvelle sub)
```

## 11. Flux de messagerie (envoi groupé)

```
1. Admin crée une notification ou un message
   → POST /api/v1/admin/messaging/notifications/ (ou messages/)

2. Admin ouvre le modal d'envoi
   → Checkbox "Envoyer à tous" OU sélection individuelle d'utilisateurs avec email

3. Admin confirme l'envoi
   → POST /api/v1/admin/messaging/notifications/{id}/send/
   → Body: {send_to_all: false, recipients: [1,2,3], channel: "mail"}
   → send_bulk_notification_task.delay(notif_id, user_ids) (Celery)
   → Email envoyé à chaque utilisateur via Resend
```

## 12. Flux de notifications push temps réel

```
1. Événement métier (nouvelle commande, preuve uploadée, abonnement activé, etc.)
   → notify_* function dans notifications/services.py

2. Email (existant, inchangé)
   → _send_email(user, subject, template, context)
   → send_email_task.delay() → Resend

3. Push (nouveau, en parallèle)
   → _push_user(user, title, body, data, notification_type)
   → send_push_notification_task.delay()
   → push_service.send_push_to_user()
     → Fetch PushToken actifs pour l'utilisateur
     → POST Expo Push API (https://exp.host/--/api/v2/ios/sendPushNotification)
     → PushNotification.objects.create() (historique avec is_read, data pour deep linking)

4. Côté mobile
   → expo-notifications reçoit la push (foreground/background/killed)
   → Tap → addNotificationResponseListener extrait data.screen
   → router.push('/{screen}') (deep linking)
   → Notification stockée dans le centre de notifications (/notifications)
   → Mark read → POST /user/notifications/{id}/mark_read/
```
