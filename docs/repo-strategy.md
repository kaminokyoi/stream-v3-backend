# Repository Strategy

## Current state (2026-08)

StreamPartner uses **multi-repos** (5 Git repositories), not a monorepo. The
parent `stream-v3` repo holds only documentation; the 4 children are
independent repos on their own `beta`/`main` branches.

| Repo             | Purpose                              | Hosting |
|------------------|--------------------------------------|---------|
| `stream-v3`      | docs/ (audit, runbooks)              | GitHub  |
| `backend`        | Django REST API                     | VPS Docker |
| `web-user`       | Next.js user frontend                | Railway |
| `web-admin`      | Next.js admin panel                  | Railway |
| `mobile_admin`   | Flutter admin app (iOS+Android)      | Stores  |

## Why multi-repo (not monorepo)

- Independent deploy cadences (backend changes don't force frontend rebuilds)
- Different tooling stacks (uv/npm/flutter) with isolated lock files
- Independent CI/CD pipelines
- Team can split ownership later

## Shared code between web-user / web-admin

Both Next.js frontends duplicate ~600 lines (apiFetch, types, hooks, toasts,
Modal, ConfirmDialog). Two options were considered for L2.25:

1. **Extract to a private npm package** (`@streampartner/web-shared`)
   - Pro: versioned, no path-hacks
   - Con: publish workflow overhead for small team
2. **Keep duplication** with `AGENTS.md` convention
   - Pro: zero infra
   - Con: drift over time

**Current decision:** keep duplication for now; revisit when drift becomes a
maintenance burden. The new shared components (`Modal`, `ConfirmDialog`,
`toast.tsx`, `useDebouncedValue`) are intentionally identical between repos
to ease a future extraction.

## Coordination across repos

- All repos have `main` (production) + `beta` (integration) branches
- `beta` is merged to `main` after manual validation
- Cross-repo API contracts documented in `backend/docs/api.md`
- OpenAPI schema (L2.12) generated from backend, types can be regenerated
  via `openapi-typescript` when contracts change