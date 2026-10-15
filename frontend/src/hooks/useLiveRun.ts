import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ActiveFault, LiveMessage, RunStatus } from '../api/types';
import { useStoreStatus } from './useHealth';

export const MAX_POINTS_PER_SERIES = 600;
const FLUSH_MS = 200; // at most ~5 redraws per second
const LATENCY_WINDOW_MS = 10_000;

export interface LiveSeries {
  t: string[];
  value: number[];
  truth: number[];
}

export type LiveConnectionState = 'connecting' | 'open' | 'reconnecting' | 'unavailable' | 'closed';

export interface LiveRunState {
  connection: LiveConnectionState;
  /** seconds until the next reconnect attempt (when reconnecting) */
  retryIn: number | null;
  progress: { pct: number; replayed_until: string | null } | null;
  faults: ActiveFault[];
  status: RunStatus | null;
  /** keyed by `${signal_id}|${symbol}`; arrays are mutated in place, use `revision` to detect changes */
  series: Record<string, LiveSeries>;
  latencyP50: number | null;
  revision: number;
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const TERMINAL: RunStatus[] = ['done', 'failed', 'cancelled'];

/**
 * Subscribes to the live run stream (WS /ws/runs/{id}/live). Messages are
 * buffered and flushed to React state at most 5×/s; each series keeps at most
 * 600 points. Reconnects with exponential backoff; does not connect while
 * health reports Redis down (state "unavailable").
 */
export function useLiveRun(runId: string, enabled: boolean, opts: { onStatus?: (s: RunStatus) => void; readings?: boolean } = {}): LiveRunState {
  const { redisUp } = useStoreStatus();
  const keepReadings = opts.readings ?? true;
  const onStatusRef = useRef(opts.onStatus);
  onStatusRef.current = opts.onStatus;

  const [state, setState] = useState<LiveRunState>({
    connection: 'connecting',
    retryIn: null,
    progress: null,
    faults: [],
    status: null,
    series: {},
    latencyP50: null,
    revision: 0,
  });

  // mutable buffers shared with the socket callbacks
  const buf = useRef({
    runId,
    series: {} as Record<string, LiveSeries>,
    latencies: [] as { at: number; ms: number }[],
    progress: null as LiveRunState['progress'],
    faults: [] as ActiveFault[],
    status: null as RunStatus | null,
    dirty: false,
  });

  useEffect(() => {
    if (!enabled) {
      setState((s) => ({ ...s, connection: 'closed', retryIn: null }));
      return;
    }
    if (!redisUp) {
      setState((s) => ({ ...s, connection: 'unavailable', retryIn: null }));
      return;
    }

    let disposed = false;
    let attempt = 0;
    let conn: { close: () => void } | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let countdown: ReturnType<typeof setInterval> | null = null;
    const b = buf.current;
    if (b.runId !== runId) Object.assign(b, { runId, series: {}, latencies: [], progress: null, faults: [], status: null, dirty: true });

    const onMessage = (m: LiveMessage) => {
      switch (m.type) {
        case 'reading': {
          if (keepReadings) {
            const key = `${m.signal_id}|${m.symbol}`;
            const s = (b.series[key] ??= { t: [], value: [], truth: [] });
            s.t.push(m.t);
            s.value.push(m.value);
            s.truth.push(m.truth);
          }
          b.latencies.push({ at: Date.now(), ms: m.latency_ms });
          break;
        }
        case 'progress':
          b.progress = { pct: m.pct, replayed_until: m.replayed_until };
          break;
        case 'faults':
          b.faults = m.active;
          break;
        case 'status':
          if (b.status !== m.status) {
            b.status = m.status;
            onStatusRef.current?.(m.status);
          }
          break;
      }
      b.dirty = true;
    };

    const connect = () => {
      if (disposed) return;
      setState((s) => ({ ...s, connection: attempt === 0 ? 'connecting' : 'reconnecting', retryIn: null }));
      conn = api.openRunLive(runId, {
        onOpen: () => {
          attempt = 0;
          setState((s) => ({ ...s, connection: 'open', retryIn: null }));
        },
        onMessage,
        onClose: () => {
          if (disposed) return;
          if (b.status && TERMINAL.includes(b.status)) {
            setState((s) => ({ ...s, connection: 'closed' }));
            return;
          }
          const delay = Math.min(15_000, 1000 * 2 ** attempt);
          attempt++;
          let left = Math.ceil(delay / 1000);
          setState((s) => ({ ...s, connection: 'reconnecting', retryIn: left }));
          countdown = setInterval(() => {
            left = Math.max(0, left - 1);
            setState((s) => ({ ...s, retryIn: left }));
          }, 1000);
          retryTimer = setTimeout(() => {
            if (countdown) clearInterval(countdown);
            connect();
          }, delay);
        },
      });
    };
    connect();

    const flush = setInterval(() => {
      if (!b.dirty) return;
      b.dirty = false;
      for (const s of Object.values(b.series)) {
        const extra = s.t.length - MAX_POINTS_PER_SERIES;
        if (extra > 0) {
          s.t.splice(0, extra);
          s.value.splice(0, extra);
          s.truth.splice(0, extra);
        }
      }
      const cutoff = Date.now() - LATENCY_WINDOW_MS;
      b.latencies = b.latencies.filter((l) => l.at >= cutoff);
      setState((s) => ({
        ...s,
        progress: b.progress,
        faults: b.faults,
        status: b.status,
        series: b.series,
        latencyP50: median(b.latencies.map((l) => l.ms)),
        revision: s.revision + 1,
      }));
    }, FLUSH_MS);

    return () => {
      disposed = true;
      conn?.close();
      if (retryTimer) clearTimeout(retryTimer);
      if (countdown) clearInterval(countdown);
      clearInterval(flush);
    };
  }, [runId, enabled, redisUp, keepReadings]);

  return state;
}
