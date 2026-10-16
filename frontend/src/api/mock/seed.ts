import type { Annotation, Dataset, Experiment, Run, Signal } from '../types';
import { expandGrid } from '../../lib/grid';
import { reportFor } from './generators';
import { hash01, hashString } from './random';

export interface MockData {
  signals: Signal[];
  datasets: Dataset[];
  experiments: Experiment[];
  runs: Run[];
  annotations: Annotation[];
}

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

export function buildSeed(now = Date.now()): MockData {
  const signals: Signal[] = [
    {
      id: 'sig_mid_price',
      name: 'mid-price',
      type: 'latest-value',
      inputs: ['quotes'],
      window_ms: 0,
      params: {},
      description: 'Average of best bid and best ask.',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
    {
      id: 'sig_micro_price',
      name: 'micro-price',
      type: 'latest-value',
      inputs: ['quotes'],
      window_ms: 0,
      params: { weighting: 'size' },
      description: 'Bid/ask weighted by the opposite side size: (bid·askQty + ask·bidQty) / (bidQty + askQty).',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
    {
      id: 'sig_quoted_spread',
      name: 'quoted spread',
      type: 'latest-value',
      inputs: ['quotes'],
      window_ms: 0,
      params: {},
      description: 'Best ask minus best bid.',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
    {
      id: 'sig_ofi_1s',
      name: 'order flow imbalance 1s',
      type: 'running-total',
      inputs: ['trades', 'quotes'],
      window_ms: 1_000,
      params: { normalize: 'total_volume' },
      description: '(buy volume − sell volume) / total volume over the last second.',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
    {
      id: 'sig_signed_volume_5s',
      name: 'signed volume 5s',
      type: 'running-total',
      inputs: ['trades'],
      window_ms: 5_000,
      params: {},
      description: 'Sum of trade sizes, positive for buyer-initiated and negative for seller-initiated, over 5 seconds.',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
    {
      id: 'sig_vwap_60s',
      name: 'VWAP 60s',
      type: 'running-total',
      inputs: ['trades'],
      window_ms: 60_000,
      params: {},
      description: 'Volume-weighted average trade price over the last 60 seconds.',
      builtin: true,
      version: 2,
      updated_at: iso(now - 12 * DAY),
    },
    {
      id: 'sig_realized_vol_60s',
      name: 'realized volatility 60s',
      type: 'running-total',
      inputs: ['trades'],
      window_ms: 60_000,
      params: { sample_ms: 1000 },
      description: 'Square root of the sum of squared 1-second log returns over 60 seconds.',
      builtin: true,
      version: 1,
      updated_at: iso(now - 30 * DAY),
    },
  ];

  const datasets: Dataset[] = [];
  for (const symbol of ['BTCUSDT', 'ETHUSDT'] as const)
    for (const kind of ['trades', 'quotes'] as const)
      for (const day of ['2026-08-01', '2026-08-02', '2026-08-03']) {
        const id = `ds_${symbol.slice(0, 3).toLowerCase()}_${kind[0]}_${day.slice(5).replace('-', '')}`;
        const r = hash01(hashString(id), 1);
        const rows = Math.round((kind === 'trades' ? (symbol === 'BTCUSDT' ? 2_400_000 : 1_300_000) : 6_100_000) * (0.85 + 0.3 * r));
        datasets.push({
          id,
          symbol,
          kind,
          day,
          status: 'ready',
          row_count: rows,
          size_bytes: Math.round(rows * (kind === 'trades' ? 31 : 38)),
          checksum_ok: true,
          error: null,
          created_at: iso(now - 20 * DAY + datasets.length * 5 * MIN),
          version: 1,
        });
      }

  const allSignalIds = signals.map((s) => s.id);

  // Experiment 1: done delay sweep, 3 consistency levels x 6 delays = 18 runs
  const exp1: Experiment = {
    id: 'exp_delay_sweep',
    name: 'Delay sweep — BTC & ETH, Aug 1',
    symbols: ['BTCUSDT', 'ETHUSDT'],
    dates: { start: '2026-08-01', end: '2026-08-01' },
    signal_ids: allSignalIds,
    params: {
      consistency: ['ONE', 'QUORUM', 'ALL'],
      delay_ms: [0, 1, 5, 25, 100, 500],
      packet_loss_pct: [0],
      clock_skew_ms: [0],
      node_outage: ['none'],
    },
    replay_speed: 50,
    status: 'done',
    tags: ['baseline', 'delay'],
    notes: 'Main hypothesis test: does network delay hurt running-total signals more than latest-value ones?',
    run_count: 18,
    version: 3,
    created_at: iso(now - 6 * DAY),
    updated_at: iso(now - 4 * DAY),
  };

  // Experiment 2: running packet-loss sweep, 2 x 3 = 6 runs
  const exp2: Experiment = {
    id: 'exp_packet_loss',
    name: 'Packet loss under ONE vs QUORUM',
    symbols: ['BTCUSDT'],
    dates: { start: '2026-08-02', end: '2026-08-02' },
    signal_ids: ['sig_micro_price', 'sig_quoted_spread', 'sig_ofi_1s', 'sig_vwap_60s', 'sig_signed_volume_5s'],
    params: {
      consistency: ['ONE', 'QUORUM'],
      delay_ms: [25],
      packet_loss_pct: [0, 1, 5],
      clock_skew_ms: [0],
      node_outage: ['none'],
    },
    replay_speed: 10,
    status: 'running',
    tags: ['packet-loss'],
    notes: '',
    run_count: 6,
    version: 2,
    created_at: iso(now - 1 * DAY),
    updated_at: iso(now - 40 * MIN),
  };

  // Experiment 3: draft
  const exp3: Experiment = {
    id: 'exp_skew_outage',
    name: 'Clock skew + node outage',
    symbols: ['BTCUSDT'],
    dates: { start: '2026-08-03', end: '2026-08-03' },
    signal_ids: ['sig_mid_price', 'sig_micro_price', 'sig_ofi_1s', 'sig_vwap_60s'],
    params: {
      consistency: ['ONE', 'QUORUM', 'ALL'],
      delay_ms: [0],
      packet_loss_pct: [0],
      clock_skew_ms: [0, 50, 200],
      node_outage: ['none', 'one_node_down'],
    },
    replay_speed: 50,
    status: 'draft',
    tags: ['clock-skew', 'outage'],
    notes: 'Waiting on the node-outage fault injector before launching.',
    run_count: 0,
    version: 1,
    created_at: iso(now - 3 * HOUR),
    updated_at: iso(now - 2 * HOUR),
  };

  const runs: Run[] = [];
  const readings = (e: Experiment) => 864_000 * e.symbols.length;

  expandGrid(exp1.params).forEach((config, i) => {
    const id = `run_ds_${String(i + 1).padStart(2, '0')}`;
    const started = now - 5 * DAY + i * 25 * MIN;
    const report: Run['report'] = {};
    for (const s of signals) report[s.id] = reportFor(id, s, config, readings(exp1));
    runs.push({
      id,
      experiment_id: exp1.id,
      config,
      status: 'done',
      queue_position: null,
      progress: { pct: 100, replayed_until: '2026-08-02T00:00:00.000Z' },
      started_at: iso(started),
      finished_at: iso(started + 24 * MIN),
      error: null,
      report,
      version: 3,
    });
  });

  const exp2Signals = signals.filter((s) => exp2.signal_ids.includes(s.id));
  expandGrid(exp2.params).forEach((config, i) => {
    const id = `run_pl_${String(i + 1).padStart(2, '0')}`;
    const base: Run = {
      id,
      experiment_id: exp2.id,
      config,
      status: 'queued',
      queue_position: null,
      progress: { pct: 0, replayed_until: null },
      started_at: null,
      finished_at: null,
      error: null,
      report: null,
      version: 1,
    };
    if (i < 2) {
      const started = now - 50 * MIN + i * 18 * MIN;
      const report: Record<string, ReturnType<typeof reportFor>> = {};
      for (const s of exp2Signals) report[s.id] = reportFor(id, s, config, readings(exp2));
      Object.assign(base, {
        status: 'done',
        progress: { pct: 100, replayed_until: '2026-08-03T00:00:00.000Z' },
        started_at: iso(started),
        finished_at: iso(started + 17 * MIN),
        report,
        version: 3,
      });
    } else if (i === 2) {
      Object.assign(base, {
        status: 'running',
        progress: { pct: 34, replayed_until: iso(Date.parse('2026-08-02T00:00:00Z') + 0.34 * DAY) },
        started_at: iso(now - 6 * MIN),
        version: 2,
      });
    }
    runs.push(base);
  });

  const annotations: Annotation[] = [
    {
      id: 'ann_1',
      target_type: 'experiment',
      target_id: exp1.id,
      text: 'Running-total signals blow up past 25 ms at ONE; QUORUM and ALL stay flat. Matches the hypothesis.',
      tags: ['finding'],
      author: 'Alex',
      created_at: iso(now - 4 * DAY + 2 * HOUR),
      updated_at: iso(now - 4 * DAY + 2 * HOUR),
      version: 1,
    },
    {
      id: 'ann_2',
      target_type: 'experiment',
      target_id: exp1.id,
      text: 'Latency p99 at ALL with 500 ms delay is the price we pay — worth a slide.',
      tags: ['slides', 'latency'],
      author: 'Priya',
      created_at: iso(now - 3 * DAY),
      updated_at: iso(now - 3 * DAY),
      version: 1,
    },
    {
      id: 'ann_3',
      target_type: 'run',
      target_id: 'run_ds_06',
      text: 'Worst run in the sweep. VWAP drift is visible during every delay window.',
      tags: ['outlier'],
      author: 'Alex',
      created_at: iso(now - 4 * DAY + 3 * HOUR),
      updated_at: iso(now - 4 * DAY + 3 * HOUR),
      version: 1,
    },
  ];

  return { signals, datasets, experiments: [exp1, exp2, exp3], runs, annotations };
}
