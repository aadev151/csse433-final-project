import { useComputedColorScheme } from '@mantine/core';
import type { SignalType } from '../api/types';
import { SIGNAL_TYPE_COLOR } from '../lib/colors';

export function useSignalColor(type: SignalType): string {
  const scheme = useComputedColorScheme('light');
  return SIGNAL_TYPE_COLOR[type][scheme];
}

/** Both signal-type colours plus chart ink for the current colour scheme. */
export function useChartColors() {
  const scheme = useComputedColorScheme('light');
  const dark = scheme === 'dark';
  return {
    dark,
    latest: SIGNAL_TYPE_COLOR['latest-value'][scheme],
    running: SIGNAL_TYPE_COLOR['running-total'][scheme],
    byType: (t: SignalType) => SIGNAL_TYPE_COLOR[t][scheme],
    ink: dark ? '#f0efec' : '#0b0b0b',
    inkSecondary: dark ? '#c3c2b7' : '#52514e',
    muted: '#898781',
    grid: dark ? '#2c2c2a' : '#e1e0d9',
    axis: dark ? '#383835' : '#c3c2b7',
    surface: dark ? '#1a1a19' : '#fcfcfb',
    pending: dark ? '#383835' : '#e9e8e3',
  };
}
