// Request/response types for the Consistency Under Fire API.
// This file is the single source of truth on the frontend and must stay in
// sync with docs/api-contract.md.

export type ISODateTime = string; // ISO 8601, e.g. "2026-08-01T13:45:00.000Z"
export type ISODate = string; // "YYYY-MM-DD"

// ---------------------------------------------------------------------------
// Common metadata
// ---------------------------------------------------------------------------

/** Value of the `X-Served-By` response header on every GET. */
export type ServedBy = 'mongodb' | 'cassandra' | 'redis' | 'snapshot';

export type StoreName = 'mongodb' | 'cassandra' | 'redis';
export const STORE_NAMES: StoreName[] = ['cassandra', 'mongodb', 'redis'];

export interface WriteInfo {
  status: 'committed' | 'pending';
  stores_written: StoreName[];
  stores_pending: StoreName[];
}

/** Body returned by every POST/PUT/DELETE on a user record. */
export interface WriteResponse<T> {
  record: T | null;
  write: WriteInfo;
}

/** Error body returned with every non-2xx status. */
export interface ApiErrorBody {
  reason: string; // machine-readable, e.g. "not_found", "in_use", "builtin", "cassandra_down", "validation"
  message: string; // human-readable
  used_by?: { id: string; name: string }[]; // present on 409 "in_use"
}

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------

export type SignalType = 'latest-value' | 'running-total';
export type SignalInputKind = 'trades' | 'quotes';

export interface Signal {
  id: string;
  name: string;
  type: SignalType;
  inputs: SignalInputKind[];
  window_ms: number;
  params: Record<string, number | string>;
  description: string;
  builtin: boolean;
  version: number;
  updated_at: ISODateTime;
}

/** Body for POST /signals and PUT /signals/{id}. */
export interface SignalInput {
  name: string;
  type: SignalType;
  inputs: SignalInputKind[];
  window_ms: number;
  params: Record<string, number | string>;
  description: string;
  /** PUT only: the version the client edited (optimistic concurrency, optional). */
  version?: number;
}

export type MarketSymbol = 'BTCUSDT' | 'ETHUSDT' | 'SOLUSDT';
export const SYMBOLS: MarketSymbol[] = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
export type DatasetStatus = 'downloading' | 'verifying' | 'ready' | 'failed';

export interface Dataset {
  id: string;
  symbol: MarketSymbol;
  kind: SignalInputKind;
  day: ISODate;
  status: DatasetStatus;
  row_count: number | null;
  size_bytes: number | null;
  checksum_ok: boolean | null;
  error: string | null;
  created_at: ISODateTime;
  version: number;
}

/** Body for POST /datasets/import. start/end are inclusive days. */
export interface DatasetImportInput {
  symbol: MarketSymbol;
  kind: SignalInputKind;
  start: ISODate;
  end: ISODate;
}

export interface DatasetImportResponse {
  records: Dataset[];
  write: WriteInfo;
}

export type Consistency = 'ONE' | 'QUORUM' | 'ALL';
export const CONSISTENCY_LEVELS: Consistency[] = ['ONE', 'QUORUM', 'ALL'];
export type NodeOutage = 'none' | 'one_node_down';
export type ExperimentStatus = 'draft' | 'queued' | 'running' | 'done' | 'failed';

export interface ExperimentParams {
  consistency: Consistency[];
  delay_ms: number[];
  packet_loss_pct: number[];
  clock_skew_ms: number[];
  node_outage: NodeOutage[];
}

