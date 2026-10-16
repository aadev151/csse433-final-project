import { ApiError, type ApiClient, type LiveConnection, type LiveHandlers, type Served } from './client';
import type {
  Annotation,
  Experiment,
  ExperimentInput,
  LiveMessage,
  ReadingPoint,
  Run,
  Signal,
  SignalInput,
  WriteResponse,
} from './types';
import { expandGrid, daysBetween } from '../lib/grid';
import { activeFaultsAt, faultWindowsFor, makeReadingModel, readingAt, readingsBetween } from './mock/generators';
import { randomBetween, sleep } from './mock/random';
import { mockServer as S } from './mock/server';

/** In-memory fake backend with simulated latency (150–400 ms) and store outages. */

const clone = <T>(x: T): T => structuredClone(x);

async function latency() {
  await sleep(randomBetween(150, 400));
  if (S.dev.failRequests) throw new ApiError(500, 'Simulated server error (developer panel: "Fail API requests").', { reason: 'internal', message: 'Simulated server error' });
}

async function served<T>(fn: () => T): Promise<Served<T>> {
  await latency();
  return { data: clone(fn()), servedBy: S.servedBy() };
}

function notFound(what: string): never {
  throw new ApiError(404, `${what} not found.`, { reason: 'not_found', message: `${what} not found.` });
}

function findOr404<T extends { id: string }>(list: T[], id: string, what: string): T {
  return list.find((x) => x.id === id) ?? notFound(what);
}

function validationError(message: string): never {
  throw new ApiError(422, message, { reason: 'validation', message });
}

function result<T>(record: T | null, write: WriteResponse<T>['write']): WriteResponse<T> {
  return { record: record ? clone(record) : null, write };
}

function now() {
  return new Date().toISOString();
}

function validateExperiment(b: ExperimentInput) {
  if (!b.name.trim()) validationError('Name is required.');
  if (!b.symbols.length) validationError('Pick at least one symbol.');
  if (!b.signal_ids.length) validationError('Pick at least one signal.');
  const p = b.params;
  if (!p.consistency.length || !p.delay_ms.length || !p.packet_loss_pct.length || !p.clock_skew_ms.length || !p.node_outage.length)
    validationError('Every test setting needs at least one value.');
}

