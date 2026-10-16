import type { ExperimentParams, RunConfig } from '../api/types';
import { CONSISTENCY_LEVELS } from '../api/types';

/** Number of runs an experiment's settings grid expands to. */
export function gridSize(p: ExperimentParams): number {
  return p.consistency.length * p.delay_ms.length * p.packet_loss_pct.length * p.clock_skew_ms.length * p.node_outage.length;
}

/** Cartesian product of the settings grid, in display order (consistency, then delay, then the rest). */
export function expandGrid(p: ExperimentParams): RunConfig[] {
  const out: RunConfig[] = [];
  const consistency = [...p.consistency].sort((a, b) => CONSISTENCY_LEVELS.indexOf(a) - CONSISTENCY_LEVELS.indexOf(b));
  const num = (xs: number[]) => [...xs].sort((a, b) => a - b);
  for (const c of consistency)
    for (const d of num(p.delay_ms))
      for (const l of num(p.packet_loss_pct))
        for (const s of num(p.clock_skew_ms))
          for (const o of p.node_outage)
            out.push({ consistency: c, delay_ms: d, packet_loss_pct: l, clock_skew_ms: s, node_outage: o });
  return out;
}

/** Sort comparator for run configs: consistency (ONE, QUORUM, ALL), delay asc, then the other settings. */
export function compareConfigs(a: RunConfig, b: RunConfig): number {
  return (
    CONSISTENCY_LEVELS.indexOf(a.consistency) - CONSISTENCY_LEVELS.indexOf(b.consistency) ||
    a.delay_ms - b.delay_ms ||
    a.packet_loss_pct - b.packet_loss_pct ||
    a.clock_skew_ms - b.clock_skew_ms ||
    (a.node_outage === b.node_outage ? 0 : a.node_outage === 'none' ? -1 : 1)
  );
}

/** Short human label for a run config, omitting settings at their defaults. */
export function configLabel(c: RunConfig, opts: { compact?: boolean } = {}): string {
  const sep = opts.compact ? ' · ' : ', ';
  const parts: string[] = [c.consistency, `${c.delay_ms} ms`];
  if (c.packet_loss_pct) parts.push(`${c.packet_loss_pct}% loss`);
  if (c.clock_skew_ms) parts.push(`skew ${c.clock_skew_ms} ms`);
  if (c.node_outage === 'one_node_down') parts.push('1 node down');
  return parts.join(sep);
}

/** Inclusive number of days between two YYYY-MM-DD strings. */
export function dayCount(start: string, end: string): number {
  const a = Date.parse(`${start}T00:00:00Z`);
  const b = Date.parse(`${end}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return 0;
  return Math.round((b - a) / 86_400_000) + 1;
}

/** All YYYY-MM-DD days from start to end inclusive. */
export function daysBetween(start: string, end: string): string[] {
  const n = dayCount(start, end);
  const base = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: n }, (_, i) => new Date(base + i * 86_400_000).toISOString().slice(0, 10));
}
