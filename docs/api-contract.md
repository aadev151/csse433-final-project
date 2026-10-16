# Consistency Under Fire — API contract

This is the contract the frontend (`frontend/`) is built against. It mirrors
`frontend/src/api/types.ts` exactly; if you change one, change the other.

- Base URL: `http://localhost:8000` (frontend env `VITE_API_URL`).
- Every HTTP endpoint is prefixed with `/api`. The WebSocket lives at `/ws/...` (no `/api`).
- JSON everywhere (`Content-Type: application/json`), except the CSV exports.
- Timestamps are ISO 8601 strings (`2026-08-01T13:45:00.000Z`). Days are `YYYY-MM-DD`.
- IDs are strings.

## Conventions

### `X-Served-By` header (every GET)

Every `GET` response carries `X-Served-By: mongodb | cassandra | redis | snapshot`,
naming the store that answered. MongoDB is the source of truth; when it is down
the backend answers from Cassandra, then Redis, then a local snapshot. The UI
shows this as a "served from …" badge.

The CORS config must expose it: `Access-Control-Expose-Headers: X-Served-By`.

### Write responses (every POST / PUT / DELETE on a user record)

User records = signals, experiments, runs, annotations, datasets.

```ts
interface WriteInfo {
  status: "committed" | "pending";
  stores_written: ("mongodb" | "cassandra" | "redis")[];
  stores_pending: ("mongodb" | "cassandra" | "redis")[];
}

interface WriteResponse<T> {
  record: T | null;   // the record after the write; null for DELETE
  write: WriteInfo;
}
```

`status` is `"committed"` only when `stores_pending` is empty. A write whose
stores are down is still accepted (`200`) with those stores in `stores_pending`;
the backend syncs them later and reports the backlog in `GET /health`
(`pending_writes`).

### Errors

Every non-2xx response has this body:

```ts
interface ApiErrorBody {
  reason: string;   // machine readable: "not_found" | "validation" | "in_use" | "builtin" | "cassandra_down" | ...
  message: string;  // human readable, shown to the user
  used_by?: { id: string; name: string }[];  // only on 409 "in_use"
}
```

FastAPI's default `{"detail": {...}}` wrapping is also accepted by the frontend
(it unwraps `detail`), and a plain string `detail` becomes `message`.

| Status | When |
|---|---|
| 400 / 422 | invalid body or query (`reason: "validation"`) |
| 404 | unknown id (`reason: "not_found"`) |
| 409 | conflict: deleting a built-in signal (`builtin`), deleting a signal used by experiments (`in_use` + `used_by`), launching an experiment that is already running (`already_running`), version mismatch on PUT (`version_conflict`) |
| 503 | a required store is down (`cassandra_down` on readings) |

## Types

```ts
type ServedBy = "mongodb" | "cassandra" | "redis" | "snapshot";
type StoreName = "mongodb" | "cassandra" | "redis";
```

### Signal

```ts
interface Signal {
  id: string;
  name: string;
  type: "latest-value" | "running-total";
  inputs: ("trades" | "quotes")[];
  window_ms: number;
  params: Record<string, number | string>;
  description: string;
  builtin: boolean;
  version: number;
  updated_at: string;
}

// POST /signals, PUT /signals/{id}
interface SignalInput {
  name: string;
  type: "latest-value" | "running-total";
  inputs: ("trades" | "quotes")[];
  window_ms: number;
  params: Record<string, number | string>;
  description: string;
  version?: number;   // PUT only: version the client edited (optional optimistic concurrency)
}
```

### Dataset

```ts
interface Dataset {
  id: string;
  symbol: "BTCUSDT" | "ETHUSDT" | "SOLUSDT";
  kind: "trades" | "quotes";
  day: string;                 // YYYY-MM-DD
  status: "downloading" | "verifying" | "ready" | "failed";
  row_count: number | null;
  size_bytes: number | null;
  checksum_ok: boolean | null;
  error: string | null;
  created_at: string;
  version: number;
}

// POST /datasets/import  (start/end inclusive)
interface DatasetImportInput {
  symbol: "BTCUSDT" | "ETHUSDT" | "SOLUSDT";
  kind: "trades" | "quotes";
  start: string;  // YYYY-MM-DD
  end: string;    // YYYY-MM-DD
}

interface DatasetImportResponse {
  records: Dataset[];   // one per day
  write: WriteInfo;
}
```

### Experiment

