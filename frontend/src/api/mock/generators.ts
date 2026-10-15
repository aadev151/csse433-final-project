import type { ActiveFault, FaultWindow, ReadingPoint, RunConfig, Signal, SignalReport } from '../types';
import { gauss, hash01, hashString, mulberry32, smoothNoise } from './random';

/**
 * Deterministic synthetic market-data generator for mock mode.
 *
 * truth(t): seeded random walk (knots every 5 minutes, linearly interpolated)
 *           plus fine-grained smooth noise, shaped per signal.
 * value(t): truth + error, where the error amplitude comes from the same model
 *           that produces the run report, grows inside fault windows, and is
 *           much larger (and persistent) for running-total signals.
 */

const BASE_PRICE: Record<string, number> = { BTCUSDT: 64_250, ETHUSDT: 3_140, SOLUSDT: 152 };

type Shape = 'price' | 'spread' | 'bounded' | 'volume' | 'volatility';

const SHAPE_BY_ID: Record<string, Shape> = {
  sig_mid_price: 'price',
  sig_micro_price: 'price',
  sig_quoted_spread: 'spread',
  sig_ofi_1s: 'bounded',
  sig_signed_volume_5s: 'volume',
  sig_vwap_60s: 'price',
  sig_realized_vol_60s: 'volatility',
};

function shapeOf(signal: Pick<Signal, 'id' | 'type'>): Shape {
  return SHAPE_BY_ID[signal.id] ?? (signal.type === 'latest-value' ? 'price' : 'bounded');
}

/** Typical magnitude used to normalise errors (and to scale synthetic errors back). */
export function errorScale(signal: Pick<Signal, 'id' | 'type'>, symbol: string): number {
  const p = BASE_PRICE[symbol] ?? 100;
  switch (shapeOf(signal)) {
    case 'price':
      return p * 0.001;
    case 'spread':
      return p * 0.00002;
    case 'bounded':
      return 0.5;
    case 'volume':
      return symbol === 'BTCUSDT' ? 4 : 60;
    case 'volatility':
      return 0.0006;
  }
}

// ---------------------------------------------------------------------------
// Truth
// ---------------------------------------------------------------------------

const KNOT_MS = 5 * 60_000;
const walkCache = new Map<string, Float64Array>();

function walk(key: string, fromMs: number, knots: number): Float64Array {
  const cacheKey = `${key}|${fromMs}|${knots}`;
  let w = walkCache.get(cacheKey);
  if (!w) {
    const rnd = mulberry32(hashString(cacheKey));
    w = new Float64Array(knots + 2);
    let x = 0;
    for (let i = 0; i < w.length; i++) {
      // Box-Muller from the seeded generator
      const g = Math.sqrt(-2 * Math.log(Math.max(1e-9, rnd()))) * Math.cos(2 * Math.PI * rnd());
      x += g;
      w[i] = x;
    }
    walkCache.set(cacheKey, w);
  }
  return w;
}

export interface SeriesContext {
  signal: Pick<Signal, 'id' | 'type'>;
  symbol: string;
  rangeStartMs: number; // start of the experiment's replay window
  rangeEndMs: number;
}

