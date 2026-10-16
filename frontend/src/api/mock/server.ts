import type {
  AuditRecord,
  AuditResult,
  Dataset,
  Experiment,
  Health,
  RecordType,
  Run,
  ServedBy,
  Signal,
  StoreName,
  WriteInfo,
} from '../types';
import { STORE_NAMES } from '../types';
import { dayCount } from '../../lib/grid';
import { reportFor } from './generators';
import { hash01, hashString } from './random';
import { buildSeed, type MockData } from './seed';

/**
 * In-memory fake backend state: the records, the simulated up/down state of
 * the three stores, per-store replica versions (for the audit), the pending
 * write backlog, and a 1 s ticker that advances runs and dataset imports.
 */

type Versions = Record<StoreName, number | null>;

interface PendingWrite {
  store: StoreName;
  key: string;
  version: number | null; // null = delete
}

export interface DevState {
  stores: Record<StoreName, boolean>;
  nodeDown: boolean; // take one Cassandra node (cass3) down while the cluster stays up
  failRequests: boolean; // make every API call except /health fail with 500
}

const NODE_NAMES = ['cass1', 'cass2', 'cass3'];
const RUN_PCT_PER_SEC = 0.6; // ~2.8 minutes per run

class MockServer {
  data: MockData = buildSeed();
  dev: DevState = { stores: { cassandra: true, mongodb: true, redis: true }, nodeDown: false, failRequests: false };
  private replicas = new Map<string, Versions>();
  private names = new Map<string, string>();
  private pending: PendingWrite[] = [];
  private drainPerTick: Record<StoreName, number> = { cassandra: 1, mongodb: 1, redis: 1 };
  private listeners = new Set<() => void>();
  private queueSeq = new Map<string, number>();
  private nextSeq = 1;
  private datasetTicks = new Map<string, number>();
  private idCounter = 1;

  constructor() {
    this.resetReplicas();
    setInterval(() => this.tick(), 1000);
    setInterval(() => this.drain(), 250);
  }

