import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import type { AnnotationTarget, ExperimentFilters, Run } from '../api/types';

/** Query keys, in one place so mutations can invalidate them. */
export const qk = {
  signals: ['signals'] as const,
  datasets: ['datasets'] as const,
  experiments: (f?: ExperimentFilters) => (f ? (['experiments', f] as const) : (['experiments'] as const)),
  experiment: (id: string) => ['experiment', id] as const,
  runs: (expId: string) => ['runs', expId] as const,
  run: (id: string) => ['run', id] as const,
  faults: (id: string) => ['faults', id] as const,
  queue: ['queue'] as const,
  annotations: (t: AnnotationTarget, id: string) => ['annotations', t, id] as const,
};

const ACTIVE: Run['status'][] = ['queued', 'running', 'waiting_for_cassandra'];
export const isActiveRun = (r: Pick<Run, 'status'>) => ACTIVE.includes(r.status);

export function useSignals() {
  return useQuery({ queryKey: qk.signals, queryFn: () => api.listSignals() });
}

export function useDatasets() {
  return useQuery({
    queryKey: qk.datasets,
    queryFn: () => api.listDatasets(),
    // poll every 3 s while any import is in progress
    refetchInterval: (q) => (q.state.data?.data.some((d) => d.status === 'downloading' || d.status === 'verifying') ? 3000 : false),
  });
}

export function useExperiments(filters: ExperimentFilters = {}) {
  return useQuery({
    queryKey: qk.experiments(filters),
    queryFn: () => api.listExperiments(filters),
    refetchInterval: (q) => (q.state.data?.data.some((e) => e.status === 'running' || e.status === 'queued') ? 5000 : false),
  });
}

export function useExperiment(id: string | undefined) {
  return useQuery({
    queryKey: qk.experiment(id ?? ''),
    queryFn: () => api.getExperiment(id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ['running', 'queued'].includes(q.state.data.data.status) ? 3000 : false),
  });
}

export function useRuns(expId: string | undefined) {
  return useQuery({
    queryKey: qk.runs(expId ?? ''),
    queryFn: () => api.listRuns(expId!),
    enabled: !!expId,
    refetchInterval: (q) => (q.state.data?.data.some(isActiveRun) ? 3000 : false),
  });
}

export function useQueue() {
  return useQuery({ queryKey: qk.queue, queryFn: () => api.getQueue(), refetchInterval: 2000 });
}

export function useAnnotations(targetType: AnnotationTarget, targetId: string) {
  return useQuery({ queryKey: qk.annotations(targetType, targetId), queryFn: () => api.listAnnotations(targetType, targetId) });
}