```ts
interface ExperimentParams {
  consistency: ("ONE" | "QUORUM" | "ALL")[];
  delay_ms: number[];
  packet_loss_pct: number[];
  clock_skew_ms: number[];
  node_outage: ("none" | "one_node_down")[];
}

interface Experiment {
  id: string;
  name: string;
  symbols: ("BTCUSDT" | "ETHUSDT" | "SOLUSDT")[];
  dates: { start: string; end: string };   // YYYY-MM-DD, inclusive
  signal_ids: string[];
  params: ExperimentParams;
  replay_speed: number;                    // 1, 5, 10, 50
  status: "draft" | "queued" | "running" | "done" | "failed";
  tags: string[];
  notes: string;
  run_count: number;                       // runs created by launches; 0 for a draft
  version: number;
  created_at: string;
  updated_at: string;
}

// POST /experiments, PUT /experiments/{id}
interface ExperimentInput {
  name: string;
  symbols: ("BTCUSDT" | "ETHUSDT" | "SOLUSDT")[];
  dates: { start: string; end: string };
  signal_ids: string[];
  params: ExperimentParams;
  replay_speed: number;
  tags: string[];
  notes: string;
  version?: number;   // PUT only
}

interface LaunchResponse {
  run_ids: string[];
  write: WriteInfo;
}
```

Replication factor is fixed at 3 and is not a setting.

### Run

```ts
interface RunConfig {
  consistency: "ONE" | "QUORUM" | "ALL";
  delay_ms: number;
  packet_loss_pct: number;
  clock_skew_ms: number;
  node_outage: "none" | "one_node_down";
}

interface SignalReport {
  avg_error: number;        // mean |value - truth| normalised by the signal's typical magnitude (unitless)
  max_error: number;        // max of the same quantity
  wrong_call_rate: number;  // 0..1
  staleness_p50_ms: number;
  staleness_p99_ms: number;
  latency_p50_ms: number;
  latency_p99_ms: number;
  readings_count: number;
}

interface Run {
  id: string;
  experiment_id: string;
  config: RunConfig;
  status: "queued" | "waiting_for_cassandra" | "running" | "done" | "failed" | "cancelled";
  queue_position: number | null;   // 1-based while waiting, else null
  progress: { pct: number; replayed_until: string | null };   // pct 0..100
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  report: Record<string, SignalReport> | null;   // keyed by signal_id; null until done
  version: number;
}

interface ReadingPoint {
  t: string;
  value: number;          // signal value computed from what Cassandra returned
  truth: number;          // ground truth from the clean file
  staleness_ms: number;
  latency_ms: number;
}

interface ReadingsResponse { points: ReadingPoint[] }

interface FaultWindow {
  start: string;
  end: string;
  kind: "delay" | "packet_loss" | "clock_skew" | "node_down";
  target: string;          // node, e.g. "cass2"
  value: number | null;    // ms for delay / clock_skew, % for packet_loss, null for node_down
}

interface QueueState {
  running: Run | null;
  waiting: Run[];          // in queue order
  blocked_reason: "cassandra_down" | null;
}
```

### Annotation

```ts
interface Annotation {
  id: string;
  target_type: "experiment" | "run";
  target_id: string;
  text: string;
  tags: string[];
  author: string;
  created_at: string;
  updated_at: string;
  version: number;
}

// POST /annotations
interface AnnotationInput {
  target_type: "experiment" | "run";
  target_id: string;
  text: string;
  tags: string[];
  author: string;   // free-text name; there is no auth
}

// PUT /annotations/{id}
interface AnnotationUpdate {
  text: string;
  tags: string[];
  version?: number;
}
```

### Health

```ts
interface Health {
  checked_at: string;
  mode: "normal" | "degraded" | "offline";   // offline = all three stores down
  stores: {
    cassandra: { up: boolean; latency_ms: number | null; nodes: { name: string; status: "UN" | "DN" }[] };
    mongodb:   { up: boolean; latency_ms: number | null };
    redis:     { up: boolean; latency_ms: number | null };
  };
  pending_writes: { cassandra: number; mongodb: number; redis: number };
}
```

### Audit

```ts
interface AuditResult {
  checked_at: string;
  summary: { total: number; matching: number; mismatched: number; missing: number };
  records: {
    type: "signal" | "experiment" | "run" | "annotation" | "dataset";
    id: string;
    name: string;
    versions: { mongodb: number | null; cassandra: number | null; redis: number | null };  // null = absent (or store unreachable)
    status: "match" | "mismatch" | "missing";
  }[];
}

// POST /audit/repair
type AuditRepairInput = { type: "signal" | "experiment" | "run" | "annotation" | "dataset"; id: string } | { all: true };
```

## Endpoints

