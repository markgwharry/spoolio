# Frontend context (React 19 + Vite)

- **All authenticated API calls go through `authFetch`** from `src/AuthContext.jsx`. It
  attaches the token, dedupes refreshes and retries once on 401. Never set an
  `Authorization` header by hand, and never use raw `fetch` except on pre-auth pages
  (Login/Register). All API paths are relative (`/api/...`); the dev proxy is in
  `vite.config.mjs`.
- **Design system:** `design/` at the repository root is the source of truth. Read
  `design/README.md` (voice, vocabulary, colour, type, patterns) before touching any UI.
  New styles use the tokens in `design/tokens.css` only: no raw hex, no `!important`.
- **Current state:** the app still runs the old "Workshop" theme (`public/spoolio_theme_1.css`
  plus the global stylesheets in `src/styles/`, imported by `index.jsx`). The redesign
  replaces it in phases: the token foundation, the Daylight and Reading lamp themes, and
  self-hosted Literata, IBM Plex Sans and IBM Plex Mono first, then each screen rebuilt on
  `src/components/library/`. Don't extend the Workshop theme; if a change can't wait, keep
  it minimal.
- **Dashboard.jsx** is a compact container. Data, mutations, derived view state,
  controller state, forms, modals, reports and rendering live in focused hooks
  (`src/hooks/`) and `src/components/dashboard/`. Shared lookup data loads through
  `src/hooks/useMetadata.js`. Extend those modules rather than growing the container.
- **PWA/assets:** there is deliberately no offline service worker. Keep the web manifest
  accurate.
- **Accessibility:** `ConfirmDialog` traps focus, so reuse it for modals. `App.jsx` has the
  skip link and the aria-live region. Controls are at least 44px tall. Use `<button>`,
  never `<div onClick>`.
- Verify changes with `npm test` and `npm run build`.
