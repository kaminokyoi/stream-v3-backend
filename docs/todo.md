# TODO — Audits & Améliorations

> Dernière mise à jour : 2026-08-02

---

## ORDRE D'IMPLÉMENTATION

**Les items sont ordonnés du MOINS risqué au PLUS risqué de casser l'application.**
- **Niveau 0** — Trivial, zéro risque (quick wins immédiats)
- **Niveau 1** — Faible risque (ajouts, config isolée)
- **Niveau 2** — Risque moyen (migrations, refactors localisés)
- **Niveau 3** — Risque élevé (refactors d'architecture, changements d'auth)

Implémenter niveau par niveau. Chaque niveau doit être validé avant de passer au suivant.

---

# AUDIT COMPLET — Sécurité, Architecture, Future-Proofing
> 75 items validés. Chacun : problème, solution, résultat attendu, risque de cassure.

---

## NIVEAU 0 — Trivial, zéro risque (quick wins immédiats)

### [ ] L0.1 — `retry: 0` sur les mutations React Query (doublons commande)
- **Problème** : `providers.tsx` des 2 frontends a `mutations: { retry: 1 }`. Une mutation (création commande, envoi notification, suppression) dont la réponse se perd est réexécutée → doublons.
- **Solution** : `mutations: { retry: 0 }` dans `web-user/components/providers.tsx` et `web-admin/components/providers.tsx`.
- **Résultat attendu** : Aucun doublon de POST/PATCH/DELETE.
- **Risque cassure** : Nul. Effort : 1 ligne par repo.

### [ ] L0.2 — `staleTime: 30s` au lieu de `0` (salve de requêtes au focus)
- **Problème** : `staleTime: 0` → toute donnée immédiatement stale. Combiné à `refetchOnWindowFocus: true`, chaque switch d'onglet re-fetch 6-10 queries (dashboard admin).
- **Solution** : `staleTime: 30_000, gcTime: 5*60*1000` dans `providers.tsx` des 2 frontends.
- **Résultat attendu** : -90% de requêtes au focus, UX fluide.
- **Risque cassure** : Nul.

### [ ] L0.3 — Committer les tests backend (`test_*.py` gitignorés)
- **Problème** : `.gitignore:12` ignore `test_*.py` → 7 fichiers (104 tests) non trackés. Perte disque = perte définitive.
- **Solution** : Retirer `test_*.py` du `.gitignore`, `git add tests/`, committer.
- **Résultat attendu** : Tests versionnés, CI future possible.
- **Risque cassure** : Aucun.

### [ ] L0.4 — Flutter : permission `INTERNET` au manifest de production
- **Problème** : `INTERNET` déclarée seulement dans `src/debug` et `src/profile`. Build release → app sans réseau.
- **Solution** : Ajouter `<uses-permission android:name="android.permission.INTERNET"/>` dans `mobile_admin/android/app/src/main/AndroidManifest.xml`.
- **Résultat attendu** : APK release fonctionnelle.
- **Risque cassure** : Aucun (ajout).

### [ ] L0.5 — Flutter : `google-services.json` gitignore + example
- **Problème** : `google-services.json` commité avec placeholders → pattern invite à commiter les vraies clés.
- **Solution** : gitignore `**/google-services.json` + `**/GoogleService-Info.plist` + créer `google-services.json.example` + setup doc README Flutter.
- **Résultat attendu** : Fuite évitée, setup dev documenté.
- **Risque cassure** : Aucun.

### [ ] L0.6 — Flutter : URL par défaut `10.0.2.2` au lieu de `localhost:8000`
- **Problème** : `http://localhost:8000` cassé sur device physique et émulateur Android (localhost = émulateur lui-même). HTTP clair bloqué par ATS iOS.
- **Solution** : Par défaut `http://10.0.2.2:8000/api/v1` (émulateur Android), override via `--dart-define=API_URL=...`. Staging HTTPS par défaut idéalement.
- **Résultat attendu** : App fonctionnelle out-of-the-box en dev.
- **Risque cassure** : Faible (change une valeur par défaut).

### [ ] L0.7 — Flutter : fix `AuthState.copyWith` (`error ?? this.error`)
- **Problème** : `error: error` au lieu de `error: error ?? this.error` → `copyWith(status: loading)` efface user/error.
- **Solution** : Pattern standard ou migrer `AuthState` vers `freezed`.
- **Résultat attendu** : Comportement intuitif.
- **Risque cassure** : Faible (revisiter 5 call sites).

### [ ] L0.8 — Flutter : `computePageCount` helper unique (magic `20` ×8)
- **Problème** : `(data.count / 20).ceil().clamp(1, 999)` copié 8 fois. `AppConstants.pageSize` existe mais inutilisé.
- **Solution** : Helper unique `computePageCount(total)` ou champ `numPages` dans `Paginated<T>`.
- **Résultat attendu** : Une source de vérité.
- **Risque cassure** : Aucun.

### [ ] L0.9 — Flutter : logger les 11 `catch (_)` silencieux
- **Problème** : 11 catch vides (push, auth, api). Aucune visibilité crashes prod.
- **Solution** : `package:logging` ou Crashlytics dans tous les catch. Exposer l'erreur au caller pour `registerToken`.
- **Résultat attendu** : Diagnostique crashes possible.
- **Risque cassure** : Aucun (ajout de logs).

### [ ] L0.10 — Dépendances inutiles : `animejs`, `@phosphor-icons/react`, `daisyui`
- **Problème** : `animejs` (0 import), `@phosphor-icons/react` (0 import, la version CSS est utilisée), `daisyui` (0 classe DaisyUI utilisée).
- **Solution** : `npm uninstall animejs @types/animejs @phosphor-icons/react daisyui` (vérifier `@plugin "daisyui"` dans globals.css avant de retirer).
- **Résultat attendu** : -200 KB node_modules, build plus rapide.
- **Risque cassure** : Nul.

### [ ] L0.11 — `react-apexcharts` en `dynamic()` (~200 KB)
- **Problème** : Import statique dans `web-admin/app/(admin)/page.tsx:4` → 200 KB dans le bundle initial.
- **Solution** : `const Chart = dynamic(() => import('react-apexcharts'), { ssr: false, loading: () => <Skeleton/> })`.
- **Résultat attendu** : -200 KB bundle initial, code-splitting immédiat.
- **Risque cassure** : Faible.

### [ ] L0.12 — `config/celery.py` : `logging` shadow le module + `print()` redondant
- **Problème** : `logging = getLogger(__name__)` shadow le module `logging`. `print()` redondant dans `debug_task`.
- **Solution** : Renommer en `logger`, supprimer le `print()`.
- **Résultat attendu** : Code propre.
- **Risque cassure** : Aucun.

### [ ] L0.13 — Assets Next boilerplate à supprimer
- **Problème** : `public/{file,globe,next,vercel,window}.svg` jamais référencés.
- **Solution** : `rm public/{file,globe,next,vercel,window}.svg` dans les 2 frontends.
- **Résultat attendu** : Dépôt plus léger.
- **Risque cassure** : Nul.

