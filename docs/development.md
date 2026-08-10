# StreamPartner — Guide de développement

> Installation, commandes, conventions et déploiement.

---

## 0. Structure des repos Git

Chaque application a désormais son propre repo Git :

| Repo | URL GitHub | Description | Stack |
|---|---|---|---|
| `streampartner-backend` | `https://github.com/kaminokyoi/stream-v3-backend.git` | API Django REST + Celery + push | Django 6.0 + DRF + SimpleJWT |
| `streampartner-web-user` | `https://github.com/kaminokyoi/stream-v3-web-user.git` | Frontend utilisateur | Next.js + TypeScript + Tailwind |
| `streampartner-web-admin` | `https://github.com/kaminokyoi/stream-v3-web-admin.git` | Frontend admin | Next.js + TypeScript + Tailwind |
| `streampartner-mobile-admin` | `https://github.com/kaminokyoi/stream-v3-mobile-admin.git` | App mobile admin | Expo SDK 57 + React Native (Flutter planifié — voir `prompt.md`) |

Pour développer localement, cloner chaque repo dans le même dossier parent :

```bash
mkdir streampartner && cd streampartner
git clone https://github.com/kaminokyoi/stream-v3-backend.git backend
git clone https://github.com/kaminokyoi/stream-v3-web-user.git web-user
git clone https://github.com/kaminokyoi/stream-v3-web-admin.git web-admin
git clone https://github.com/kaminokyoi/stream-v3-mobile-admin.git mobile-admin
```

---

## 1. Prérequis

| Outil | Version | Rôle |
|---|---|---|
| Python | 3.12+ | Backend Django |
| Node.js | 18+ | Frontends Next.js |
| bun | latest | Mobile admin (Expo) — gestionnaire de paquets |
| Flutter | latest stable | Mobile admin (portage planifié — voir `prompt.md`) |
| uv | latest | Gestionnaire de paquets Python (Astral) |
| npm / bun | latest | Gestionnaire de paquets Node.js (bun pour mobile-admin) |
| Redis (optionnel) | 7+ | Celery broker + cache (fallback LocMem en dev) |

---

## 2. Installation backend

```bash
cd backend

# Installer les dépendances
uv sync

# Configurer l'environnement
cp .env.example .env  # ou créer .env manuellement
# Éditer .env avec les valeurs appropriées (voir docs/api.md §9)

# Migrations
uv run python manage.py migrate

# Créer un superutilisateur
uv run python manage.py createsuperuser

# Lancer le serveur de dev
uv run python manage.py runserver
```

### Configuration `.env` minimale (dev)

```env
ENVIRONMENT=development
SECRET_KEY=your-secret-key-here
CACHE_BACKEND=locmem
# REDIS_URL=redis://localhost:6379  # décommenter si Redis disponible
```

### Cache

Le backend utilise un fallback automatique :
- Si `REDIS_URL` est vide **ou** `CACHE_BACKEND=locmem` → `LocMemCache` (local memory, pas de Redis requis)
- Sinon → Redis cache avec `socket_timeout=2s`

En développement, mettre `CACHE_BACKEND=locmem` dans `.env` pour fonctionner sans Redis.

---

## 3. Installation web-user

```bash
cd web-user
npm install
cp .env.example .env.local  # ou créer .env.local
npm run dev
```

### `.env.local`

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Build

```bash
npm run build   # build production
npm run start   # serveur production
```

---

## 4. Installation web-admin

```bash
cd web-admin
npm install
cp .env.example .env.local  # ou créer .env.local
npm run dev
```

### `.env.local`

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Build

```bash
npm run build   # build production
npm run start   # serveur production
```

---

## 5. Installation mobile-admin (Expo SDK 57)

```bash
cd mobile-admin
bun install
```

### `.env`

```
EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Démarrer

```bash
bun expo start              # dev server
bun expo start --android    # Android
bun expo start --ios        # iOS
bun expo start --web        # Web (développement)
bun run typecheck           # TypeScript check
```

### EAS Build

```bash
bun x eas-cli build --profile development --platform android  # dev client
bun x eas-cli build --profile preview --platform android      # APK de test
bun x eas-cli build --profile production --platform android   # release
bun x eas-cli submit --platform android                       # store submission
```

> Note : Sur Node 24+, utiliser `NODE_OPTIONS=--no-strip-types` si erreur de type stripping.

---

## 6. Commandes utiles

### Backend

```bash
# Tests
uv run pytest tests/                          # tous les tests
uv run pytest tests/test_api_admin.py -xvs    # un fichier avec détail
uv run pytest -k "card"                       # tests par nom

# Migrations
uv run python manage.py makemigrations        # générer
uv run python manage.py migrate               # appliquer

# Serveur
uv run python manage.py runserver             # dev server (port 8000)

# Celery (optionnel en dev — EAGER mode en tests)
uv run celery -A config worker -l info        # worker
uv run celery -A config beat -l info          # beat scheduler

# Shell
uv run python manage.py shell                 # Django shell

# Vérifications
uv run python manage.py check                 # system check
uv run python manage.py collectstatic --noinput  # static files
```

### Frontends

```bash
# web-user
cd web-user && npm run dev     # dev server (port 3000)
cd web-user && npm run build   # build production

# web-admin
cd web-admin && npm run dev    # dev server (port 3001)
cd web-admin && npm run build  # build production