| Method | Path | Request | Response (200) | Errors |
|---|---|---|---|---|
| GET | `/api/health` | – | `Health` | – |
| GET | `/api/datasets` | – | `Dataset[]` | – |
| POST | `/api/datasets/import` | `DatasetImportInput` | `DatasetImportResponse` | 422 |
| DELETE | `/api/datasets/{id}` | – | `WriteResponse<null>` | 404 |
| GET | `/api/signals` | – | `Signal[]` | – |
| GET | `/api/signals/{id}` | – | `Signal` | 404 |
| POST | `/api/signals` | `SignalInput` | `WriteResponse<Signal>` | 422 |
| PUT | `/api/signals/{id}` | `SignalInput` | `WriteResponse<Signal>` | 404, 409 `builtin` / `version_conflict`, 422 |
| DELETE | `/api/signals/{id}` | – | `WriteResponse<null>` | 404, 409 `builtin`, 409 `in_use` (+`used_by`) |
| GET | `/api/experiments?status=&tag=&q=` | query: `status` (ExperimentStatus), `tag`, `q` (name substring, case-insensitive); all optional | `Experiment[]` | – |
| GET | `/api/experiments/{id}` | – | `Experiment` | 404 |
| POST | `/api/experiments` | `ExperimentInput` | `WriteResponse<Experiment>` (status `draft`) | 422 |
| PUT | `/api/experiments/{id}` | `ExperimentInput` | `WriteResponse<Experiment>` | 404, 409, 422 |
| DELETE | `/api/experiments/{id}` | – | `WriteResponse<null>` (also deletes its runs) | 404 |
| POST | `/api/experiments/{id}/clone` | – | `WriteResponse<Experiment>` (new draft, name `"<name> (copy)"`) | 404 |
| POST | `/api/experiments/{id}/launch` | – | `LaunchResponse` (grid expanded into runs, all queued) | 404, 409 `already_running` |
| GET | `/api/experiments/{id}/runs` | – | `Run[]` | 404 |
| GET | `/api/experiments/{id}/export.csv` | – | `text/csv` (one row per run × signal with config + report) | 404 |
| GET | `/api/runs/{id}` | – | `Run` | 404 |
| POST | `/api/runs/{id}/cancel` | – | `WriteResponse<Run>` (status `cancelled`) | 404, 409 if already finished |
| GET | `/api/runs/{id}/readings?signal_id=&symbol=&from=&to=&max_points=2000` | `signal_id`, `symbol` required; `from`/`to` ISO optional; `max_points` default 2000 | `ReadingsResponse` (downsampled to ≤ `max_points`, ascending `t`) | 404, 503 `{ "reason": "cassandra_down" }` |
| GET | `/api/runs/{id}/faults` | – | `FaultWindow[]` | 404 |
| GET | `/api/runs/{id}/export.csv` | – | `text/csv` (readings) | 404, 503 `cassandra_down` |
| GET | `/api/queue` | – | `QueueState` | – |
| GET | `/api/annotations?target_type=&target_id=` | both required | `Annotation[]` (newest first) | 422 |
| POST | `/api/annotations` | `AnnotationInput` | `WriteResponse<Annotation>` | 422 |
| PUT | `/api/annotations/{id}` | `AnnotationUpdate` | `WriteResponse<Annotation>` | 404, 409 |
| DELETE | `/api/annotations/{id}` | – | `WriteResponse<null>` | 404 |
| GET | `/api/audit` | – | `AuditResult` | – |
| POST | `/api/audit/repair` | `AuditRepairInput` | `AuditResult` (fresh audit after repair) | 404 |

All GETs carry `X-Served-By`. The frontend polls `/api/health` every 2 s,
`/api/queue` every 2 s, the dataset list every 3 s while an import is in
progress, and a run every 5 s when the live socket is unavailable.

## WebSocket: `WS /ws/runs/{id}/live`

Bridged from Redis pub/sub. If Redis is down the server refuses the connection
(close the socket immediately); the frontend then polls `GET /api/runs/{id}`.

Server → client messages (JSON text frames):

```ts
type LiveMessage =
  | { type: "reading"; signal_id: string; symbol: string; t: string; value: number; truth: number; staleness_ms: number; latency_ms: number }
  | { type: "progress"; pct: number; replayed_until: string | null }
  | { type: "faults"; active: { kind: "delay" | "packet_loss" | "clock_skew" | "node_down"; target: string; value: number | null }[] }
  | { type: "status"; status: "queued" | "waiting_for_cassandra" | "running" | "done" | "failed" | "cancelled" };
```

Expected rates: `reading` ~10/s per signal and symbol; `progress` ~1/s;
`faults` whenever the active set changes (sending it ~1/s is fine); `status`
on every change. The client sends nothing.