function csv(rows: (string | number | null)[][]): Blob {
  const esc = (v: string | number | null) => {
    const s = v === null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return new Blob([rows.map((r) => r.map(esc).join(',')).join('\n') + '\n'], { type: 'text/csv' });
}

function readingModel(run: Run, signal: Signal, symbol: string) {
  const exp = findOr404(S.data.experiments, run.experiment_id, 'Experiment');
  const [a, b] = S.experimentRange(exp);
  return makeReadingModel(run.id, { signal, symbol, rangeStartMs: a, rangeEndMs: b }, run.config);
}

function replayedUntilMs(run: Run, exp: Experiment): number {
  const [a, b] = S.experimentRange(exp);
  if (run.status === 'done') return b;
  return run.progress.replayed_until ? Date.parse(run.progress.replayed_until) : a;
}

export function createMockClient(): ApiClient {
  return {
    mode: 'mock',

    getHealth: async () => {
      await sleep(randomBetween(150, 400));
      return { data: S.health(), servedBy: S.servedBy() };
    },

    // ------------------------------------------------------------ datasets
    listDatasets: () => served(() => [...S.data.datasets].sort((a, b) => a.symbol.localeCompare(b.symbol) || a.day.localeCompare(b.day) || a.kind.localeCompare(b.kind))),
    importDatasets: async (body) => {
      await latency();
      if (body.end < body.start) validationError('End date is before start date.');
      const days = daysBetween(body.start, body.end);
      if (days.length > 31) validationError('Import at most 31 days at a time.');
      const created = [];
      let write = { status: 'committed' as const, stores_written: [], stores_pending: [] } as WriteResponse<null>['write'];
      for (const day of days) {
        if (S.data.datasets.some((d) => d.symbol === body.symbol && d.kind === body.kind && d.day === day && d.status !== 'failed')) continue;
        S.data.datasets = S.data.datasets.filter((d) => !(d.symbol === body.symbol && d.kind === body.kind && d.day === day));
        const d = {
          id: S.newId('ds'),
          symbol: body.symbol,
          kind: body.kind,
          day,
          status: 'downloading' as const,
          row_count: null,
          size_bytes: null,
          checksum_ok: null,
          error: null,
          created_at: now(),
          version: 1,
        };
        S.data.datasets.push(d);
        created.push(d);
        write = S.write('dataset', d.id, 1, `${d.symbol} ${d.kind} ${d.day}`);
      }
      if (!created.length) validationError('All of those days are already imported.');
      return { records: clone(created), write };
    },
    deleteDataset: async (id) => {
      await latency();
      findOr404(S.data.datasets, id, 'Dataset');
      S.data.datasets = S.data.datasets.filter((d) => d.id !== id);
      return result(null, S.write('dataset', id, null));
    },

    // ------------------------------------------------------------ signals
    listSignals: () => served(() => S.data.signals),
    getSignal: (id) => served(() => findOr404(S.data.signals, id, 'Signal')),
    createSignal: async (body: SignalInput) => {
      await latency();
      if (!body.name.trim()) validationError('Name is required.');
      const s: Signal = {
        id: S.newId('sig'),
        name: body.name.trim(),
        type: body.type,
        inputs: body.inputs,
        window_ms: body.window_ms,
        params: body.params,
        description: body.description,
        builtin: false,
        version: 1,
        updated_at: now(),
      };
      S.data.signals.push(s);
      return result(s, S.write('signal', s.id, 1, s.name));
    },
    updateSignal: async (id, body) => {
      await latency();
      const s = findOr404(S.data.signals, id, 'Signal');
      if (s.builtin) throw new ApiError(409, 'Built-in signals cannot be edited.', { reason: 'builtin', message: 'Built-in signals cannot be edited.' });
      Object.assign(s, {
        name: body.name.trim(),
        type: body.type,
        inputs: body.inputs,
        window_ms: body.window_ms,
        params: body.params,
        description: body.description,
        version: s.version + 1,
        updated_at: now(),
      });
      return result(s, S.write('signal', s.id, s.version, s.name));
    },
    deleteSignal: async (id) => {
      await latency();
      const s = findOr404(S.data.signals, id, 'Signal');
      if (s.builtin) throw new ApiError(409, 'Built-in signals cannot be deleted.', { reason: 'builtin', message: 'Built-in signals cannot be deleted.' });
      const usedBy = S.data.experiments.filter((e) => e.signal_ids.includes(id));
      if (usedBy.length) {
        const message = `Used by ${usedBy.length} experiment${usedBy.length === 1 ? '' : 's'}: ${usedBy.map((e) => e.name).join(', ')}.`;
        throw new ApiError(409, message, { reason: 'in_use', message, used_by: usedBy.map((e) => ({ id: e.id, name: e.name })) });
      }
      S.data.signals = S.data.signals.filter((x) => x.id !== id);
      return result(null, S.write('signal', id, null));
    },

    // ------------------------------------------------------------ experiments
    listExperiments: (f = {}) =>
      served(() =>
        S.data.experiments
          .filter((e) => !f.status || e.status === f.status)
          .filter((e) => !f.tag || e.tags.includes(f.tag))
          .filter((e) => !f.q || e.name.toLowerCase().includes(f.q.toLowerCase()))
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
      ),
    getExperiment: (id) => served(() => findOr404(S.data.experiments, id, 'Experiment')),
    createExperiment: async (body) => {
      await latency();
      validateExperiment(body);
      const e: Experiment = {
        id: S.newId('exp'),
        name: body.name.trim(),
        symbols: body.symbols,
        dates: body.dates,
        signal_ids: body.signal_ids,
        params: body.params,
        replay_speed: body.replay_speed,
        status: 'draft',
        tags: body.tags,
        notes: body.notes,
        run_count: 0,
        version: 1,
        created_at: now(),
        updated_at: now(),
      };
      S.data.experiments.push(e);
      return result(e, S.write('experiment', e.id, 1, e.name));
    },
    updateExperiment: async (id, body) => {
      await latency();
      validateExperiment(body);
      const e = findOr404(S.data.experiments, id, 'Experiment');
      Object.assign(e, {
        name: body.name.trim(),
        symbols: body.symbols,
        dates: body.dates,
        signal_ids: body.signal_ids,
        params: body.params,
        replay_speed: body.replay_speed,
        tags: body.tags,
        notes: body.notes,
        version: e.version + 1,
        updated_at: now(),
      });
      return result(e, S.write('experiment', e.id, e.version, e.name));
    },
    deleteExperiment: async (id) => {
      await latency();
      findOr404(S.data.experiments, id, 'Experiment');
      for (const r of S.data.runs.filter((x) => x.experiment_id === id)) S.write('run', r.id, null);
      S.data.runs = S.data.runs.filter((r) => r.experiment_id !== id);
      S.data.experiments = S.data.experiments.filter((e) => e.id !== id);
      return result(null, S.write('experiment', id, null));
    },
    cloneExperiment: async (id) => {
      await latency();
      const src = findOr404(S.data.experiments, id, 'Experiment');
      const e: Experiment = {
        ...clone(src),
        id: S.newId('exp'),
        name: `${src.name} (copy)`,
        status: 'draft',
        run_count: 0,
        version: 1,
        created_at: now(),
        updated_at: now(),
      };
      S.data.experiments.push(e);
      return result(e, S.write('experiment', e.id, 1, e.name));
    },
    launchExperiment: async (id) => {
      await latency();
      const e = findOr404(S.data.experiments, id, 'Experiment');
      const active = S.data.runs.some((r) => r.experiment_id === id && ['queued', 'running', 'waiting_for_cassandra'].includes(r.status));
      if (active) throw new ApiError(409, 'This experiment already has runs in progress.', { reason: 'already_running', message: 'This experiment already has runs in progress.' });
      const configs = expandGrid(e.params);
      const ids: string[] = [];
      let write = S.write('experiment', e.id, e.version, e.name);
      for (const config of configs) {
        const run: Run = {
          id: S.newId('run'),
          experiment_id: e.id,
          config,
          status: S.isUp('cassandra') ? 'queued' : 'waiting_for_cassandra',
          queue_position: null,
          progress: { pct: 0, replayed_until: null },
          started_at: null,
          finished_at: null,
          error: null,
          report: null,
          version: 1,
        };
        S.data.runs.push(run);
        S.enqueue(run);
        ids.push(run.id);
        write = S.write('run', run.id, 1, run.id);
      }
      e.run_count += configs.length;
      e.version++;
      e.updated_at = now();
      S.write('experiment', e.id, e.version, e.name);
      S.refreshExperimentStatus(e.id);
      S.waitingRuns().forEach((r, i) => (r.queue_position = i + 1));
      return { run_ids: ids, write };
    },
    listRuns: (id) =>
      served(() => {
        findOr404(S.data.experiments, id, 'Experiment');
        return S.data.runs.filter((r) => r.experiment_id === id);
      }),
    exportExperimentCsv: async (id) => {
      await latency();
      const e = findOr404(S.data.experiments, id, 'Experiment');
      const rows: (string | number | null)[][] = [
        ['run_id', 'consistency', 'delay_ms', 'packet_loss_pct', 'clock_skew_ms', 'node_outage', 'status', 'signal_id', 'signal_name', 'signal_type', 'avg_error', 'max_error', 'wrong_call_rate', 'staleness_p50_ms', 'staleness_p99_ms', 'latency_p50_ms', 'latency_p99_ms', 'readings_count'],
      ];
      for (const r of S.data.runs.filter((x) => x.experiment_id === id))
        for (const sid of e.signal_ids) {
          const s = S.data.signals.find((x) => x.id === sid);
          const rep = r.report?.[sid];
          rows.push([r.id, r.config.consistency, r.config.delay_ms, r.config.packet_loss_pct, r.config.clock_skew_ms, r.config.node_outage, r.status, sid, s?.name ?? '', s?.type ?? '', rep?.avg_error ?? null, rep?.max_error ?? null, rep?.wrong_call_rate ?? null, rep?.staleness_p50_ms ?? null, rep?.staleness_p99_ms ?? null, rep?.latency_p50_ms ?? null, rep?.latency_p99_ms ?? null, rep?.readings_count ?? null]);
        }
      return csv(rows);
    },

    // ------------------------------------------------------------ runs
    getRun: (id) => served(() => findOr404(S.data.runs, id, 'Run')),
    cancelRun: async (id) => {
      await latency();
      const r = findOr404(S.data.runs, id, 'Run');
      if (!['queued', 'running', 'waiting_for_cassandra'].includes(r.status))
        throw new ApiError(409, 'Only queued or running runs can be cancelled.', { reason: 'not_cancellable', message: 'Only queued or running runs can be cancelled.' });
      Object.assign(r, { status: 'cancelled', finished_at: now(), queue_position: null, version: r.version + 1 });
      const write = S.write('run', r.id, r.version, r.id);
      S.refreshExperimentStatus(r.experiment_id);
      return result(r, write);
    },
    getReadings: async (runId, q) => {
      await latency();
      if (!S.isUp('cassandra')) throw new ApiError(503, 'Readings are stored in Cassandra, which is down.', { reason: 'cassandra_down', message: 'Readings are stored in Cassandra, which is down.' });
      const run = findOr404(S.data.runs, runId, 'Run');
      const exp = findOr404(S.data.experiments, run.experiment_id, 'Experiment');
      const signal = findOr404(S.data.signals, q.signal_id, 'Signal');
      const [a] = S.experimentRange(exp);
      const until = replayedUntilMs(run, exp);
      const from = Math.max(a, q.from ? Date.parse(q.from) : a);
      const to = Math.min(until, q.to ? Date.parse(q.to) : until);
      const points: ReadingPoint[] = run.status === 'queued' || run.status === 'waiting_for_cassandra' ? [] : readingsBetween(readingModel(run, signal, q.symbol), from, to, q.max_points ?? 2000);
      return { data: { points }, servedBy: 'cassandra' };
    },
    getFaults: (runId) =>
      served(() => {
        const run = findOr404(S.data.runs, runId, 'Run');
        const exp = findOr404(S.data.experiments, run.experiment_id, 'Experiment');
        const [a, b] = S.experimentRange(exp);
        const until = replayedUntilMs(run, exp);
        return faultWindowsFor(run.config, a, b).filter((w) => Date.parse(w.start) < until);
      }),
    exportRunCsv: async (id) => {
      await latency();
      if (!S.isUp('cassandra')) throw new ApiError(503, 'Readings are stored in Cassandra, which is down.', { reason: 'cassandra_down', message: 'Readings are stored in Cassandra, which is down.' });
      const run = findOr404(S.data.runs, id, 'Run');
      const exp = findOr404(S.data.experiments, run.experiment_id, 'Experiment');
      const [a] = S.experimentRange(exp);
      const rows: (string | number | null)[][] = [['t', 'signal_id', 'symbol', 'value', 'truth', 'staleness_ms', 'latency_ms']];
      for (const sid of exp.signal_ids) {
        const s = S.data.signals.find((x) => x.id === sid);
        if (!s) continue;
        for (const sym of exp.symbols)
          for (const p of readingsBetween(readingModel(run, s, sym), a, replayedUntilMs(run, exp), 500))
            rows.push([p.t, sid, sym, p.value, p.truth, p.staleness_ms, p.latency_ms]);
      }
      return csv(rows);
    },
    openRunLive: (runId, handlers: LiveHandlers): LiveConnection => {
      let closed = false;
      const timers: ReturnType<typeof setTimeout>[] = [];
      const fail = (reason: string) => {
        if (closed) return;
        closed = true;
        timers.forEach(clearInterval);
        handlers.onClose?.(reason);
      };
      if (!S.isUp('redis')) {
        timers.push(setTimeout(() => fail('redis_down'), 300));
        return { close: () => ((closed = true), timers.forEach(clearTimeout)) };
      }
      let lastStatus: Run['status'] | null = null;
      let lastTMs = 0;
      let ticks = 0;
      const send = (m: LiveMessage) => !closed && handlers.onMessage(m);
      timers.push(
        setTimeout(() => {
          if (closed) return;
          handlers.onOpen?.();
          timers.push(
            setInterval(() => {
              if (!S.isUp('redis')) return fail('redis_down');
              const run = S.data.runs.find((r) => r.id === runId);
              const exp = run && S.data.experiments.find((e) => e.id === run.experiment_id);
              if (!run || !exp) return fail('not_found');
              if (run.status !== lastStatus) {
                lastStatus = run.status;
                send({ type: 'status', status: run.status });
              }
              ticks++;
              if (run.status !== 'running') return;
              const [a, b] = S.experimentRange(exp);
              // interpolate replay time smoothly between the 1 s progress ticks
              const target = run.progress.replayed_until ? Date.parse(run.progress.replayed_until) : a;
              const stepMs = ((b - a) * 0.6) / 100 / 10;
              const tMs = Math.min(b, target, Math.max(lastTMs + stepMs, target - stepMs * 10));
              if (tMs <= lastTMs) return;
              lastTMs = tMs;
              for (const sid of exp.signal_ids) {
                const s = S.data.signals.find((x) => x.id === sid);
                if (!s) continue;
                for (const sym of exp.symbols) {
                  const p = readingAt(readingModel(run, s, sym), tMs);
                  send({ type: 'reading', signal_id: sid, symbol: sym, ...p });
                }
              }
              if (ticks % 10 === 0) {
                send({ type: 'progress', pct: run.progress.pct, replayed_until: run.progress.replayed_until });
                send({ type: 'faults', active: activeFaultsAt(faultWindowsFor(run.config, a, b), tMs) });
              }
            }, 100),
          );
        }, 250),
      );
      return {
        close: () => {
          closed = true;
          timers.forEach((t) => {
            clearTimeout(t);
            clearInterval(t);
          });
        },
      };
    },

    // ------------------------------------------------------------ queue
    getQueue: () =>
      served(() => ({
        running: S.data.runs.find((r) => r.status === 'running') ?? null,
        waiting: S.waitingRuns(),
        blocked_reason: S.isUp('cassandra') ? null : ('cassandra_down' as const),
      })),

    // ------------------------------------------------------------ annotations
    listAnnotations: (targetType, targetId) =>
      served(() =>
        S.data.annotations
          .filter((a) => a.target_type === targetType && a.target_id === targetId)
          .sort((a, b) => b.created_at.localeCompare(a.created_at)),
      ),
    createAnnotation: async (body) => {
      await latency();
      if (!body.text.trim()) validationError('Annotation text is required.');
      const a: Annotation = {
        id: S.newId('ann'),
        ...body,
        text: body.text.trim(),
        author: body.author.trim() || 'anonymous',
        created_at: now(),
        updated_at: now(),
        version: 1,
      };
      S.data.annotations.push(a);
      return result(a, S.write('annotation', a.id, 1, a.text.slice(0, 40)));
    },
    updateAnnotation: async (id, body) => {
      await latency();
      const a = findOr404(S.data.annotations, id, 'Annotation');
      if (!body.text.trim()) validationError('Annotation text is required.');
      Object.assign(a, { text: body.text.trim(), tags: body.tags, updated_at: now(), version: a.version + 1 });
      return result(a, S.write('annotation', a.id, a.version, a.text.slice(0, 40)));
    },
    deleteAnnotation: async (id) => {
      await latency();
      findOr404(S.data.annotations, id, 'Annotation');
      S.data.annotations = S.data.annotations.filter((a) => a.id !== id);
      return result(null, S.write('annotation', id, null));
    },

    // ------------------------------------------------------------ audit
    getAudit: () => served(() => S.audit()),
    repairAudit: async (body) => {
      await latency();
      S.repair('all' in body ? undefined : `${body.type}:${body.id}`);
      return S.audit();
    },
  };
}
