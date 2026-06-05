# Synapse — Web UI

The control surface for Synapse. A React + TypeScript SPA (Vite) that implements the
`Synapse.html` design. It ships as a static bundle served by the **Cloud Backend host**
(same origin as the REST API — no CORS), and talks to **Supabase** directly for Auth,
Realtime, and the data API.

See [`docs/web-ui.md`](../docs/web-ui.md) for the product spec.

## Develop

```bash
cd synapse_web
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check (tsc) + production build → dist/
npm run preview  # serve the built bundle
```

The Cloud Backend serves the built bundle from `dist/`: point its `web_ui_dist`
setting at this folder's `dist/` (see `synapse_cloud/app.py` — the `StaticFiles` mount).

## Stack

| Concern         | Choice |
|-----------------|--------|
| Framework       | React 18 + TypeScript (Vite SPA) |
| Routing         | react-router-dom |
| Server state    | TanStack Query (`src/api/queries.ts`) |
| Client state    | Zustand (`src/store/ui.ts`) |
| Realtime / Auth | Supabase (`src/lib/supabase.ts`) |
| Styling         | Bespoke design system (`src/styles/`) + Tailwind tokens |
| Charts          | Recharts |
| Markdown editor | CodeMirror 6 (`@uiw/react-codemirror`) |

> The bespoke design system (`colors_and_type.css`, `effects.css`, `app.css`) is the
> styling contract and is kept **verbatim** from the design handoff. Tailwind is wired
> to the same tokens (`tailwind.config.js`) for anything new.

## Architecture

```
src/
  styles/        design-system CSS (verbatim) + Tailwind layers
  types.ts       typed domain models
  data/mock.ts   the busy-fleet mock data (typed)
  api/queries.ts TanStack hooks — the seam to real REST / Supabase
  lib/supabase.ts Supabase client (null until env configured → app runs on mock data)
  store/ui.ts    Zustand: toast, palette, wizard, tweaks, live approvals queue
  components/     Primitives (Icon/Button/Chip…), Common (PageHead/Modal/Toast…), Shell
  screens/        one file per screen; agent/ holds the detail shell + tabs/
  router.tsx      route table
design-reference/ the original design prototype (NOT compiled) — pixel reference
```

Data is mock-only for now; every screen reads it through the `src/api/queries.ts`
hooks so wiring real endpoints later is a local change.

## Conventions (for contributors filling screens)

- **Port the design from `design-reference/`** — recreate the matching `app/*.jsx`
  prototype using the existing `.db-*` classes in `src/styles/app.css`. Match the
  visual output; do not invent new styles when a `.db-*` class exists.
- Read data via the **hooks in `src/api/queries.ts`**; never import `src/data/mock`
  directly from a screen.
- Reuse **`components/Primitives.tsx`** (`Icon`, `Button`, `Chip`, `LogoMark`,
  `HatchCorners`, `Kicker`) and **`components/Common.tsx`** (`PageHead`, `MetricCard`,
  `Modal`, `ConfirmDialog`, `Toggle`, `Segmented`, `Sparkline`, `BarChart`,
  `HeartStrip`, `EmptyState`, `daemonName`, `AgentAvatar`, `Toast`).
- Cross-cutting interaction state (toasts, command palette, New Agent wizard, Tweaks
  panel, live HITL approvals) lives in **`src/store/ui.ts`**.
- **Own exactly your file.** Don't edit the shell, router, or another screen — new
  sub-component files are fine. `npm run build` must stay green.
