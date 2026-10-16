# Consistency Under Fire — frontend

Web UI for the CSSE433 project that measures how much NoSQL consistency choices
corrupt market-data signals. It is a React 18 + TypeScript + Vite app using
React Router 6, TanStack Query, Mantine 7 and Plotly (`react-plotly.js/factory`
with `plotly.js-dist-min`).

The frontend talks to the FastAPI backend through one client interface
(`src/api/client.ts`). There are two implementations:

- `src/api/httpClient.ts` calls the real API at `VITE_API_URL`.
- `src/api/mockClient.ts` is an in-memory fake backend with seed data,
  simulated latency (150–400 ms), a simulated WebSocket and simulated
  database outages.

Components never know which one is active. The API contract lives in
[`../docs/api-contract.md`](../docs/api-contract.md) and mirrors
`src/api/types.ts` exactly.

## Run it

Requires Node 18+ (developed on Node 22).

```bash
cd frontend
npm install
```

### Mock mode (no backend needed)

```bash
VITE_USE_MOCK=true npm run dev     # or: npm run dev:mock
```

Open http://localhost:5173. A purple **Dev** button in the bottom-right corner
opens the developer panel (mock mode only). Use it to:

- take Cassandra, MongoDB and Redis up or down (rehearse the outage demo),
- take one Cassandra node (`cass3`) down while the cluster stays up,
- make every API call fail with a 500 (to see the error states),
- reset the seed data, or clear all data (to see the empty states).

Turning a store down changes `/health`, the "served from …" badges, write
results (that store becomes pending) and feature behavior. When it comes
back, its pending writes drain over about 5 seconds and a green
"… is back and fully synced." toast appears.

Mock state lives in browser memory. **Reloading the page resets everything**,
including the dev-panel switches. Navigate inside the app during a demo
rehearsal.

### Against the real API

```bash
cp .env.example .env.local    # then edit it
# VITE_USE_MOCK=false
# VITE_API_URL=http://localhost:8000
npm run dev
```

The backend must:

- serve every endpoint under `/api` and the live socket at `/ws/runs/{id}/live`,
- allow CORS from the dev server origin and expose the `X-Served-By` header
  (`Access-Control-Expose-Headers: X-Served-By`).

### Build and lint

```bash
npm run build   # tsc -b && vite build
npm run lint    # eslint
```

## What's where

```
src/
  api/            types.ts (contract types), client.ts (interface + ApiError),
                  httpClient.ts, mockClient.ts, ws.ts, index.ts (picks the client)
  api/mock/       seed.ts, generators.ts (truth/readings/report model),
                  server.ts (store state, replication, pending drain, run scheduler)
  components/     layout/ (AppLayout, StatusBar, OutageBanner, HealthWatcher, DevPanel),
                  charts/ (FragilityHeatmap, MetricVsDelayChart, ReadingsChart,
                  StalenessHistogram), Annotations, LiveMonitor, states, badges
  hooks/          useHealth, useLiveRun, useWriteMutation, queries, …
  lib/            formatting, colors, grid expansion, metrics, toasts
  pages/          Dashboard, Datasets, Signals, Experiments, ExperimentDesigner,
                  ExperimentDetail, RunDetail, Queue, Audit
```

## Behavior notes

- **Outages.** The top bar polls `GET /health` every 2 s. When `mode` is not
  `normal`, a banner explains what is affected. When a store changes state,
  every query is refetched so badges and fallbacks update. Readings charts
  show the Cassandra message when Cassandra is down. The live monitor falls
  back to polling `GET /runs/{id}` every 5 s when Redis is down. Queued runs
  show "waiting for Cassandra".
- **Write toasts.** Every create/update/delete uses `useWriteMutation`:
  - green "Saved." when the write is committed,
  - amber "Saved. Waiting to sync to …" when some stores are pending,
  - red with a Retry button when the request fails. Retry is offered only
    for network errors and 5xx responses.
- **Colors.** Latest-value signals are blue (`#2a78d6`) and running-total
  signals are orange (`#eb6834`) everywhere. This is a colorblind-safe pair.
  Truth is always a dashed neutral gray. Green, amber and red are used only
  for status. The heatmap uses a single-hue sequential blue ramp.
