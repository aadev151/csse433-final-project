import { useMemo, useState } from 'react';
import { Alert, Anchor, Button, Group, Paper, Progress, Stack, Table, Text } from '@mantine/core';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Run } from '../api/types';
import { ConfirmModal } from '../components/ConfirmModal';
import { RunStatusBadge } from '../components/badges';
import { FaultChips } from '../components/LiveMonitor';
import { EmptyState, ErrorState, LoadingState, PageHeader, SectionTitle } from '../components/states';
import { qk, useExperiments, useQueue } from '../hooks/queries';
import { useLiveRun } from '../hooks/useLiveRun';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { fmtAgo, fmtTime } from '../lib/format';
import { configLabel } from '../lib/grid';

function RunningCard({ run, experimentName, onCancel }: { run: Run; experimentName: string; onCancel: () => void }) {
  const live = useLiveRun(run.id, true, { readings: false });
  const progress = live.progress ?? run.progress;
  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="xs">
        <Stack gap={0}>
          <Text size="xs" c="dimmed">
            Running now
          </Text>
          <Anchor component={Link} to={`/runs/${run.id}`} fw={600}>
            {experimentName}
          </Anchor>
          <Text size="sm">{configLabel(run.config)}</Text>
        </Stack>
        <Group gap="xs">
          <RunStatusBadge run={run} />
          <Button size="xs" variant="light" color="red" onClick={onCancel}>
            Cancel
          </Button>
        </Group>
      </Group>
      <Group gap="sm" wrap="nowrap">
        <Progress value={progress.pct} style={{ flex: 1 }} animated />
        <Text size="xs" w={44} ta="right">
          {progress.pct.toFixed(1)}%
        </Text>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>
        Replayed until <span className="mono">{fmtTime(progress.replayed_until)}</span> UTC · started {fmtAgo(run.started_at)}
      </Text>
      <Group gap="xs" mt="sm">
        <Text size="xs" fw={600}>
          Active faults:
        </Text>
        {live.connection === 'unavailable' ? (
          <Text size="xs" c="dimmed">
            Live fault info is unavailable while Redis is down.
          </Text>
        ) : (
          <FaultChips faults={live.faults} emptyText={live.connection === 'open' ? 'No faults active right now' : 'connecting…'} />
        )}
      </Group>
    </Paper>
  );
}

export function QueuePage() {
  const q = useQueue();
  const exps = useExperiments();
  const names = useMemo(() => new Map((exps.data?.data ?? []).map((e) => [e.id, e.name])), [exps.data]);
  const [toCancel, setToCancel] = useState<Run | null>(null);
  const cancel = useWriteMutation({
    mutationFn: (r: Run) => api.cancelRun(r.id),
    action: 'Run cancelled',
    invalidate: [qk.queue, ['runs'], ['run'], ['experiment']],
    onSuccess: () => setToCancel(null),
  });
  const name = (r: Run) => names.get(r.experiment_id) ?? r.experiment_id;

  return (
    <>
      <PageHeader title="Queue" subtitle="Runs execute one at a time against the Cassandra cluster." servedBy={q.data?.servedBy} />
      {q.isPending ? (
        <LoadingState rows={5} height={40} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <Stack gap="md">
          {q.data.data.blocked_reason === 'cassandra_down' && (
            <Alert color="yellow" variant="light" title="Waiting for Cassandra">
              Runs are waiting for Cassandra to come back. They will start automatically.
            </Alert>
          )}
          {q.data.data.running ? (
            <RunningCard run={q.data.data.running} experimentName={name(q.data.data.running)} onCancel={() => setToCancel(q.data.data.running)} />
          ) : q.data.data.waiting.length === 0 ? (
            <EmptyState
              title="Nothing running"
              message="The queue is empty. Launch an experiment to queue its runs."
              action={
                <Button component={Link} to="/experiments">
                  Go to experiments
                </Button>
              }
            />
          ) : null}
          {q.data.data.waiting.length > 0 && (
            <>
              <SectionTitle>Waiting ({q.data.data.waiting.length})</SectionTitle>
              <Table.ScrollContainer minWidth={700}>
                <Table highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th className="num" w={60}>
                        #
                      </Table.Th>
                      <Table.Th>Experiment</Table.Th>
                      <Table.Th>Config</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {q.data.data.waiting.map((r, i) => (
                      <Table.Tr key={r.id}>
                        <Table.Td className="num">{r.queue_position ?? i + 1}</Table.Td>
                        <Table.Td>
                          <Anchor component={Link} to={`/runs/${r.id}`} size="sm">
                            {name(r)}
                          </Anchor>
                        </Table.Td>
                        <Table.Td>{configLabel(r.config)}</Table.Td>
                        <Table.Td>
                          <RunStatusBadge run={{ ...r, queue_position: null }} />
                        </Table.Td>
                        <Table.Td>
                          <Group justify="flex-end">
                            <Button size="compact-xs" variant="subtle" color="red" onClick={() => setToCancel(r)}>
                              Cancel
                            </Button>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </>
          )}
        </Stack>
      )}
      <ConfirmModal
        opened={!!toCancel}
        title="Cancel run?"
        message={toCancel ? <>Cancel the {configLabel(toCancel.config)} run of <b>{name(toCancel)}</b>?</> : ''}
        confirmLabel="Cancel run"
        loading={cancel.isPending}
        onConfirm={() => toCancel && cancel.mutate(toCancel)}
        onClose={() => setToCancel(null)}
      />
    </>
  );
}