  // ---------------------------------------------------------------- dev panel

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    this.listeners.forEach((fn) => fn());
  }

  setStore(store: StoreName, up: boolean) {
    if (this.dev.stores[store] === up) return;
    this.dev = { ...this.dev, stores: { ...this.dev.stores, [store]: up } };
    if (up) {
      // drain the backlog for this store over ~5 seconds (20 ticks of 250 ms)
      const n = this.pending.filter((p) => p.store === store).length;
      this.drainPerTick[store] = Math.max(1, Math.ceil(n / 20));
    }
    this.emit();
  }

  setNodeDown(down: boolean) {
    this.dev = { ...this.dev, nodeDown: down };
    this.emit();
  }

  setFailRequests(fail: boolean) {
    this.dev = { ...this.dev, failRequests: fail };
    this.emit();
  }

  reset(empty = false) {
    this.data = empty ? { signals: [], datasets: [], experiments: [], runs: [], annotations: [] } : buildSeed();
    this.pending = [];
    this.queueSeq.clear();
    this.datasetTicks.clear();
    this.resetReplicas();
    this.emit();
  }

  get pendingCounts(): Record<StoreName, number> {
    const c: Record<StoreName, number> = { cassandra: 0, mongodb: 0, redis: 0 };
    for (const p of this.pending) c[p.store]++;
    return c;
  }

  // ---------------------------------------------------------------- store state

  isUp(store: StoreName): boolean {
    return this.dev.stores[store];
  }

  servedBy(): ServedBy {
    if (this.isUp('mongodb')) return 'mongodb';
    if (this.isUp('cassandra')) return 'cassandra';
    if (this.isUp('redis')) return 'redis';
    return 'snapshot';
  }

  health(): Health {
    const up = this.dev.stores;
    const nUp = STORE_NAMES.filter((s) => up[s]).length;
    const lat = (s: StoreName, base: number) => (up[s] ? Math.round((base + Math.random() * base) * 10) / 10 : null);
    return {
      checked_at: new Date().toISOString(),
      mode: nUp === 3 ? 'normal' : nUp === 0 ? 'offline' : 'degraded',
      stores: {
        cassandra: {
          up: up.cassandra,
          latency_ms: lat('cassandra', this.dev.nodeDown ? 4 : 1.8),
          nodes: NODE_NAMES.map((name) => ({
            name,
            status: up.cassandra && !(this.dev.nodeDown && name === 'cass3') ? 'UN' : 'DN',
          })),
        },
        mongodb: { up: up.mongodb, latency_ms: lat('mongodb', 1.2) },
        redis: { up: up.redis, latency_ms: lat('redis', 0.4) },
      },
      pending_writes: this.pendingCounts,
    };
  }

  // ---------------------------------------------------------------- replication

  newId(prefix: string): string {
    return `${prefix}_${Date.now().toString(36)}${(this.idCounter++).toString(36)}`;
  }

  private resetReplicas() {
    this.replicas.clear();
    this.names.clear();
    const d = this.data;
    const all: [RecordType, { id: string; version: number }, string][] = [
      ...d.signals.map((r) => ['signal', r, r.name] as [RecordType, Signal, string]),
      ...d.datasets.map((r) => ['dataset', r, `${r.symbol} ${r.kind} ${r.day}`] as [RecordType, Dataset, string]),
      ...d.experiments.map((r) => ['experiment', r, r.name] as [RecordType, Experiment, string]),
      ...d.runs.map((r) => ['run', r, r.id] as [RecordType, Run, string]),
      ...d.annotations.map((r) => ['annotation', r, r.text.slice(0, 40)] as [RecordType, { id: string; version: number }, string]),
    ];
    for (const [type, rec, name] of all) {
      const key = `${type}:${rec.id}`;
      this.replicas.set(key, { mongodb: rec.version, cassandra: rec.version, redis: rec.version });
      this.names.set(key, name);
    }
    // Seeded drift so the audit page has something to show and repair.
    if (this.replicas.has('signal:sig_vwap_60s')) this.replicas.set('signal:sig_vwap_60s', { mongodb: 2, cassandra: 2, redis: 1 });
    if (this.replicas.has('annotation:ann_2')) this.replicas.set('annotation:ann_2', { mongodb: 1, cassandra: null, redis: 1 });
  }

  /** Records a write to every store: applied where up, queued as pending where down. */
  write(type: RecordType, id: string, version: number | null, name?: string): WriteInfo {
    const key = `${type}:${id}`;
    if (name) this.names.set(key, name);
    const v = this.replicas.get(key) ?? { mongodb: null, cassandra: null, redis: null };
    const written: StoreName[] = [];
    const pending: StoreName[] = [];
    for (const s of STORE_NAMES) {
      if (this.isUp(s)) {
        v[s] = version;
        written.push(s);
        // a newer write supersedes anything still queued for this store
        this.pending = this.pending.filter((p) => !(p.store === s && p.key === key));
      } else {
        this.pending.push({ store: s, key, version });
        pending.push(s);
      }
    }
    this.setReplica(key, v);
    // writes that happen inside the mock (ticker) still need listeners to refresh
    this.emit();
    return { status: pending.length ? 'pending' : 'committed', stores_written: written, stores_pending: pending };
  }

  private setReplica(key: string, v: Versions) {
    if (v.mongodb === null && v.cassandra === null && v.redis === null) this.replicas.delete(key);
    else this.replicas.set(key, v);
  }

  private drain() {
    let changed = false;
    for (const s of STORE_NAMES) {
      if (!this.isUp(s)) continue;
      let budget = this.drainPerTick[s];
      for (let i = 0; i < this.pending.length && budget > 0; ) {
        const p = this.pending[i];
        if (p.store !== s) {
          i++;
          continue;
        }
        const v = this.replicas.get(p.key) ?? { mongodb: null, cassandra: null, redis: null };
        v[s] = p.version;
        this.setReplica(p.key, v);
        this.pending.splice(i, 1);
        budget--;
        changed = true;
      }
    }
    if (changed) this.emit();
  }

  audit(): AuditResult {
    const records: AuditRecord[] = [];
    for (const [key, v] of this.replicas) {
      const [type, ...rest] = key.split(':');
      const id = rest.join(':');
      const visible: Versions = {
        mongodb: this.isUp('mongodb') ? v.mongodb : null,
        cassandra: this.isUp('cassandra') ? v.cassandra : null,
        redis: this.isUp('redis') ? v.redis : null,
      };
      const reachable = STORE_NAMES.filter((s) => this.isUp(s)).map((s) => v[s]);
      let status: AuditRecord['status'] = 'match';
      if (reachable.some((x) => x === null)) status = 'missing';
      else if (new Set(reachable).size > 1) status = 'mismatch';
      records.push({ type: type as RecordType, id, name: this.names.get(key) ?? id, versions: visible, status });
    }
    const order = { mismatch: 0, missing: 1, match: 2 };
    records.sort((a, b) => order[a.status] - order[b.status] || a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
    return {
      checked_at: new Date().toISOString(),
      summary: {
        total: records.length,
        matching: records.filter((r) => r.status === 'match').length,
        mismatched: records.filter((r) => r.status === 'mismatch').length,
        missing: records.filter((r) => r.status === 'missing').length,
      },
      records,
    };
  }

  /** Copies the source-of-truth version (MongoDB, else the newest) to every reachable store. */
  repair(key?: string) {
    const keys = key ? [key] : [...this.replicas.keys()];
    for (const k of keys) {
      const v = this.replicas.get(k);
      if (!v) continue;
      const truth = this.isUp('mongodb') && v.mongodb !== null ? v.mongodb : Math.max(...STORE_NAMES.map((s) => v[s] ?? -1));
      for (const s of STORE_NAMES) {
        if (!this.isUp(s)) continue;
        v[s] = truth < 0 ? null : truth;
        this.pending = this.pending.filter((p) => !(p.store === s && p.key === k));
      }
      this.setReplica(k, v);
    }
    this.emit();
  }

  // ---------------------------------------------------------------- simulation

  enqueue(run: Run) {
    this.queueSeq.set(run.id, this.nextSeq++);
  }

  /** Runs waiting to execute, in queue order. */
  waitingRuns(): Run[] {
    const waiting = this.data.runs.filter((r) => r.status === 'queued' || r.status === 'waiting_for_cassandra');
    for (const r of waiting) if (!this.queueSeq.has(r.id)) this.enqueue(r);
    return waiting.sort((a, b) => (this.queueSeq.get(a.id) ?? 0) - (this.queueSeq.get(b.id) ?? 0));
  }

  experimentRange(e: Experiment): [number, number] {
    const start = Date.parse(`${e.dates.start}T00:00:00Z`);
    return [start, start + dayCount(e.dates.start, e.dates.end) * 86_400_000];
  }

  private touchRun(run: Run, patch: Partial<Run>) {
    Object.assign(run, patch, { version: run.version + 1 });
    this.write('run', run.id, run.version, run.id);
  }

  refreshExperimentStatus(expId: string) {
    const e = this.data.experiments.find((x) => x.id === expId);
    if (!e) return;
    const runs = this.data.runs.filter((r) => r.experiment_id === expId);
    let status: Experiment['status'] = e.status;
    if (runs.length === 0) status = 'draft';
    else if (runs.some((r) => r.status === 'running')) status = 'running';
    else if (runs.some((r) => r.status === 'queued' || r.status === 'waiting_for_cassandra')) status = 'queued';
    else if (runs.every((r) => r.status === 'failed' || r.status === 'cancelled')) status = 'failed';
    else status = 'done';
    if (status !== e.status) {
      e.status = status;
      e.version++;
      e.updated_at = new Date().toISOString();
      this.write('experiment', e.id, e.version, e.name);
    }
  }

  private tick() {
    const cassUp = this.isUp('cassandra');
    const now = new Date().toISOString();
    const touched = new Set<string>();

    // runs
    let running = this.data.runs.find((r) => r.status === 'running') ?? null;
    if (!cassUp) {
      if (running) {
        this.touchRun(running, { status: 'waiting_for_cassandra' });
        touched.add(running.experiment_id);
        // keep it at the front of the queue
        this.queueSeq.set(running.id, 0);
        running = null;
      }
      for (const r of this.data.runs)
        if (r.status === 'queued') {
          this.touchRun(r, { status: 'waiting_for_cassandra' });
          touched.add(r.experiment_id);
        }
    } else {
      for (const r of this.data.runs)
        if (r.status === 'waiting_for_cassandra') {
          this.touchRun(r, { status: 'queued' });
          touched.add(r.experiment_id);
        }
      if (!running) {
        const next = this.waitingRuns()[0];
        if (next) {
          this.touchRun(next, { status: 'running', started_at: next.started_at ?? now });
          running = next;
          touched.add(next.experiment_id);
        }
      }
      if (running) {
        const e = this.data.experiments.find((x) => x.id === running!.experiment_id);
        const pct = Math.min(100, running.progress.pct + RUN_PCT_PER_SEC);
        if (e) {
          const [a, b] = this.experimentRange(e);
          running.progress = { pct, replayed_until: new Date(a + (pct / 100) * (b - a)).toISOString() };
        }
        if (pct >= 100 && e) {
          const report: Run['report'] = {};
          for (const s of this.data.signals.filter((x) => e.signal_ids.includes(x.id)))
            report[s.id] = reportFor(running.id, s, running.config, 864_000 * dayCount(e.dates.start, e.dates.end) * e.symbols.length);
          this.touchRun(running, { status: 'done', finished_at: now, report });
          touched.add(running.experiment_id);
        }
      }
    }
    const waiting = this.waitingRuns();
    waiting.forEach((r, i) => (r.queue_position = i + 1));
    for (const r of this.data.runs) if (!waiting.includes(r)) r.queue_position = null;
    touched.forEach((id) => this.refreshExperimentStatus(id));

    // dataset imports: downloading (3 s) -> verifying (2 s) -> ready / failed
    for (const d of this.data.datasets) {
      if (d.status !== 'downloading' && d.status !== 'verifying') continue;
      const t = (this.datasetTicks.get(d.id) ?? 0) + 1;
      this.datasetTicks.set(d.id, t);
      if (d.status === 'downloading' && t >= 3) {
        if (Date.parse(`${d.day}T00:00:00Z`) + 86_400_000 > Date.now()) {
          Object.assign(d, { status: 'failed', error: 'No archive published for this day yet (404 from data.binance.vision).' });
        } else {
          d.status = 'verifying';
        }
        d.version++;
        this.write('dataset', d.id, d.version);
      } else if (d.status === 'verifying' && t >= 5) {
        const r = hash01(hashString(d.id), 2);
        const rows = Math.round((d.kind === 'trades' ? 1_800_000 : 6_000_000) * (0.8 + 0.4 * r));
        Object.assign(d, { status: 'ready', row_count: rows, size_bytes: rows * (d.kind === 'trades' ? 31 : 38), checksum_ok: true });
        d.version++;
        this.write('dataset', d.id, d.version);
      }
    }
  }
}

export const mockServer = new MockServer();
