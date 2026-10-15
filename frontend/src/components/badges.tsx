import type { ReactNode } from 'react';
import { Badge, Code, Tooltip } from '@mantine/core';
import { useSignalColor } from '../hooks/useSignalColor';
import type { DatasetStatus, ExperimentStatus, Run, RunStatus, SignalType } from '../api/types';
import { DATASET_STATUS_COLOR, EXPERIMENT_STATUS_COLOR, RUN_STATUS_COLOR } from '../lib/colors';

export function SignalTypeBadge({ type, size = 'sm' }: { type: SignalType; size?: 'xs' | 'sm' | 'md' }) {
  const color = useSignalColor(type);
  return (
    <Badge size={size} radius="sm" variant="light" color={color} tt="none" style={{ flexShrink: 0, overflow: 'visible' }} styles={{ label: { overflow: 'visible' } }} leftSection={<span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: 2, background: color }} />}>
      {type}
    </Badge>
  );
}

const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  queued: 'queued',
  waiting_for_cassandra: 'waiting for Cassandra',
  running: 'running',
  done: 'done',
  failed: 'failed',
  cancelled: 'cancelled',
};

export function RunStatusBadge({ run }: { run: Pick<Run, 'status' | 'queue_position' | 'error'> }) {
  const text = RUN_STATUS_TEXT[run.status] + (run.status === 'queued' && run.queue_position ? ` · #${run.queue_position}` : '');
  const badge = (
    <Badge size="sm" radius="sm" variant="light" color={RUN_STATUS_COLOR[run.status]} tt="none">
      {text}
    </Badge>
  );
  return run.error ? <Tooltip label={run.error}>{badge}</Tooltip> : badge;
}

export function ExperimentStatusBadge({ status }: { status: ExperimentStatus }) {
  return (
    <Badge size="sm" radius="sm" variant="light" color={EXPERIMENT_STATUS_COLOR[status]} tt="none">
      {status}
    </Badge>
  );
}

export function DatasetStatusBadge({ status }: { status: DatasetStatus }) {
  return (
    <Badge size="sm" radius="sm" variant="light" color={DATASET_STATUS_COLOR[status]} tt="none">
      {status}
    </Badge>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <Code bg="transparent" p={0} fz="xs" className="mono">{children}</Code>;
}
