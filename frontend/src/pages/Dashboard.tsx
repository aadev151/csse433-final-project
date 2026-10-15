import { useMemo, type ReactNode } from 'react';
import { Anchor, Badge, Button, Grid, Group, Paper, Progress, Skeleton, Stack, Table, Text, Title } from '@mantine/core';
import { useQueries } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Run, StoreName } from '../api/types';
import { ExperimentStatusBadge } from '../components/badges';
import { IconPlus } from '../components/icons';
import { ErrorState, PageHeader } from '../components/states';
import { qk, useExperiments, useQueue, useSignals } from '../hooks/queries';
import { useHealth } from '../hooks/useHealth';
import { STORE_LABEL, fmtAgo, fmtMs, fmtTime } from '../lib/format';
import { configLabel } from '../lib/grid';
import { fmtMetric } from '../lib/metrics';

function Card({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <Paper withBorder p="md" radius="md" h="100%">
      <Group justify="space-between" mb="sm">
        <Title order={4} fz={15}>
          {title}
        </Title>
        {right}
      </Group>
      {children}
    </Paper>
  );
}

function HealthCard() {
  const q = useHealth();
  if (q.isPending) return <Skeleton h={180} />;
  if (!q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} title="Health check failed" />;
  const h = q.data;
  const stores: StoreName[] = ['cassandra', 'mongodb', 'redis'];
  return (
    <Stack gap="xs">
      <Table withRowBorders={false} verticalSpacing={4}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Store</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th className="num">Ping</Table.Th>
            <Table.Th className="num">Pending writes</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {stores.map((s) => (
            <Table.Tr key={s}>
              <Table.Td fw={500}>{STORE_LABEL[s]}</Table.Td>
              <Table.Td>
                <Badge size="sm" variant="light" color={h.stores[s].up ? 'green' : 'red'} tt="none">
                  {h.stores[s].up ? 'up' : 'down'}
                </Badge>
              </Table.Td>
              <Table.Td className="num">{fmtMs(h.stores[s].latency_ms)}</Table.Td>
              <Table.Td className="num">
                {h.pending_writes[s] > 0 ? (
                  <Text span c="yellow.8" fw={600} size="sm">
                    {h.pending_writes[s]}
                  </Text>
                ) : (
                  0
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group gap={6}>
        <Text size="xs" c="dimmed">
          Cassandra nodes:
        </Text>
        {h.stores.cassandra.nodes.map((n) => (
          <Badge key={n.name} size="sm" variant="light" color={n.status === 'UN' ? 'green' : 'red'} tt="none" className="mono">
            {n.name} {n.status}
          </Badge>
        ))}
      </Group>
      <Text size="xs" c="dimmed">
        Checked <span className="mono">{fmtTime(h.checked_at)}</span> UTC · mode {h.mode}
      </Text>
    </Stack>
  );
}

function QueueCard({ names }: { names: Map<string, string> }) {
  const q = useQueue();
  if (q.isPending) return <Skeleton h={120} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const { running, waiting, blocked_reason } = q.data.data;
  return (
    <Stack gap="sm">
      {blocked_reason === 'cassandra_down' && (
        <Text size="sm" c="yellow.8">
          Runs are waiting for Cassandra to come back.
        </Text>
      )}
      {running ? (
        <Stack gap={4}>
          <Anchor component={Link} to={`/runs/${running.id}`} fw={600} size="sm">
            {names.get(running.experiment_id) ?? running.experiment_id}
          </Anchor>
          <Text size="sm">{configLabel(running.config)}</Text>
          <Group gap="sm" wrap="nowrap">
            <Progress value={running.progress.pct} style={{ flex: 1 }} animated />
            <Text size="xs" w={40} ta="right">
              {Math.round(running.progress.pct)}%
            </Text>
          </Group>
        </Stack>
      ) : (
        <Text size="sm" c="dimmed">
          Nothing running right now.
        </Text>
      )}
      <Group justify="space-between">
        <Text size="sm">
          <Text span fw={650}>
            {waiting.length}
          </Text>{' '}
          run{waiting.length === 1 ? '' : 's'} waiting
        </Text>
        <Anchor component={Link} to="/queue" size="sm">
          Open queue →
        </Anchor>
      </Group>
    </Stack>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const exps = useExperiments();
  const signals = useSignals();
  const names = useMemo(() => new Map((exps.data?.data ?? []).map((e) => [e.id, e.name])), [exps.data]);
  const sigNames = useMemo(() => new Map((signals.data?.data ?? []).map((s) => [s.id, s.name])), [signals.data]);
  const recent = (exps.data?.data ?? []).slice(0, 5);
  const withRuns = (exps.data?.data ?? []).filter((e) => e.run_count > 0).slice(0, 5);
  const runQs = useQueries({ queries: withRuns.map((e) => ({ queryKey: qk.runs(e.id), queryFn: () => api.listRuns(e.id) })) });
  const finished = runQs
    .flatMap((q) => q.data?.data ?? [])
    .filter((r): r is Run & { finished_at: string } => r.status === 'done' && !!r.finished_at)
    .sort((a, b) => b.finished_at.localeCompare(a.finished_at))
    .slice(0, 5);

  const worst = (r: Run) => {
    const entries = Object.entries(r.report ?? {});
    if (!entries.length) return null;
    const [sid, rep] = entries.reduce((a, b) => (b[1].avg_error > a[1].avg_error ? b : a));
    const p99 = Math.max(...entries.map(([, x]) => x.latency_p99_ms));
    return { name: sigNames.get(sid) ?? sid, err: rep.avg_error, p99 };
  };

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="How much do weak consistency choices corrupt market-data signals?"
        servedBy={exps.data?.servedBy}
        actions={
          <Button component={Link} to="/experiments/new" leftSection={<IconPlus size={16} />}>
            New experiment
          </Button>
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card title="Database health">
            <HealthCard />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card title="Queue">
            <QueueCard names={names} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card
            title="Recent experiments"
            right={
              <Anchor component={Link} to="/experiments" size="sm">
                All →
              </Anchor>
            }
          >
            {exps.isPending ? (
              <Stack gap={6}>{[1, 2, 3].map((i) => <Skeleton key={i} h={28} />)}</Stack>
            ) : exps.isError ? (
              <ErrorState error={exps.error} onRetry={() => exps.refetch()} />
            ) : recent.length === 0 ? (
              <Stack align="flex-start" gap="xs">
                <Text size="sm" c="dimmed">
                  No experiments yet.
                </Text>
                <Button size="xs" component={Link} to="/experiments/new">
                  Design your first experiment
                </Button>
              </Stack>
            ) : (
              <Table highlightOnHover>
                <Table.Tbody>
                  {recent.map((e) => (
                    <Table.Tr key={e.id} className="clickable-row" onClick={() => navigate(`/experiments/${e.id}`)}>
                      <Table.Td fw={500}>{e.name}</Table.Td>
                      <Table.Td>
                        <ExperimentStatusBadge status={e.status} />
                      </Table.Td>
                      <Table.Td className="num">{e.run_count} runs</Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {fmtAgo(e.updated_at)}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}>
          <Card title="Recently finished runs">
            {exps.isPending || runQs.some((q) => q.isPending) ? (
              <Stack gap={6}>{[1, 2, 3].map((i) => <Skeleton key={i} h={28} />)}</Stack>
            ) : runQs.find((q) => q.isError) ? (
              <ErrorState error={runQs.find((q) => q.isError)!.error} onRetry={() => runQs.forEach((q) => q.refetch())} />
            ) : finished.length === 0 ? (
              <Text size="sm" c="dimmed">
                No finished runs yet. Results show up here as runs complete.
              </Text>
            ) : (
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Run</Table.Th>
                    <Table.Th>Worst avg error</Table.Th>
                    <Table.Th className="num">Max latency p99</Table.Th>
                    <Table.Th>Finished</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {finished.map((r) => {
                    const w = worst(r);
                    return (
                      <Table.Tr key={r.id} className="clickable-row" onClick={() => navigate(`/runs/${r.id}`)}>
                        <Table.Td>
                          <Text size="sm" fw={500} lineClamp={1}>
                            {names.get(r.experiment_id) ?? r.experiment_id}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {configLabel(r.config)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          {w ? (
                            <Text size="sm">
                              {w.name}: <b>{fmtMetric('avg_error', w.err)}</b>
                            </Text>
                          ) : (
                            '—'
                          )}
                        </Table.Td>
                        <Table.Td className="num">{w ? fmtMs(w.p99) : '—'}</Table.Td>
                        <Table.Td>
                          <Text size="xs" c="dimmed">{fmtAgo(r.finished_at)}</Text>
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}