export function truthAt(ctx: SeriesContext, tMs: number): number {
  const knots = Math.ceil((ctx.rangeEndMs - ctx.rangeStartMs) / KNOT_MS);
  const shape = shapeOf(ctx.signal);
  // price-like signals share one underlying walk per symbol so mid/micro/vwap move together
  const walkKey = shape === 'price' ? `price:${ctx.symbol}` : `${ctx.signal.id}:${ctx.symbol}`;
  const w = walk(walkKey, ctx.rangeStartMs, knots);
  const x = Math.max(0, (tMs - ctx.rangeStartMs) / KNOT_MS);
  const i = Math.min(Math.floor(x), w.length - 2);
  const f = Math.min(1, x - i);
  const base = w[i] + (w[i + 1] - w[i]) * f;
  const seed = hashString(walkKey);
  const fine = smoothNoise(seed, tMs / 4000) * 0.35 + smoothNoise(seed + 7, tMs / 600) * 0.15;
  const p = BASE_PRICE[ctx.symbol] ?? 100;
  switch (shape) {
    case 'price': {
      const offset = ctx.signal.id === 'sig_micro_price' ? smoothNoise(seed + 3, tMs / 1500) * p * 0.00003 : 0;
      const lag = ctx.signal.id === 'sig_vwap_60s' ? -smoothNoise(seed + 11, tMs / 60_000) * p * 0.0002 : 0;
      return p * (1 + 0.0012 * (base + fine)) + offset + lag;
    }
    case 'spread':
      return p * 0.00002 * (1 + 0.6 * Math.abs(Math.sin(base * 0.7) + fine));
    case 'bounded':
      return Math.tanh(0.25 * base * Math.sin(base * 0.3) + 1.6 * fine);
    case 'volume':
      return errorScale(ctx.signal, ctx.symbol) * (2.5 * Math.sin(base * 0.4) + 3 * fine);
    case 'volatility':
      return 0.0006 * (1.4 + 0.5 * Math.sin(base * 0.2) + 0.4 * fine);
  }
}

// ---------------------------------------------------------------------------
// Run report model
// ---------------------------------------------------------------------------

const CONSISTENCY_FACTOR = { ONE: 1, QUORUM: 0.035, ALL: 0.012 } as const;

function jitter(key: string, spread = 0.15): number {
  return 1 + (hash01(hashString(key), 1) * 2 - 1) * spread;
}

export function reportFor(
  runId: string,
  signal: Pick<Signal, 'id' | 'type'>,
  c: RunConfig,
  readingsCount: number,
): SignalReport {
  const running = signal.type === 'running-total';
  const base = running ? 0.03 : 0.0022;
  const faultFactor =
    (1 + c.delay_ms / 22) *
    (1 + c.packet_loss_pct * 0.35) *
    (1 + c.clock_skew_ms / 45) *
    (c.node_outage === 'one_node_down' ? 1.8 : 1);
  const cf = CONSISTENCY_FACTOR[c.consistency];
  const j = jitter(`${runId}:${signal.id}`);
  const avg = base * faultFactor * cf * j + (running ? 0.0008 : 0.0002);
  const max = avg * (running ? 6.5 : 4.2) * jitter(`${runId}:${signal.id}:max`, 0.2);
  const wrongK = running ? 1.35 : 0.9;
  const wrong = 0.5 * (1 - Math.exp(-avg * wrongK * 4)) + (running ? 0.004 : 0.001);

  const replicaLag = c.delay_ms + c.packet_loss_pct * 12 + c.clock_skew_ms * 0.6 + (c.node_outage === 'one_node_down' ? 8 : 0);
  const stale50 =
    c.consistency === 'ONE' ? 1.5 + replicaLag * 0.55 : c.consistency === 'QUORUM' ? 0.8 + replicaLag * 0.02 : 0.6 + replicaLag * 0.008;
  const stale99 = stale50 * 3.2 + (c.consistency === 'ONE' ? replicaLag * 0.9 : 2);
  const lat50 =
    c.consistency === 'ONE' ? 0.7 + c.packet_loss_pct * 0.1 : c.consistency === 'QUORUM' ? 1.4 + c.delay_ms * 0.95 : 1.9 + c.delay_ms * 1.05;
  const lat99 = lat50 * 2.6 + c.packet_loss_pct * 40 + (c.node_outage === 'one_node_down' && c.consistency === 'ALL' ? 2000 : 0);

  const tj = jitter(`${runId}:${signal.id}:t`, 0.08);
  return {
    avg_error: avg,
    max_error: max,
    wrong_call_rate: Math.min(0.6, wrong),
    staleness_p50_ms: stale50 * tj,
    staleness_p99_ms: stale99 * tj,
    latency_p50_ms: lat50 * tj,
    latency_p99_ms: lat99 * tj,
    readings_count: readingsCount,
  };
}

// ---------------------------------------------------------------------------
// Fault windows
// ---------------------------------------------------------------------------