### [ ] L0.14 — `package.json` : `engines` + `packageManager` + `.nvmrc`
- **Problème** : Pas de pinning Node/npm → drift entre devs.
- **Solution** : `"engines": { "node": ">=20" }`, `"packageManager": "npm@10"`, `.nvmrc` avec `20`.
- **Résultat attendu** : Version Node uniformisée.
- **Risque cassure** : Nul.

### [ ] L0.15 — `dangerouslySetInnerHTML` sur titres statiques → `<h1>` direct
- **Problème** : `web-user/app/legal/{cgu,cgv,pc,mentions-legales}/page.tsx` utilisent `dangerouslySetInnerHTML` pour des littéraux statiques.
- **Solution** : Remplacer par `<h1>...</h1>` direct.
- **Résultat attendu** : Surface XSS éliminée.
- **Risque cassure** : Nul.

### [ ] L0.16 — `import Script from "next/script"` mort
- **Problème** : `web-user/app/dashboard/page.tsx:10` import non utilisé.
- **Solution** : Supprimer la ligne.
- **Risque cassure** : Nul.

### [ ] L0.17 — `WHATOMATE_API_KEY` vide → check au démarrage si 2FA WhatsApp activée
- **Problème** : Feature dégradée silencieusement si key absente.
- **Solution** : Si `WHATOMATE_API_KEY` vide et `ENVIRONMENT == 'production'`, logger.warning au démarrage (pas de crash — la feature est optionnelle).
- **Résultat attendu** : Dégradation visible dans les logs.
- **Risque cassure** : Aucun.

### [ ] L0.18 — 2FA UI : "5 minutes" hardcoded → `expires_in` du backend + countdown
- **Problème** : `web-admin/app/login/page.tsx:127` durcoded.
- **Solution** : Backend renvoie `expires_in` dans la réponse 2FA ; frontend affiche un countdown dynamique.
- **Résultat attendu** : Cohérence backend/frontend.
- **Risque cassure** : Faible.

### [ ] L0.19 — `cv_data/` PII → vérifier, gitignore ou déplacer
- **Problème** : Deux dossiers `csv_data/` (740 kB) avec dumps data potentiellement PII.
- **Solution** : Vérifier contenu, gitignore si PII, ou déplacer vers stockage privé.
- **Résultat attendu** : Conformité RGPD.
- **Risque cassure** : Aucun.

### [ ] L0.20 — `window.location.href` → `router.push` (sauf post-logout)
- **Problème** : `video-card.tsx:100` et `app/page.tsx:427` forcent un full reload.
- **Solution** : `router.push` partout sauf post-logout (où le reset est souhaitable).
- **Résultat attendu** : Transitions fluides.
- **Risque cassure** : Nul.

### [ ] L0.21 — `StatusBadge` uppercase forcé → décision design
- **Problème** : `text.toUpperCase()` sur tous les libellés y compris accentués.
- **Solution** : Décision design — laisser ou raffiner.
- **Risque cassure** : Casserait `widgets_test.dart` si modifié.

### [ ] L0.22 — `LoginScreen` double TextEditingController → `AppInput` accepte un `controller` externe
- **Problème** : `_LoginScreenState` crée des controllers mirroir synchronisés via `onChanged`.
- **Solution** : `AppInput` accepte un `controller` externe ou LoginScreen n'utilise pas de controller local.
- **Résultat attendu** : Pattern propre.
- **Risque cassure** : Faible.

### [ ] L0.23 — `analysis_options.yaml` Flutter minimal → activer `recommended` + `all`
- **Problème** : Seulement 6 règles. Manquent `avoid_dynamic_calls`, `require_trailing_commas`, etc.
- **Solution** : Activer le set `recommended` + `all` de `flutter_lints`, whitelister au cas par cas.
- **Résultat attendu** : Warnings au début, qualité long terme.
- **Risque cassure** : Faible (warnings, pas erreurs).

### [ ] L0.24 — `routerProvider` recréé à chaque changement auth state
- **Problème** : `Provider<GoRouter>` watch `authProvider` → rebuild GoRouter complet.
- **Solution** : `GoRouter(refreshListenable: ValueNotifier dérivé de authProvider.select(status))`.
- **Résultat attendu** : Pas de rebuild inutile.
- **Risque cassure** : Faible.

### [ ] L0.25 — `ConfirmDialog.loading` non câblé → double-clic possible
- **Problème** : `loading` exposé mais aucun appelant ne le passe → 2x delete possible.
- **Solution** : `StatefulBuilder` qui passe `loading` pendant l'await du provider.
- **Résultat attendu** : Pas de double action.
- **Risque cassure** : Faible.

### [ ] L0.26 — `Prefetch` des `<Link>` non maîtrisé
- **Problème** : Sidebar admin a 13 liens prefetch au load. Navbar user idem.
- **Solution** : `prefetch={false}` sur liens secondaires, garder prefetch sur top-3.
- **Résultat attendu** : Économie data mobile.
- **Risque cassure** : Nul.

### [ ] L0.27 — Animations `blob` permanentes → `prefers-reduced-motion`
- **Problème** : Consommation GPU continue, pas de respect de `prefers-reduced-motion`.
- **Solution** : `@media (prefers-reduced-motion: reduce) { .animate-blob, ... { animation: none !important; } }` dans globals.css.
- **Résultat attendu** : Accessibilité + batterie.
- **Risque cassure** : Nul.

### [ ] L0.28 — `Paginated<T>` dupliqué 3× → centraliser
- **Problème** : Type dupliqué dans `web-admin/lib/hooks.ts`, `web-user/lib/hooks.ts`, pages admin.
- **Solution** : Centraliser dans `lib/types.ts` (ou futur `@streampartner/shared`).
- **Résultat attendu** : Une source de vérité.
- **Risque cassure** : Nul.

### [ ] L0.29 — Magic numbers `DURATIONS`/`PAGE_SIZE`/couleurs → `lib/constants.ts`
- **Problème** : `DURATIONS` dupliqué avec casse différente (`1 Mois` vs `1 mois`), `PAGE_SIZE` répété, couleurs hardcodées.
- **Solution** : `lib/constants.ts` partagé avec `DURATIONS`, `PAGE_SIZE`, classes couleur.
- **Résultat attendu** : Désynchronisation backend impossible.
- **Risque cassure** : Nul.

### [ ] L0.30 — Convention status backend inconsistante (`active`/`actif`/`activate`)
- **Problème** : 3 conventions différentes pour le statut actif/inactif.
- **Solution** : Aligner sur `active`/`inactive` (+ migration data) ou introduire un enum côté client normalisé.
- **Résultat attendu** : Cohérence.
- **Risque cassure** : Moyen (migration + UI). **Sortir du Niveau 0 si migration.**

### [ ] L0.31 — `i18n` Flutter
- **Problème** : Toutes les strings FR codées en dur.
- **Solution** : Si une autre langue est prévue → `flutter_localizations` + `gen-l10n`. Sinon documenter FR-only.
- **Résultat attendu** : Maintainabilité.
- **Risque cassure** : Aucun (si FR-only).

