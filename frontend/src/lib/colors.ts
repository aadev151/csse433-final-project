import type { FaultKind, RunStatus, ExperimentStatus, DatasetStatus, SignalType } from '../api/types';

/**
 * App-wide colour roles. Signal-type hues come from a CVD-validated categorical
 * pair (blue / orange); status colours are reserved for status only.
 */
export const SIGNAL_TYPE_COLOR: Record<SignalType, { light: string; dark: string }> = {
  'latest-value': { light: '#2a78d6', dark: '#3987e5' },
  'running-total': { light: '#eb6834', dark: '#d95926' },
};

export const SIGNAL_TYPE_LABEL: Record<SignalType, string> = {
  'latest-value': 'latest-value',
  'running-total': 'running-total',
};

export const TRUTH_COLOR = '#898781';

/** Sequential single-hue blue ramp (light -> dark) for heatmaps. */
export const SEQUENTIAL_BLUE: [number, string][] = [
  [0, '#eef5fd'],
  [0.15, '#cde2fb'],
  [0.3, '#9ec5f4'],
  [0.45, '#6da7ec'],
  [0.6, '#3987e5'],
  [0.75, '#256abf'],
  [0.88, '#184f95'],
  [1, '#0d366b'],
];

export const FAULT_COLOR: Record<FaultKind, string> = {
  delay: '#6250d6',
  packet_loss: '#e87ba4',
  clock_skew: '#1baf7a',
  node_down: '#eda100',
};

export const FAULT_LABEL: Record<FaultKind, string> = {
  delay: 'delay',
  packet_loss: 'packet loss',
  clock_skew: 'clock skew',
  node_down: 'node down',
};

/** Mantine colour names for status badges: green = good, yellow = pending/degraded, red = failed/down. */
export const RUN_STATUS_COLOR: Record<RunStatus, string> = {
  queued: 'gray',
  waiting_for_cassandra: 'yellow',
  running: 'blue',
  done: 'green',
  failed: 'red',
  cancelled: 'gray',
};

export const EXPERIMENT_STATUS_COLOR: Record<ExperimentStatus, string> = {
  draft: 'gray',
  queued: 'yellow',
  running: 'blue',
  done: 'green',
  failed: 'red',
};

export const DATASET_STATUS_COLOR: Record<DatasetStatus, string> = {
  downloading: 'blue',
  verifying: 'yellow',
  ready: 'green',
  failed: 'red',
};