export interface Experiment {
  id: string;
  name: string;
  symbols: MarketSymbol[];
  dates: { start: ISODate; end: ISODate }; // inclusive days
  signal_ids: string[];
  params: ExperimentParams;
  replay_speed: number;
  status: ExperimentStatus;
  tags: string[];
  notes: string;
  run_count: number; // number of runs created by launches (0 for a draft)
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/** Body for POST /experiments and PUT /experiments/{id}. */
export interface ExperimentInput {
  name: string;
  symbols: MarketSymbol[];
  dates: { start: ISODate; end: ISODate };
  signal_ids: string[];
  params: ExperimentParams;
  replay_speed: number;
  tags: string[];
  notes: string;
  /** PUT only: the version the client edited (optimistic concurrency, optional). */
  version?: number;
}

export interface ExperimentFilters {
  status?: ExperimentStatus;
  tag?: string;
  q?: string;
}

export interface LaunchResponse {
  run_ids: string[];
  write: WriteInfo;
}

export interface RunConfig {
  consistency: Consistency;
  delay_ms: number;
  packet_loss_pct: number;
  clock_skew_ms: number;
  node_outage: NodeOutage;
}

export type RunStatus = 'queued' | 'waiting_for_cassandra' | 'running' | 'done' | 'failed' | 'cancelled';

export interface SignalReport {
  avg_error: number; // mean |value - truth| normalised by the signal's typical magnitude (unitless)
  max_error: number; // max of the same quantity
  wrong_call_rate: number; // fraction 0..1
  staleness_p50_ms: number;
  staleness_p99_ms: number;
  latency_p50_ms: number;
  latency_p99_ms: number;
  readings_count: number;
}

export interface RunInput {
  experiment_id: string,
  config: RunConfig,
  queue_position: number | null,
  progress: { pct: number; replayed_until: ISODateTime | null };
  error: string | null,
  report: Record<string, SignalReport> | null; // keyed by signal_id
  version: number;
}

export interface RunCancel {
  status: RunStatus
}

export interface Run {
  id: string;
  experiment_id: string;
  config: RunConfig;
  status: RunStatus;
  queue_position: number | null;
  progress: { pct: number; replayed_until: ISODateTime | null };
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  error: string | null;
  report: Record<string, SignalReport> | null; // keyed by signal_id
  version: number;
}

export interface ReadingPoint {
  t: ISODateTime;
  value: number;
  truth: number;
  staleness_ms: number;
  latency_ms: number;
}

export interface ReadingsQuery {
  signal_id: string;
  symbol: string;
  from?: ISODateTime;
  to?: ISODateTime;
  max_points?: number; // default 2000
}

export interface ReadingsResponse {
  points: ReadingPoint[];
}

export type FaultKind = 'delay' | 'packet_loss' | 'clock_skew' | 'node_down';

export interface FaultWindow {
  start: ISODateTime;
  end: ISODateTime;
  kind: FaultKind;
  target: string; // node name, e.g. "cass2"
  value: number | null; // ms for delay/clock_skew, % for packet_loss, null for node_down
}

export interface QueueState {
  running: Run | null;
  waiting: Run[];
  blocked_reason: 'cassandra_down' | null;
}

export type AnnotationTarget = 'experiment' | 'run';

export interface Annotation {
  id: string;
  target_type: AnnotationTarget;
  target_id: string;
  text: string;
  tags: string[];
  author: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
  version: number;
}

/** Body for POST /annotations. */
export interface AnnotationInput {
  target_type: AnnotationTarget;
  target_id: string;
  text: string;
  tags: string[];
  author: string;
}

/** Body for PUT /annotations/{id}. */
export interface AnnotationUpdate {
  text: string;
  tags: string[];
  version?: number;
}

// ---------------------------------------------------------------------------
// Health & audit
// ---------------------------------------------------------------------------

export type HealthMode = 'normal' | 'degraded' | 'offline';

export interface CassandraNode {
  name: string;
  status: 'UN' | 'DN';
}

export interface StoreHealth {
  up: boolean;
  latency_ms: number | null;
}

export interface Health {
  checked_at: ISODateTime;
  mode: HealthMode;
  stores: {
    cassandra: StoreHealth & { nodes: CassandraNode[] };
    mongodb: StoreHealth;
    redis: StoreHealth;
  };
  pending_writes: Record<StoreName, number>;
}

export type RecordType = 'signal' | 'experiment' | 'run' | 'annotation' | 'dataset';

export interface AuditRecord {
  type: RecordType;
  id: string;
  name: string;
  versions: Record<StoreName, number | null>;
  status: 'match' | 'mismatch' | 'missing';
}

export interface AuditResult {
  checked_at: ISODateTime;
  summary: { total: number; matching: number; mismatched: number; missing: number };
  records: AuditRecord[];
}

/** Body for POST /audit/repair: either one record or everything. */
export type AuditRepairInput = { type: RecordType; id: string } | { all: true };

// ---------------------------------------------------------------------------
// Live run stream (WS /ws/runs/{id}/live)
// ---------------------------------------------------------------------------

export interface ActiveFault {
  kind: FaultKind;
  target: string;
  value: number | null;
}

export type LiveMessage =
  | {
      type: 'reading';
      signal_id: string;
      symbol: string;
      t: ISODateTime;
      value: number;
      truth: number;
      staleness_ms: number;
      latency_ms: number;
    }
  | { type: 'progress'; pct: number; replayed_until: ISODateTime | null }
  | { type: 'faults'; active: ActiveFault[] }
  | { type: 'status'; status: RunStatus };