### [ ] L0.32 — Nom snake_case vs camelCase inconsistent dans les types frontend
- **Problème** : Mix `is_staff` (backend) vs `has_personal` (backend aussi mais camelCase).
- **Solution** : Trancher et documenter : garder snake_case pour tout ce qui vient de l'API.
- **Résultat attendu** : Cohérence.
- **Risque cassure** : Nul.

---

## NIVEAU 1 — Faible risque (ajouts, config isolée)

### [ ] L1.1 — `SECURE_*` settings en prod (HSTS, SSL redirect, secure cookies)
- **Problème** : Pas de `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER`. HTTP non redirigé, cookies en clair, downgrade attacks.
- **Solution** : Bloc `if ENVIRONMENT == 'production'` dans `config/settings.py` :
  ```python
  SECURE_SSL_REDIRECT = True
  SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
  SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
  SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = True
  SECURE_CONTENT_TYPE_NOSNIFF = True
  SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
  ```
- **Résultat attendu** : HTTPS enforced, HSTS, cookies sécurisés.
- **Risque cassure** : Faible (⚠ Vérifier d'abord que le VPS termine TLS — sinon redirect loop).

### [ ] L1.2 — `FERNET_KEY` obligatoire en prod
- **Problème** : Si absent, dérive silencieusement de `SECRET_KEY` → rotation SECRET_KEY = cartes indéchiffrables (data loss).
- **Solution** : `if ENVIRONMENT == 'production' and not FERNET_KEY: raise RuntimeError('FERNET_KEY obligatoire en production')`.
- **Résultat attendu** : Pas de dérive silencieuse.
- **Risque cassure** : Faible.

### [ ] L1.3 — `DEBUG` silent-fall sur typo `ENVIRONMENT`
- **Problème** : `ENVIRONMENT="prod"` ou `production ` (espace) → DEBUG=True sur SQLite en prod.
- **Solution** : `DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'` ; refuser ENVIRONMENT hors `{development, staging, production}`.
- **Résultat attendu** : DEBUG=False garantit en prod.
- **Risque cassure** : Faible.

### [ ] L1.4 — ALLOWED_HOSTS / CORS via env vars
- **Problème** : Code en dur dans `config/settings.py`, localhost inclus en prod.
- **Solution** : `ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')` ; `CORS_ALLOWED_ORIGINS` uniquement via env (enlever localhost de la liste prod).
- **Résultat attendu** : Configuration prod sans commit.
- **Risque cassure** : Faible.

### [ ] L1.5 — Endpoint healthcheck
- **Problème** : Pas de `/health/` → Railway ne sait pas si app prête.
- **Solution** : `GET /api/v1/public/health/` check DB `SELECT 1` + Redis ping + S3 head → `{status, components}`. Configurer Railway healthcheck_path.
- **Résultat attendu** : Pas de traffic avant readiness.
- **Risque cassure** : Faible.

### [ ] L1.6 — `LOGGING` dict dans settings
- **Problème** : 19 modules utilisent `logger.info` silencieux. Debug prod impossible.
- **Solution** : Configurer `LOGGING` (console + fichier rotatif `logs/django.log`), INFO pour `api`, `payments`, `notifications`. Idéalement **JSON structuré** via `python-json-logger`.
- **Résultat attendu** : Traces exploitables en prod.
- **Risque cassure** : Faible.

### [ ] L1.7 — Sentry (error tracking)
- **Problème** : Exceptions 500 invisibles hors logs VPS.
- **Solution** : `sentry-sdk` (Django + Celery integrations) + `SENTRY_DSN` env + sampling 100% errors / 10% transactions.
- **Résultat attendu** : Alertes temps réel, stack traces enrichies.
- **Risque cassure** : Faible.

### [ ] L1.8 — Throttle login/OTP/register → brute force + OTP bombing
- **Problème** : `anon: 60/min` uniforme → 60 OTP/min WhatsApp = coûteux, brute force passwords.
- **Solution** : Throttle scoped par vue : `LoginThrottle: '5/min'` sur `jwt/create`, `OtpThrottle: '3/min'` sur `2fa-verify` (+ lockout après 5 échecs via cache), `RegisterThrottle: '5/min'` sur `users/`. Ajouter `django-axes`.
- **Résultat attendu** : Brute force et OTP bombing neutralisés.
- **Risque cassure** : Faible.

### [ ] L1.9 — `error.tsx` / `not-found.tsx` / `loading.tsx` (2 frontends)
- **Problème** : Pas d'error boundary, pas de 404 personnalisée → écran Next générique sans brand.
- **Solution** : `app/error.tsx` (signature `unstable_retry` en Next 16), `app/not-found.tsx`, `app/loading.tsx`, `app/(admin)/error.tsx` (préserve la sidebar).
- **Résultat attendu** : UX dégradée gracieuse, brand préservé, retry possible.
- **Risque cassure** : Faible.

### [ ] L1.10 — `next/image` (14 `<img>` → optimisation)
- **Problème** : Pas de WebP/AVIF, pas de lazy loading, pas de blur. Preuves de paiement en eager.
- **Solution** : `next/image` + `images.remotePatterns` dans `next.config.ts` pour `t3.storageapi.dev` et `ui-avatars.com`. Pour les previews File → `URL.createObjectURL`, laisser `<img>`.
- **Résultat attendu** : LCP amélioré, data mobile /2.
- **Risque cassure** : Faible (attention `fill` vs dimensions fixes).

### [ ] L1.11 — `catch {}` vides → helper `withToast` (mutations silencieuses)
- **Problème** : Quasi toutes les mutations avales l'erreur. Modal se ferme parfois même en cas d'erreur.
- **Solution** : Helper `withToast(promise, {success, error})` qui lit `err instanceof ApiError ? err.message` et `addToast`. Conserver le modal ouvert si erreur. Appliquer aux 12+ call sites.
- **Résultat attendu** : Feedback utilisateur, support désengorgé.
- **Risque cassure** : Faible.

### [ ] L1.12 — Modales a11y : focus trap / ARIA / Escape (composant `<Modal>` partagé)
- **Problème** : Modales sans `role="dialog"`, pas de trap, Escape inégal, Tab sort.
- **Solution** : Composant `<Modal>` partagé (`role="dialog" aria-modal`, FocusTrap, Escape, restore focus, `inert` React 19 sur le reste). Utilisé partout.
- **Résultat attendu** : Opérable au clavier, lecteurs d'écran informés.
- **Risque cassure** : Faible.

### [ ] L1.13 — `ConfirmDialog` réutilisable (remplacer `confirm()`/`alert()` natifs)
- **Problème** : `confirm()` bloque le thread UI, non personnalisable, inaccessible.
- **Solution** : `<ConfirmDialog>` réutilisable (déjà partiellement dans `payment/[orderId]/page.tsx:307`). L'utiliser partout.
- **Résultat attendu** : UX cohérente, traduisible, accessible.
- **Risque cassure** : Faible.

### [ ] L1.14 — A11y : aria-*, role, navigation clavier, labels
- **Problème** : Quasi-absente (`aria-label` manquant sur ~30 boutons icône, toasts sans `aria-live`, inputs sans `<label htmlFor>`, dropdowns sans navigation clavier).
- **Solution** : `aria-label` boutons icône ; `aria-live="polite"` toasts ; `aria-expanded`+`aria-haspopup="listbox"` triggers dropdown ; navigation flèches ; `<label htmlFor>` inputs.
- **Résultat attendu** : Conformité WCAG / RGAA France.
- **Risque cassure** : Faible.

### [ ] L1.15 — Contraste a11y (text-gray-500/600 sur #050505 sous WCAG AA)
- **Problème** : Textes gris trop clairs sur fond noir.
- **Solution** : Remonter à `text-gray-400` minimum. Auditer au contrast checker.
- **Résultat attendu** : Conformité contraste.
- **Risque cassure** : Nul.

### [ ] L1.16 — `runserver` → `gunicorn` en prod Docker
- **Problème** : `docker-compose.yaml:4` lance `runserver` (dev server) en prod.
- **Solution** : `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120`.
- **Résultat attendu** : Server prod performant.
- **Risque cassure** : Faible.

### [ ] L1.17 — Procfile / nixpacks / railway.json versionnés (config deploy)
- **Problème** : Aucun fichier config deploy versionné → perte config WeasyPrint.
- **Solution** : Committer `Procfile` (web/worker/beat/flower) + `nixpacks.toml` (deps système : libpango, libharfbuzz, libjpeg).
- **Résultat attendu** : Build/deploy reproductible.
- **Risque cassure** : Faible.

### [ ] L1.18 — Dockerfile / docker-compose / entrypoint gitignorés → committer
- **Problème** : `.gitignore` ignore ces 3 fichiers → setup nouvel env impossible depuis git.
- **Solution** : Dé-gitigner + committer.
- **Résultat attendu** : Infra reproductible depuis le repo.
- **Risque cassure** : Faible.

### [ ] L1.19 — `migrate` sur tous les services → service `release` one-shot
- **Problème** : N processes `migrate` en parallèle → locks Postgres, downtime.
- **Solution** : Service `release` one-shot (Procfile) séparé de web/worker/beat.
- **Résultat attendu** : Démarrage propre.
- **Risque cassure** : Faible.

### [ ] L1.20 — `collectstatic` automatisé en prod
- **Problème** : Pas automatisé → CSS/JS admin manquants sioublié.
- **Solution** : entrypoint ou build step Dockerfile.
- **Résultat attendu** : Statics toujours présents.
- **Risque cassure** : Faible.

### [ ] L1.21 — Python version alignée sur 3.13 partout
- **Problème** : `.python-version` (3.12) vs `Dockerfile` (3.13).
- **Solution** : Aligner sur 3.13 partout.
- **Résultat attendu** : Comportement identique dev/prod.
- **Risque cassure** : Faible.

### [ ] L1.22 — Versions backend `>=` → borner majeures (`<7` pour Django, etc.)
- **Problème** : 25 deps sur 26 en `>=` sans borne sup → Django 7 cassera.
- **Solution** : Borner : `"django>=6.0,<7"`, `"djangorestframework>=3.17,<4"`, etc.
- **Résultat attendu** : Reproductibilité.
- **Risque cassure** : Faible.

### [ ] L1.23 — Logs structurés JSON (`django-structlog` + `request_id`)
- **Problème** : Plain text → ingestion ELK/Loki difficile.
- **Solution** : `django-structlog` + middleware `request_id`.
- **Résultat attendu** : Corrélation d'incidents possible.
- **Risque cassure** : Faible.

### [ ] L1.24 — `apiFetch` web-admin omet AbortController sur retry → réaligner
- **Problème** : Divergence avec web-user.
- **Solution** : Ajouter l'AbortController sur le retry (comme web-user).
- **Résultat attendu** : Comportement cohérent.
- **Risque cassure** : Nul.

### [ ] L1.25 — `_hexToColor` dupliqué Flutter → extension partagée
- **Problème** : Méthode identique dupliquée dans `inventory_screen.dart` et `subscriptions_screen.dart`.
- **Solution** : `extension StringX on String` dans `lib/core/utils/color_utils.dart`.
- **Résultat attendu** : DRY.
- **Risque cassure** : Aucun.

### [ ] L1.26 — Push Flutter : `requestPermission` à chaque `getToken` + `onTokenRefresh`
- **Problème** : Popup potentiel intempestif, pas d'écouteur `onTokenRefresh`.
- **Solution** : Cacher le token après premier `getToken()` ; écouter `FirebaseMessaging.instance.onTokenRefresh` → `registerDevice`.
- **Résultat attendu** : Pas de popup, tokens à jour.
- **Risque cassure** : Faible.

### [ ] L1.27 — Types Flutter : `dynamic` → typé (`AdminUser`/`AdminProof`)
- **Problème** : Widgets reçoivent `final dynamic user` alors que classes freezed existent.
- **Solution** : Typer fortement. Pour `messaging_screen`, créer `sealed class NotificationItem` ou 2 widgets séparés.
- **Résultat attendu** : Autocompletion, refactoring safe.
- **Risque cassure** : Faible.

### [ ] L1.28 — Flutter : Firebase iOS `GoogleService-Info.plist` manquant → crash
- **Problème** : Pas de plist iOS → crash `[FirebaseCore] Default app has not been configured`.
- **Solution** : Télécharger le plist depuis la console Firebase, l'ajouter via Xcode (target Runner).
- **Résultat attendu** : Pas de crash iOS au lancement.
- **Risque cassure** : Aucun (ajout).

### [ ] L1.29 — Flutter : crashlytics / logging dans `catch`
- **Problème** : cf. L0.9 mais avec Crashlytics pour prod.
- **Solution** : `firebase_crashlytics` pour prod, `package:logging` pour dev.
- **Résultat attendu** : Crashes visibles Firebase console.
- **Risque cassure** : Faible.

### [ ] L1.30 — READMEs minimaux (3 repos : backend, web-user, web-admin)
- **Problème** : READMEs absents ou inutiles (boilerplate create-next-app).
- **Solution** : README minimal : quoi / stack / install rapide / commandes / lien docs. Le README Flutter documente `--dart-define=API_URL=...`, setup Firebase, où poser `google-services.json`.
- **Résultat attendu** : Onboarding sans aide externe.
- **Risque cassure** : Aucun.

### [ ] L1.31 — Docs `docs/` copiées dans le repo backend
- **Problème** : Docs vitent dans le repo parent, pas dans le repo backend.
- **Solution** : Copier `docs/` dans le repo backend.
- **Résultat attendu** : Dev qui clone le backend a accès à l'API doc.
- **Risque cassure** : Aucun.

### [ ] L1.32 — `AGENTS.md` enrichis (contexte projet)
- **Problème** : Les 2 `AGENTS.md` ne contiennent que l'avertissement Next.js.
- **Solution** : Enrichir : rôles, dépendances clés, commandes, conventions.
- **Résultat attendu** : Contexte projet pour les agents IA.
- **Risque cassure** : Aucun.

### [ ] L1.33 — Pre-commit hooks (ruff/eslint/prettier/gitleaks)
- **Problème** : Pas de hooks pre-commit.
- **Solution** : `.pre-commit-config.yaml` avec `ruff`, `djhtml`, `eslint`, `prettier`, `detect-secrets`/`gitleaks`.
- **Résultat attendu** : Qualité uniformisée, secrets bloqués avant commit.
- **Risque cassure** : Faible.

### [ ] L1.34 — Branch protection `main` (PR + review + CI green)
- **Problème** : Pas de protection, commits directs sur main.
- **Solution** : Branch protection GitHub : require PR + 1 review + CI green.
- **Résultat attendu** : Revue de code obligatoire.
- **Risque cassure** : Aucun.

### [ ] L1.35 — CI/CD GitHub Actions minimal par repo
- **Problème** : 0 workflow sur les 4 repos.
- **Solution** : Workflow minimal — backend (`uv sync --frozen && pytest --cov && pip-audit`), frontends (`npm ci && tsc --noEmit && npm run build && npm audit`), Flutter (`flutter test`).
- **Résultat attendu** : Régressions détectées avant merge.
- **Risque cassure** : Aucun.

### [ ] L1.36 — Tests frontend (Vitest + Playwright)
- **Problème** : Zéro test frontend (flow paiement critique non couvert).
- **Solution** : Vitest + React Testing Library pour composants/hooks ; Playwright E2E pour flow critique login → achat → validation admin.
- **Résultat attendu** : Régressions UI détectées.
- **Risque cassure** : Aucun.

### [ ] L1.37 — Tests backend coverage measurement (`--cov-fail-under`)
- **Problème** : `pytest-cov` installé mais `addopts` ne l'appelle pas.
- **Solution** : `addopts = "-ra --strict-markers --cov=. --cov-report=term-missing --cov-fail-under=70"`.
- **Résultat attendu** : Coverage mesurée et seuil green CI.
- **Risque cassure** : Faible.

### [ ] L1.38 — Tests Flutter (ApiClient/AuthNotifier/repos)
- **Problème** : Seuls models, login, widgets testés. ApiClient/AuthNotifier/PushService/repos non testés.
- **Solution** : `mocktail` (déjà en dev deps) + tests refresh 401 concurrent, gate admin, un repo CRUD, PushService.
- **Résultat attendu** : Refactor risqué sécurisé.
- **Risque cassure** : Aucun.

### [ ] L1.39 — Monitoring Celery : service flower + auth
- **Problème** : `flower` installé non lancé. Pas de vue sur les tâches en attente/échouées.
- **Solution** : Service flower dans docker-compose + auth basic + reverse proxy.
- **Résultat attendu** : Détection tâches zombies.
- **Risque cassure** : Faible.

### [ ] L1.40 — Versions S3 lifecycle (backup cross-region lifecycle)
- **Problème** : Media files S3 sans versioning, sans lifecycle. Preuves = pièces justificatives (à conserver 10 ans).
- **Solution** : Activer versioning + lifecycle sur le bucket T3.
- **Résultat attendu** : Preuves non perdues en cas de suppression accidentelle.
- **Risque cassure** : Aucun.

### [ ] L1.41 — Rotation des secrets (VPS Docker `.env` + Railway vars)
- **Problème** : `.env` local a SECRET_KEY prod + password DB + AWS + Resend en clair. Fuite déjà consommée si outils/agents ont eu accès. Rotation SECRET_KEY déclenche aussi L1.2 (FERNET dérive de SECRET_KEY).
- **Solution** : (a) Rotation immédiate de toutes les clés (SECRET_KEY, DB, AWS, Resend, Redis, FERNET) ; (b) `.env.local` factice pour dev (secrets uniquement dans le VPS Docker env-file et Railway vars) ; (c) pre-commit `gitleaks` (cf. L1.33) ; (d) vérifier que la DB n'est pas exposée sans filtrage IP.
- **Résultat attendu** : Aucun secret prod accessible hors hébergeur. Alertes sur futur commit de secret.
- **Risque cassure** : Faible (rotation transparente si faite proprement, mais nécessite `manage.py` re-chiffrement des `EncryptedCharField` si SECRET_KEY ou FERNET_KEY changent — voir L2.2/L2.3).

### [ ] L1.42 — Backups PostgreSQL (VPS Docker → S3 chiffré)
- **Problème** : Aucune stratégie documentée. Perte DB = perte users, orders, subscriptions, cartes.
- **Solution** : Vérifier backups auto du VPS (cron `pg_dump` du container postgres → S3 chiffré via `aws s3 cp`).Tester un restore au moins une fois par mois.
- **Résultat attendu** : RPO < 24h, RTO testé.
- **Risque cassure** : Aucun.

---

## NIVEAU 2 — Risque moyen (migrations, refactors localisés)

### [ ] L2.1 — `Account.email` + `Account.password` → `EncryptedCharField`
- **Problème** : `products/models.py:107-108` — credentials comptes tiers (Netflix, Prime) en plain text. Une breach DB = dump des credentials. `Card.numero` est déjà chiffré.
- **Solution** : Migrer les 2 champs vers `EncryptedCharField`. Migration + script one-shot de re-chiffrement des valeurs existantes (lire en clair, réécrire chiffré). Adapter `AdminAccountSerializer` (la lecture déchiffre automatiquement via `from_db_value`).
- **Résultat attendu** : Credentials comptes tiers chiffrés en DB.
- **Risque cassure** : Moyen (migration + re-chiffrement one-shot). ⚠ Si L1.41 (rotation SECRET_KEY) effectuée avant, re-chiffrer avec la nouvelle FERNET_KEY.

### [ ] L2.2 — `twofa_secret` → `EncryptedCharField`
- **Problème** : `users/models.py` — `twofa_secret` en clair. Compromission = 2FA cassé pour les users qui l'ont activée.
- **Solution** : Migrer vers `EncryptedCharField`. Migration + script one-shot de re-chiffrement. `verify_totp` lit via `from_db_value` (déchiffrement automatique).
- **Résultat attendu** : Secrets 2FA chiffrés en DB.
- **Risque cassure** : Moyen (idem L2.1).

### [ ] L2.3 — CVV carte bancaire jamais stocké (PCI-DSS)
- **Problème** : `products/models.py:56` — `cvv = CharField(max_length=10)`. Le CVV ne doit jamais être persisté.
- **Solution** : Supprimer le champ + migration + UI admin (ne pas afficher le CVV). Le CVV est saisi au moment du paiement uniquement.
- **Résultat attendu** : Conformité PCI sur ce point.
- **Risque cassure** : Moyen (migration + UI + données existantes à effacer).

### [ ] L2.4 — CSP / security headers (frontends)
- **Problème** : `next.config.ts` vide → pas de CSP, X-Frame-Options, HSTS. Clickjacking + injection scripts.
- **Solution** : `headers()` dans `next.config.ts` (CSP, X-Frame-Options=ny, X-Content-Type-Options=nosniff, Referrer-Policy, Permissions-Policy, HSTS). Démarrer en `Content-Security-Policy-Report-Only` pour ne rien casser, puis switch.
- **Résultat attendu** : Clickjacking + XSS mitigés.
- **Risque cassure** : Moyen (CSP peut casser scripts inline — tester).

### [ ] L2.5 — CSRF protection (si L3.1 cookies HttpOnly activé)
- **Problème** : Si on passe aux cookies (L3.1), le JWT Bearer n'immunise plus contre CSRF.
- **Solution** : `SameSite=Strict` suffit en première intention, ou CSRF token double-submit (`django-cors-headers` + middleware).Requis si L3.1 fait.
- **Risque cassure** : Moyen (dépend de L3.1).

### [ ] L2.6 — `paginated<T>` → centralisé (suppr. duplication)
- **Problème** : Type dupliqué 3×.
- **Solution** : Centraliser dans `lib/types.ts`.
- **Résultat attendu** : DRY.
- **Risque cassure** : Faible.

### [ ] L2.7 — `apiFetch` mutex refresh (web-user + web-admin)
- **Problème** : 5 requêtes 401 en parallèle → 5 refreshAccessToken → logout intempestifs.
- **Solution** : `let refreshPromise; ... .finally(() => refreshPromise = null)`. Les 5 requêtes attendent la même promesse.
- **Résultat attendu** : Plus de logout fantôme.
- **Risque cassure** : Moyen (à tester).

### [ ] L2.8 — Debounce search users/cards (1 req/frappe)
- **Problème** : `users/page.tsx:94`, `cards/page.tsx:89` → 1 requête par caractère.
- **Solution** : Hook `useDebouncedValue(value, 300)`.
- **Résultat attendu** : Charge serveur /10-20.
- **Risque cassure** : Faible.

### [ ] L2.9 — Persistance filtres en URL (`useSearchParams`)
- **Problème** : Incohérente (inventory persiste localStorage, users/orders non).
- **Solution** : Synchroniser filtres avec `useSearchParams` (URL). Permet partage de lien + back button.
- **Résultat attendu** : Cohérence + partage d'URL filtrées.
- **Risque cassure** : Faible.

### [ ] L2.10 — `MOTIONS`/`DURATIONS` centralisés (déjà L0.29, renforcé ici)
- **Résultat** : voir L0.29.

### [ ] L2.11 — TypeScript strict options additions (`noUncheckedIndexedAccess`, etc.)
- **Problème** : `tsconfig.json` strict mais pas `noUncheckedIndexedAccess` (accès tableaux non sécurisés).
- **Solution** : Activer progressivement `noUncheckedIndexedAccess`, `noImplicitOverride`, `noFallthroughCasesInSwitch`.
- **Résultat attendu** : Bugs runtime évités.
- **Risque cassure** : Moyen (peut révéler des erreurs existantes).

### [ ] L2.12 — `OpenAPI` schema (`drf-spectacular` + `openapi-typescript`)
- **Problème** : Types API frontend recodés à la main → drift silencieux.
- **Solution** : `drf-spectacular` côté backend (endpoint `/api/v1/schema/` + Swagger UI) ; `openapi-typescript` côté frontends pour générer `api/types.ts`.
- **Résultat attendu** : Types générés depuis le backend, drift détecté.
- **Risque cassure** : Faible.

### [ ] L2.13 — `react-hook-form` + `zod` sur forms critiques
- **Problème** : Validation impérative manuelle via `addToast`. Pas d'erreurs inline.
- **Solution** : `react-hook-form` + `zod` sur register, login, email-setup. Schémas partageables avec le backend via OpenAPI (L2.12).
- **Résultat attendu** : Erreurs inline, états disabled cohérents.
- **Risque cassure** : Moyen (refonte par form).

### [ ] L2.14 — Découpe composants monolithiques (dashboard, subscriptions, inventory)
- **Problème** : `dashboard/page.tsx` 1230l, `subscriptions/page.tsx` 1324l, `inventory/page.tsx` 960l.
- **Solution** : Découper par feature : `app/(admin)/subscriptions/_components/` (`FiltersBar`, `SubscriptionTable`, `RenewModal`, `MarkersModal`, `HistoryDrawer`) + `_hooks.ts` + `_types.ts`. Incrémental : une modale à la fois.
- **Résultat attendu** : Maintenabilité.
- **Risque cassure** : Moyen.

### [ ] L2.15 — Dropdown factorisé (en dernier)
- **Problème** : 6 réimplémentations ~600 lignes.
- **Solution** : Étendre `SearchableSelect` (mode non-searchable + accents + ARIA + navigation clavier) + supprimer les 5 versions. Préserver `fixed inset-0` de `subscriptions/page.tsx`.
- **Résultat attendu** : Divergence visuelle éliminée.
- **Risque cassure** : Moyen (préserver les spécificités de chaque page).

### [ ] L2.16 — Flutter : déconnexion silencieuse → màj state auth
- **Problème** : Refresh token échoue → tokens cleared mais `authProvider.status` reste `authenticated` → user bloqué.
- **Solution** : `AuthEventBus` (stream) que l'`_AuthInterceptor.onError` émet `logout` → `authProvider.notifier` écoute et appelle `logout()`.
- **Résultat attendu** : Déconnexion fiable.
- **Risque cassure** : Moyen.

### [ ] L2.17 — Flutter : refresh token concurrent (file d'attente)
- **Problème** : 5 requêtes 401 → 4 rejetées (`return false`).
- **Solution** : `Completer<bool>` + file de `RequestInterceptorHandler` en pause. Toutes attendent le même refresh puis sont rejouées.
- **Résultat attendu** : Zéro erreur fantôme post-refresh.
- **Risque cassure** : Moyen.

### [ ] L2.18 — Flutter : cache offline (`dio_cache_interceptor` + `connectivity_plus`)
- **Problème** : App inutilisable métro, `FutureProvider` affiche juste `ErrorState`.
- **Solution** : `dio_cache_interceptor` (cache GET 5min) + `connectivity_plus` (banner offline) + persister `DashboardStats` via `AsyncCache.setter`.
- **Résultat attendu** : Résilience réseau.
- **Risque cassure** : Moyen.

### [ ] L2.19 — Fusionner 2 Redis (broker + cache sur 2 instances)
- **Problème** : `CELERY_BROKER_URL` → Railway, `REDIS_URL` → autre instance Railway. Probablement involontaire → coûts doublés.
- **Solution** : Fusionner sur une Redis avec deux DB (`?db=0` / `?db=1`). Vérifier d'abord si involontaire.
- **Résultat attendu** : Coûts /2, debug simplifié.
- **Risque cassure** : Faible.

### [ ] L2.20 — `docker-compose.yaml` : healthcheck postgres + `condition: service_healthy`
- **Problème** : Pas de healthcheck PG/Redis. `web` peut démarrer avant PG.
- **Solution** : `healthcheck: pg_isready` + `condition: service_healthy`.
- **Résultat attendu** : Démarrage déterministe.
- **Risque cassure** : Faible.

### [ ] L2.21 — `Account.save()` chaîne fragile → extraire vers `pre_save` receiver/service
- **Problème** : Dérivation `start_date` depuis `end_date` qui re-déclenche le calcul → effets de bord.
- **Solution** : `@receiver(pre_save, sender=Account)` ou service dédié. `save()` ne fait que le minimum.
- **Résultat attendu** : Pas d'effet de bord en chaîne.
- **Risque cassure** : Moyen.

### [ ] L2.22 — `.env.example` (corriger typo `.env.exemple`) + créer pour frontends
- **Problème** : Fichier mal nommé, manquant pour web-user/web-admin.
- **Solution** : Renommer + créer `.env.example` frontends avec `NEXT_PUBLIC_API_URL`.
- **Résultat attendu** : Doc install fonctionnelle.
- **Risque cassure** : Aucun.

### [ ] L2.23 — Monorepo hybride : clarifier (vrai monorepo OU vrai multi-repos)
- **Problème** : Parent `stream-v3` snapshot backend/web-* + sous-repos séparés → divergence.
- **Solution** : Soit vrai monorepo (un git, 4 dossiers, CI par path), soit vrai multi-repos (parent n'indexe rien).
- **Résultat attendu** : Source de vérité unique.
- **Risque cassure** : Élevé (restructuring). **Reporter à un audit d'organisation.**

### [ ] L2.24 — Tests migration rollback (CI)
- **Problème** : Aucun test de reverse. Pattern "rebuild all migrations" dangereux en prod.
- **Solution** : En CI, `migrate` puis `migrate <app> <previous>` pour valider le reverse.
- **Résultat attendu** : Rollback possible en cas de migration cassée.
- **Risque cassure** : Faible.

### [ ] L2.25 — Code dupliqué entre web-user et web-admin (package partagé)
- **Problème** : `apiFetch`, `auth-store`, `countries.ts`, `hooks.ts` dupliqués. Divergence déjà observée.
- **Solution** : Package `@streampartner/shared` (npm workspaces) ou monorepo.
- **Résultat attendu** : Une source de vérité.
- **Risque cassure** : Moyen (refonte incrémentale).

---

## NIVEAU 3 — Risque élevé (refactors d'architecture, changements d'auth)

### [ ] L3.1 — JWT → cookies `HttpOnly` + CSRF (backend + 2 frontends)
- **Problème** : `localStorage` → XSS = vol de session.
- **Solution** : Backend SimpleJWT → `JWT_AUTH_COOKIE`/`JWT_AUTH_REFRESH_COOKIE` (httpOnly + Secure + SameSite=Lax) + CSRF. Frontend : `credentials: 'include'`, plus d'`Authorization`, plus de `localStorage`. Migration des sessions existantes (double-auth pendant 7 jours).
- **Résultat attendu** : Immunité XSS.
- **Risque cassure** : **Élevé.** Refonte auth backend+frontend parallèle. Planifier après P0/P1/P2.

### [ ] L3.2 — ESLint activation (peut révéler beaucoup de warnings)
- **Problème** : 0 guard statique.
- **Solution** : `eslint.config.js` flat + script `lint` + pre-commit lint-staged.
- **Résultat attendu** : Dette maitrisée.
- **Risque cassure** : Moyen (génére beaucoup de warnings initialement — corriger progressivement).

### [ ] L3.3 — Server Components (landing page publique + progressive)
- **Problème** : 33 fichiers `"use client"` y compris landing publique → SEO/LCP dégradé.
- **Solution** : Convertir `app/page.tsx` en Server Component (fetch serveur + `next.revalidate=60`), isoler interactions en sous-composants client. Pour le dashboard, prefixer par layout serveur auth (nécessite L3.1 fait avant).
- **Résultat attendu** : HTML indexable, LCP /2 sur mobile.
- **Risque cassure** : **Élevé.** Refonte architecturale incrémentale. Faire APRÈS L3.1.

---

## AUDIT INITIAL — Scalabilité & Feature-Proofing
> généré le 2026-07-31 — 22 items (P0/P1/P2/P3). Conservés pour référence.

### P0 — Critique (à faire en premier)

#### [ ] 1. Concurrency : `select_for_update` sur profile assignment
- **Fichier** : `payments/services.py` → `ProfileAssignmentService.assign_profile`
- **Problème** : 2 users validés simultanément → même profil assigné à >2 subs.
- **Fix** :
  ```python
  with transaction.atomic():
      profile = Profile.objects.select_for_update().filter(
          account__platform=platform, ...
      ).annotate(active_count=Count('subscriptions', filter=Q(...))).first()
      if profile and profile.active_count < profile.place:
          subscription.profile = profile
          subscription.save(update_fields=['profile'])
  ```
- **Effort** : ~1h

#### [ ] 2. Concurrency : `select_for_update` sur gift code redemption
- **Fichier** : `payments/services.py` lignes 87–96 et 158–164
- **Problème** : Code `usage_limit=1` utilisé 2x en parallèle → `used_count` écrasé.
- **Fix** :
  ```python
  updated = GiftCode.objects.filter(
      pk=code.pk, used_count__lt=F('usage_limit')
  ).update(used_count=F('used_count') + 1)
  if updated == 0:
      raise ValidationError("Code expiré ou limite atteinte")
  ```
- **Effort** : ~30min

#### [ ] 3. Idempotence : admin validate (double-clic)
- **Fichier** : `api/views/admin/orders.py` → `AdminPaymentProofViewSet.validate`
- **Problème** : Pas de guard `if proof.validated: return 409`. Double-clic → `process_completed_payment` x2.
- **Fix** :
  ```python
  proof = PaymentProof.objects.select_for_update().get(pk=pk)
  if proof.validated or proof.rejected:
      return Response({'detail': 'Déjà traité.'}, status=409)
  ```
- **Effort** : ~30min

#### [ ] 4. Bug : boucle infinie notifications expired
- **Fichier** : `payments/tasks.py` → `check_expiring_subscriptions_task`
- **Problème** : Inclut `status='expired'` dans la query → les mêmes subs expirés re-notifiés chaque jour à 08h00.
- **Fix** : Filtrer uniquement `status='active'` pour le passage expired, puis `update(status='expired')`. Ajouter un flag `expired_notified=True` si on veut notifier J+1.
- **Effort** : ~1h

---

### P1 — Important (performance + corrections)

#### [ ] 5. N+1 queries : `get_platform_style` dans dashboard
- **Fichier** : `core/services.py` → `build_dashboard_subscriptions` ligne 95
- **Problème** : `Platform.objects.get(name=name)` appelé par subscription → N requêtes pour N subs.
- **Fix** : Précharger `platforms = {p.name: p for p in Platform.objects.all()}` une fois avant la boucle.
- **Effort** : ~30min

#### [ ] 6. Cache pricing + guard prix négatifs
- **Fichier** : `core/utils.py` → `calculate_price`, `core/models.py` → `PriceTier.computed_prices`
- **Problèmes** :
  - Chaque `calculate_price` hit la DB (pas de cache).
  - `base_price=400` → `year = 800-2000 = -1200` (prix négatif non protégé).
- **Fix** :
  ```python
  cache_key = f"price:{platform}:{duration}:{type}:{sub_type}"
  return cache.get_or_set(cache_key, _compute, timeout=300)
  def computed_prices(self):
      return {k: max(0, v) for k, v in raw_prices.items()}
  ```
- **Effort** : ~1h

#### [ ] 7. Duration parsing fragile (`duration[0]`)
- **Fichier** : `core/utils.py` → `calculate_expiration` ligne 37
- **Problème** : `int(duration[0])` lit le premier caractère → `"12 mois"` donne `1` au lieu de `12`.
- **Fix** : Remplacer par un `DURATION_MAP = {'1 mois': 1, '3 mois': 3, '6 mois': 6, '1 an': 12}`.
- **Effort** : ~30min

#### [ ] 8. `platform_choices()` évalué au import time
- **Fichier** : `core/utils.py` lignes 6–16
- **Problème** : Choices gelées au moment de l'import du module. Nouvelles plateformes invisibles jusqu'au restart. `print()` au lieu de logger.
- **Fix** : Rendre la fonction lazy (déjà un callable passé à `choices=`) ou ajouter un cache court TTL.
- **Effort** : ~30min

#### [ ] 9. Account `save()` — `remaining_day` recalculé à chaque save
- **Fichier** : `products/models.py` lignes 190–200
- **Problème** : `remaining_day` recalculé même quand on change juste `status`. Conflit avec le Celery task `update_remaining_days`.
- **Fix** : Séparer les responsabilités : `save()` dérive `end_date` depuis `start_date + month_count` uniquement. `remaining_day` calculé seulement par le task quotidien.
- **Effort** : ~1h

---

### P2 — Améliorations (fiabilité + sécurité)

#### [ ] 10. Retry / idempotency Celery tasks
- **Fichiers** : `notifications/tasks.py`, `payments/tasks.py`
- **Problème** : Pas de `autoretry_for`, pas de `max_retries`, pas de clé d'idempotency. Une panne Resend/Expo = notification perdue.
- **Fix** :
  ```python
  @shared_task(
      autoretry_for=(Exception,),
      max_retries=3,
      retry_backoff=True,
      retry_backoff_max=300,
  )
  def send_email_task(...):
      ...
  ```
- **Effort** : ~2h

#### [ ] 11. `Profile.is_principal` flag
- **Fichiers** : `products/models.py`, `core/services.py`
- **Problème** : La règle Spotify/Apple Music masque les credentials sauf pour le profil principal, défini comme `Min(id)`. Si le profil principal est supprimé et recréé, le mauvais profil devient "principal".
- **Fix** : Ajouter `is_principal = models.BooleanField(default=False)` sur `Profile`. Mettre à jour `SubscriptionAccessService` pour l'utiliser au lieu de `Min(id)`.
- **Effort** : ~1h

#### [ ] 12. Gift code : vérification platform manquante côté serializer
- **Fichier** : `api/serializers/user/__init__.py` → `GiftCodeVerifySerializer.validate`
- **Problème** : Si `platform` n'est pas passé, `is_valid(None)` retourne `True` même pour un code limité à une plateforme.
- **Fix** : Exiger `platform` dans le serializer ou rejeter les codes plateforme-spécifiques sans plateforme.
- **Effort** : ~30min

#### [ ] 13. PaymentProof.delete : image2 orpheline
- **Fichier** : `payments/models.py` lignes 177–180
- **Problème** : `delete()` supprime `self.image` mais pas `self.image2` → fichier orphelin sur S3.
- **Fix** :
  ```python
  def delete(self, *args, **kwargs):
      for field in [self.image, self.image2]:
          if field:
              field.delete(save=False)
      super().delete(*args, **kwargs)
  ```
- **Effort** : ~15min

#### [ ] 14. Refactor Account.save() — séparation des responsabilités
- **Fichier** : `products/models.py`
- **Problème** : La chaîne d'auto-calc dans `save()` est fragile et crée des effets de bord.
- **Fix** : Extraire vers un `@receiver(pre_save)` ou un service dédié.
- **Effort** : ~1h

#### [ ] 15. Compteurs non-atomiques dans les signals
- **Fichiers** : `products/signals.py` lignes 13–16, `payments/signals.py` lignes 8–14
- **Problème** : `instance.account.profiles -= 1; instance.account.save()` — read-modify-write non atomique. Incohérent avec `Order.save()` qui utilise `F()`.
- **Fix** : Utiliser `Account.objects.filter(pk=...).update(profiles=F('profiles') - 1)`
- **Effort** : ~30min

---

### P3 — Évolutions futures

#### [ ] 16. Payment gateway integration (FedaPay / Wave / CinetPay)
- **Solution** : Intégrer un gateway pour auto-validation des paiements Mobile Money via webhook.
- **Effort** : ~1 semaine

#### [ ] 17. Audit log credentials admin
- **Solution** : Model `CredentialViewLog(user, account, viewed_by, viewed_at)` + signal sur `AdminAccountViewSet.retrieve`.
- **Effort** : ~2h

#### [ ] 18. Règles de masquage configurables par plateforme
- **Solution** : Ajouter des flags sur `Platform` : `mask_credentials`, `mask_all`, `principal_only`. `SubscriptionAccessService` lit les flags depuis la DB.
- **Effort** : ~2h

#### [ ] 19. Zero-fill des jours vides dans les charts
- **Fichier** : `api/views/admin/dashboard.py` → `_revenue_data`, `_users_data`, `_subs_data`
- **Problème** : Le chart n'affiche que les jours avec données (3 labels sur 7 jours). Pas de zero-fill pour les jours vides.
- **Solution** : Générer la plage de dates complète côté backend et filler avec 0.
- **Effort** : ~1h

#### [ ] 20. Task locking pour Celery beat
- **Solution** : Redis lock (`cache.lock`) ou `celery-once` / `celery-singleton`.
- **Effort** : ~1h

#### [ ] 21. Batch push admin
- **Fichier** : `notifications/push_service.py` → `send_push_to_admins`
- **Problème** : N requêtes Expo séparées au lieu d'un batch.
- **Solution** : Grouper les tokens dans une seule requête Expo (jusqu'à 100 par batch).
- **Effort** : ~1h

#### [ ] 22. Profile assignment retry automatique
- **Problème** : Si aucun profil n'est disponible au moment de la validation, la subscription reste profile-less jusqu'à intervention manuelle.
- **Solution** : Task Celery qui re-tente l'assignation quand de nouveaux comptes/profils sont ajoutés.
- **Effort** : ~2h