# mobile-admin (Expo SDK 57)
cd mobile-admin && bun expo start              # dev server
cd mobile-admin && bun run typecheck           # TypeScript check
cd mobile-admin && bun x eas-cli build --profile development --platform android
cd mobile-admin && bun x eas-cli build --profile production --platform android
```

---

## 7. Conventions de code

### Général

- **Utiliser `uv run`** pour toutes les commandes Python backend
- **Pas de commentaires** dans le code (sauf demande explicite)
- **Reproduction fidèle (pixel-perfect)** : les templates Django sont la source de vérité pour les frontends Next.js
- **100% de la logique métier conservée** : pricing, masquage accès, bonus avis, renouvellements, attribution profils, notifications Celery

### Backend

- **Tests obligatoires** : pytest-django, à chaque refactoring/feature
- **Services** : la logique métier va dans `services/` (pas dans les vues ou les `save()`)
- **Signals** : notifications de changement d'accès via signals (pas dans `save()`)
- **Sérialiseurs** : DRF serializers dans `api/serializers/`, organisés par groupe (public, user, admin)
- **Filtrage** : manuel dans `get_queryset` (pas de DRF filter_backends)
- **Pricing** : toujours recalculé serveur via `calculate_price()`
- **Masquage accès** : côté serializer (jamais confiance au frontend)
- **Chiffrement** : `EncryptedCharField` (Fernet) pour données sensibles (Card.numero)

### Frontend (Next.js)

- **TypeScript** strict
- **Tailwind v4** + DaisyUI pour le styling
- **CSS custom classes** dans `@layer components` (pour que les utilities Tailwind écrasent correctement)
- **SearchableSelect** pour tous les dropdowns dans les modals (recherche auto si >=10 options)
- **Toggle switches CSS** pour les statuts (comptes, cartes, giftcodes, payment numbers)
- **Zustand** pour l'auth store (persisté)
- **TanStack Query** pour le data fetching (cache, invalidation, optimistic updates)
- **Phosphor Icons** via npm (`@phosphor-icons/web`) — pas de CDN
- **ApexCharts** via npm (`react-apexcharts`) — pas de CDN
- **GSAP / Motion One** : imports statiques (pas de CDN dynamique)

### Mobile admin (Expo / React Native)

- **TypeScript** strict
- **expo-router** (file-based routing, comme Next.js)
- **Zustand** pour l'auth store (tokens via `expo-secure-store`)
- **TanStack Query** pour le data fetching
- **expo-notifications** pour les push (auto-register au login, auto-unregister au logout)
- **Ionicons** (`@expo/vector-icons`) — jamais d'emojis
- **Dark theme** uniquement
- **Cards** au lieu de tables, **ActionSheet** (⋮) au lieu de boutons inline, **BottomSheet** au lieu de modales flottantes
- **bun** comme gestionnaire de paquets (pas npm)
- **EAS Build** pour les builds (3 profiles: development, preview, production)
- `NODE_OPTIONS=--no-strip-types` sur Node 24+

### Tests

- `CELERY_TASK_ALWAYS_EAGER=True` en tests (tâches synchrones — y compris les push tasks)
- `LocMemCache` en tests (pas de Redis requis)
- Fixtures dans `conftest.py` : `api_client`, `admin_client`, `user`, `make_order`, `make_subscription`, `make_account`, `make_profile`, `make_platform`, `make_price_tier`
- **104 tests** backend au total (13 public + 36 user + 58 admin + 10 push/pricing/access)

---

## 8. Déploiement

### Docker

Le backend utilise Docker (alpine) avec `Dockerfile` + `docker-compose.yaml`.

```bash
# Build
docker build -t streampartner-backend .

# Run
docker-compose up
```

### Railway

Le projet est déployé sur Railway. Variables d'environnement de production :

| Variable | Valeur prod |
|---|---|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY` | (clé secrète forte) |
| `DATABASE_URL` | `postgresql://...` |
| `REDIS_URL` | `redis://...` |
| `AWS_ACCESS_KEY_ID` | (clé AWS) |
| `AWS_SECRET_ACCESS_KEY` | (clé AWS) |
| `AWS_S3_BUCKET_NAME` | (nom du bucket) |
| `RESEND_API_KEY` | (clé Resend) |
| `CORS_ALLOWED_ORIGINS` | `https://web-user.example.com,https://web-admin.example.com` |

### Checklist de déploiement

1. `uv run python manage.py check` — aucune erreur
2. `uv run python manage.py migrate` — migrations appliquées
3. `uv run python manage.py collectstatic --noinput` — fichiers statiques collectés
4. `uv run pytest tests/` — tous les tests passent (104 tests)
5. `cd web-user && npm run build` — build frontend user
6. `cd web-admin && npm run build` — build frontend admin
7. `cd mobile-admin && bun x eas-cli build --profile production --platform android` — build mobile admin
8. Celery worker + beat démarrés (pour les tâches programmées + push notifications)

---

## 9. Documentation

| Fichier | Description |
|---|---|
| `docs/audit.md` | Audit Phase 1 + suivi des phases + règles métier + corrections |
| `docs/api.md` | Documentation API complète (endpoints, conventions, sécurité, env vars, push) |
| `docs/architecture.md` | Architecture (apps, modèles, services, flux, mobile-admin, push) |
| `docs/development.md` | Ce fichier — guide de développement |
| `prompt.md` | Prompt de portage mobile-admin Expo → Flutter (1008 lignes, à la racine du workspace) |
