import type { Signal, SignalReport } from '../api/types';
import { fmtInt, fmtMs, fmtPct } from './format';

export type MetricKey = 'avg_error' | 'wrong_call_rate' | 'staleness_p99_ms' | 'latency_p99_ms';

export const METRICS: { value: MetricKey; label: string; axis: string }[] = [
  { value: 'avg_error', label: 'Avg error', axis: 'Average error (normalised, unitless)' },
  { value: 'wrong_call_rate', label: 'Wrong-call rate', axis: 'Wrong-call rate (%)' },
  { value: 'staleness_p99_ms', label: 'Staleness p99', axis: 'Staleness p99 (ms)' },
  { value: 'latency_p99_ms', label: 'Latency p99', axis: 'Read latency p99 (ms)' },
];

export function metricLabel(m: MetricKey) {
  return METRICS.find((x) => x.value === m)!;
}

/** Compact value text for a metric (used in heatmap cells). */
export function fmtMetric(m: MetricKey, v: number): string {
  if (m === 'wrong_call_rate') return fmtPct(v, 1);
  if (m === 'avg_error') return v >= 0.1 ? v.toFixed(2) : v >= 0.01 ? v.toFixed(3) : v.toPrecision(2);
  return fmtMs(v);
}

/** Display value for charts (wrong-call rate shown as a percentage). */
export function metricValue(m: MetricKey, r: SignalReport): number {
  return m === 'wrong_call_rate' ? r.wrong_call_rate * 100 : r[m];
}

export function reportTooltip(signal: Pick<Signal, 'name' | 'type'>, r: SignalReport, header: string): string {
  return [
    `<b>${signal.name}</b> (${signal.type})`,
    header,
    `avg error: ${fmtMetric('avg_error', r.avg_error)}   max: ${fmtMetric('avg_error', r.max_error)}`,
    `wrong-call rate: ${fmtPct(r.wrong_call_rate, 2)}`,
    `staleness p50 / p99: ${fmtMs(r.staleness_p50_ms)} / ${fmtMs(r.staleness_p99_ms)}`,
    `latency p50 / p99: ${fmtMs(r.latency_p50_ms)} / ${fmtMs(r.latency_p99_ms)}`,
    `readings: ${fmtInt(r.readings_count)}`,
  ].join('<br>');
}

/** Signals ordered latest-value block first, then running-total, by name. */
export function orderSignals<T extends Pick<Signal, 'type' | 'name'>>(signals: T[]): T[] {
  return [...signals].sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === 'latest-value' ? -1 : 1));
}