export function faultWindowsFor(c: RunConfig, rangeStartMs: number, rangeEndMs: number): FaultWindow[] {
  const len = rangeEndMs - rangeStartMs;
  const at = (f: number) => new Date(rangeStartMs + f * len).toISOString();
  const out: FaultWindow[] = [];
  const windows: [number, number][] = [
    [0.08, 0.22],
    [0.38, 0.52],
    [0.68, 0.84],
  ];
  if (c.delay_ms > 0) for (const [a, b] of windows) out.push({ start: at(a), end: at(b), kind: 'delay', target: 'cass2', value: c.delay_ms });
  if (c.packet_loss_pct > 0)
    for (const [a, b] of windows) out.push({ start: at(a + 0.03), end: at(b + 0.02), kind: 'packet_loss', target: 'cass3', value: c.packet_loss_pct });
  if (c.clock_skew_ms > 0) out.push({ start: at(0.25), end: at(0.65), kind: 'clock_skew', target: 'cass1', value: c.clock_skew_ms });
  if (c.node_outage === 'one_node_down') out.push({ start: at(0.55), end: at(0.75), kind: 'node_down', target: 'cass3', value: null });
  return out.sort((a, b) => a.start.localeCompare(b.start));
}

export function activeFaultsAt(windows: FaultWindow[], tMs: number): ActiveFault[] {
  return windows
    .filter((w) => Date.parse(w.start) <= tMs && tMs < Date.parse(w.end))
    .map(({ kind, target, value }) => ({ kind, target, value }));
}

// ---------------------------------------------------------------------------
// Readings
// ---------------------------------------------------------------------------

export interface ReadingModel {
  ctx: SeriesContext;
  report: SignalReport; // expected report (used for error amplitudes)
  windows: FaultWindow[];
  seed: number;
}

export function makeReadingModel(runId: string, ctx: SeriesContext, config: RunConfig): ReadingModel {
  const report = reportFor(runId, ctx.signal, config, 0);
  return {
    ctx,
    report,
    windows: faultWindowsFor(config, ctx.rangeStartMs, ctx.rangeEndMs),
    seed: hashString(`${runId}:${ctx.signal.id}:${ctx.symbol}`),
  };
}

export function readingAt(m: ReadingModel, tMs: number): ReadingPoint {
  const truth = truthAt(m.ctx, tMs);
  const inFault = m.windows.some((w) => Date.parse(w.start) <= tMs && tMs < Date.parse(w.end));
  const scale = errorScale(m.ctx.signal, m.ctx.symbol);
  const amp = m.report.avg_error * scale * (inFault ? 2.4 : 0.35);
  const n = Math.floor(tMs / 100);
  let err: number;
  if (m.ctx.signal.type === 'running-total') {
    // missed/duplicated trades accumulate: persistent, drifting error
    err = amp * (1.4 * smoothNoise(m.seed, tMs / 20_000) + 0.4 * gauss(m.seed, n));
  } else {
    // stale quote: occasional jumps back to an older value
    const stale = hash01(m.seed, n) < (inFault ? 0.25 : 0.05);
    err = stale ? amp * 2.5 * gauss(m.seed + 1, n) : amp * 0.2 * gauss(m.seed + 2, n);
  }
  const s50 = m.report.staleness_p50_ms;
  const l50 = m.report.latency_p50_ms;
  const staleness = Math.max(0, s50 * (inFault ? 2 : 0.5) * -Math.log(Math.max(1e-6, hash01(m.seed + 3, n))));
  const latency = Math.max(0.1, l50 * (0.6 + 0.8 * -Math.log(Math.max(1e-6, hash01(m.seed + 4, n)))) * (inFault ? 1.5 : 0.8));
  return { t: new Date(tMs).toISOString(), value: truth + err, truth, staleness_ms: staleness, latency_ms: latency };
}

export function readingsBetween(m: ReadingModel, fromMs: number, toMs: number, maxPoints: number): ReadingPoint[] {
  if (toMs <= fromMs) return [];
  const step = Math.max(100, (toMs - fromMs) / Math.max(1, maxPoints - 1));
  const out: ReadingPoint[] = [];
  for (let t = fromMs; t <= toMs && out.length < maxPoints; t += step) out.push(readingAt(m, Math.round(t / 100) * 100));
  return out;
}
