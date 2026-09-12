# ORCA Next.js Console

This is the existing ORCA judge console, navigation view, and `/live` rescue interface. It uses the authoritative FastAPI backend in the repository root.

```bash
cp .env.example .env.local
npm ci
npm run dev -- --hostname 0.0.0.0
```

Set server-side `ORCA_BACKEND_URL` when FastAPI is not available at the local development default. Browser requests remain same-origin through `/api`; optional direct API/WebSocket URLs are documented in `.env.example`.

Validation:

```bash
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=moderate
```

See the repository root `README.md` for architecture, backend startup, environment variables, tests, and current unavailable Phase-2 components.