- **Live monitor.** Messages are buffered and flushed at most 5× per second.
  Each series keeps at most 600 points (about 60 s at 10 readings/s). If the
  socket drops, it reconnects with exponential backoff (1 s → 15 s).
- **Never blank.** Every page has loading skeletons, an empty state with a
  primary action, and an error state with Retry. A route-level error
  boundary catches render errors.

## Assumptions

Where the spec was ambiguous, I chose the simplest reasonable option:

1. **Launch response.** `POST /experiments/{id}/launch` returns
   `{ run_ids, write }`, not just `{ run_ids }`, so the UI can show the usual
   write toast. Relaunching an experiment whose runs have all finished adds
   a new set of runs. Relaunching while runs are active returns
   `409 already_running`.
2. **Cancel response.** `POST /runs/{id}/cancel` returns `WriteResponse<Run>`.
3. **Error bodies.** Error bodies are
   `{ reason, message, used_by? }`. FastAPI's `{"detail": ...}` wrapper is
   unwrapped automatically. Deleting a signal that is in use returns
   `409 in_use` with `used_by`, and the message reads "Used by N experiments: …".
4. **`avg_error` / `max_error` are normalized** (`|value − truth|` divided by
   the signal's typical magnitude, unitless), so signals with different units
   can share one heatmap.
5. **Seed datasets.** There are 12 seed datasets, not 6: BTCUSDT and ETHUSDT,
   trades and quotes, 2026-08-01..03, one dataset per day as the import rules
   describe.
6. **Dates.** Experiment `dates` and dataset days are inclusive `YYYY-MM-DD`
   values in UTC. All times in the UI are shown in UTC.
7. **Which days can be picked.** A day is available in the designer only when
   every selected symbol has `ready` datasets for every input kind its
   selected signals need. If no signals are selected yet, both trades and
   quotes are required.
8. **`run_count`** is the number of runs actually created (0 for a draft). The
   designer shows the planned grid size separately.
9. **Replay time estimate** = (days × 24 h ÷ replay speed) × number of runs.
   Runs execute one at a time.
10. **Annotation author** is a free-text name, remembered in localStorage. There
    is no authentication.
11. **Audit repair** returns a fresh `AuditResult`, not a write response, so the
    toast reports how many records still differ. Stores that are down show as
    "unreachable" in the audit table. A record's status is computed only over
    the stores that can be reached.
12. **Metric vs delay chart.** Runs that share a consistency level and delay but
    differ in other settings (loss, skew, outage) are averaged into one point.
    The chart is faceted by consistency, with a selector to show one level.
13. **Log scale by default** for the heatmap colors and the line chart y-axis,
    because errors span several orders of magnitude. A toggle switches to
    linear.
14. **Mock behavior when Cassandra goes down.** The running run pauses and
    becomes `waiting_for_cassandra` at the same progress, together with all
    queued runs. They resume automatically when Cassandra returns. The real
    backend may handle this differently. The UI only relies on the statuses.
15. **All databases down (mock).** Writes are still accepted with every store
    pending, which simulates a local outbox. Reads come from the in-memory
    snapshot, and `X-Served-By` is `snapshot`.
16. **`X-Served-By` fallback order** in the mock is MongoDB → Cassandra →
    Redis → snapshot. Readings are always served by Cassandra.
17. **Fault windows** (`GET /runs/{id}/faults`) are still available while
    Cassandra is down. Only readings and the run readings CSV return 503.
18. **CSV export** downloads through `fetch` + Blob, so errors can be shown as
    toasts instead of a broken download.
19. **Live small multiples** show one symbol at a time, with a symbol switcher
    when the experiment has several. Up to 8 charts are visible, and the rest
    scroll.
20. **Polling intervals.**
    - health and queue: every 2 s
    - datasets: every 3 s while an import is in progress
    - runs and experiments: every 3–5 s while active
    - run detail: every 5 s when Redis is down, every 10 s otherwise
21. **Imports in the mock** fail for days that have not finished yet, to
    demonstrate the `failed` status. At most 31 days can be imported at once.
