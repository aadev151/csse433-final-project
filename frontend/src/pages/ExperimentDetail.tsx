import { useMemo, useState, type ReactNode } from 'react';
import { Anchor, Badge, Button, Group, Paper, Progress, SegmentedControl, Select, SimpleGrid, Stack, Table, Tabs, Text, Tooltip } from '@mantine/core';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { ApiError } from '../api/client';
import { CONSISTENCY_LEVELS, type Consistency, type Experiment, type Run, type Signal } from '../api/types';
import { Annotations } from '../components/Annotations';
import { ConfirmModal } from '../components/ConfirmModal';
import { ExperimentStatusBadge, Mono, RunStatusBadge } from '../components/badges';
import { FragilityHeatmap } from '../components/charts/FragilityHeatmap';
import { MetricVsDelayChart } from '../components/charts/MetricVsDelayChart';
import { IconDownload } from '../components/icons';
import { EmptyState, ErrorState, LoadingState, PageHeader, SectionTitle } from '../components/states';
import { isActiveRun, useExperiment, useRuns, useSignals } from '../hooks/queries';
import { useExperimentActions } from '../hooks/useExperimentActions';
import { useStoreStatus } from '../hooks/useHealth';
import { downloadBlob, fmtShortTime } from '../lib/format';
import { compareConfigs, dayCount, gridSize } from '../lib/grid';
import { METRICS, orderSignals, type MetricKey } from '../lib/metrics';
import { notifyError } from '../lib/notify';

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} lts={0.3}>
        {label}
      </Text>
      <div>{children}</div>
    </Stack>
  );
}

function Summary({ e, signals }: { e: Experiment; signals: Signal[] }) {
  const p = e.params;
  const list = (xs: (string | number)[], unit = '') => xs.map((x) => `${x}${unit}`).join(', ');
  const used = orderSignals(signals.filter((s) => e.signal_ids.includes(s.id)));
  const missing = e.signal_ids.length - used.length;
  return (
    <Paper withBorder p="md" radius="md">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
        <Field label="Data">
          <Text size="sm">{e.symbols.join(', ')}</Text>
          <Text size="sm" className="mono">
            {e.dates.start === e.dates.end ? e.dates.start : `${e.dates.start} → ${e.dates.end}`} ({dayCount(e.dates.start, e.dates.end)} d)
          </Text>
        </Field>
        <Field label="Settings grid">
          <Text size="sm">Consistency: {list(p.consistency)}</Text>
          <Text size="sm">Delay: {list(p.delay_ms, ' ms')}</Text>
          <Text size="sm">
            Loss: {list(p.packet_loss_pct, '%')} · Skew: {list(p.clock_skew_ms, ' ms')}
          </Text>
          <Text size="sm">Node outage: {p.node_outage.map((o) => (o === 'none' ? 'none' : 'one node down')).join(', ')}</Text>
        </Field>
        <Field label="Runs">
          <Text size="sm">
            {gridSize(p)} per launch · {e.run_count} created
          </Text>
          <Text size="sm">Replay speed {e.replay_speed}× · RF 3</Text>
        </Field>
        <Field label={`Signals (${e.signal_ids.length})`}>
          <Group gap={4}>
            {used.map((s) => (
              <Tooltip key={s.id} label={s.type}>
                <Badge size="sm" variant="dot" color={s.type === 'latest-value' ? '#2a78d6' : '#eb6834'} tt="none">
                  {s.name}
                </Badge>
              </Tooltip>
            ))}
            {missing > 0 && (
              <Text size="xs" c="dimmed">
                +{missing} deleted
              </Text>
            )}
          </Group>
        </Field>
      </SimpleGrid>
      {e.notes && (
        <Text size="sm" mt="md" c="dimmed" style={{ whiteSpace: 'pre-wrap' }}>
          {e.notes}
        </Text>
      )}
    </Paper>
  );
}

function RunsTable({ runs }: { runs: Run[] }) {
  const navigate = useNavigate();
  const sorted = [...runs].sort((a, b) => compareConfigs(a.config, b.config));
  return (
    <Table.ScrollContainer minWidth={820}>
      <Table highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Consistency</Table.Th>
            <Table.Th className="num">Delay</Table.Th>
            <Table.Th className="num">Packet loss</Table.Th>
            <Table.Th className="num">Clock skew</Table.Th>
            <Table.Th>Node outage</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th w={180}>Progress</Table.Th>
            <Table.Th>Finished (UTC)</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sorted.map((r) => (
            <Table.Tr key={r.id} className="clickable-row" onClick={() => navigate(`/runs/${r.id}`)}>
              <Table.Td fw={500}>{r.config.consistency}</Table.Td>
              <Table.Td className="num">{r.config.delay_ms} ms</Table.Td>
              <Table.Td className="num">{r.config.packet_loss_pct}%</Table.Td>
              <Table.Td className="num">{r.config.clock_skew_ms} ms</Table.Td>
              <Table.Td>{r.config.node_outage === 'none' ? '—' : 'one node down'}</Table.Td>
              <Table.Td>
                <RunStatusBadge run={r} />
              </Table.Td>
              <Table.Td>
                {r.status === 'running' || (r.status === 'waiting_for_cassandra' && r.progress.pct > 0) ? (
                  <Group gap={6} wrap="nowrap">
                    <Progress value={r.progress.pct} size="sm" style={{ flex: 1 }} animated={r.status === 'running'} color={r.status === 'running' ? 'blue' : 'yellow'} />
                    <Text size="xs" w={36} ta="right">
                      {Math.round(r.progress.pct)}%
                    </Text>
                  </Group>
                ) : r.status === 'done' ? (
                  <Text size="xs" c="dimmed">
                    100%
                  </Text>
                ) : (
                  <Text size="xs" c="dimmed">
                    —
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                <Mono>{fmtShortTime(r.finished_at)}</Mono>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function Results({ e, runs, signals }: { e: Experiment; runs: Run[]; signals: Signal[] }) {
  const navigate = useNavigate();
  const [metric, setMetric] = useState<MetricKey>('avg_error');
  const [scale, setScale] = useState<'log' | 'linear'>('log');
  const [facet, setFacet] = useState<string>('all');
  const used = useMemo(() => signals.filter((s) => e.signal_ids.includes(s.id)), [signals, e.signal_ids]);
  const levels = CONSISTENCY_LEVELS.filter((l) => e.params.consistency.includes(l));
  const done = runs.filter((r) => r.status === 'done').length;

  if (runs.length === 0)
    return <EmptyState title="No results yet" message="Launch this experiment to queue its runs. The heatmap fills in as each run finishes." />;

  return (
    <Stack gap="md">
      <Group gap="sm" wrap="wrap">
        <SegmentedControl size="xs" value={metric} onChange={(v) => setMetric(v as MetricKey)} data={METRICS.map((m) => ({ value: m.value, label: m.label }))} />
        <Tooltip label="Log colour/axis scale makes small and huge errors visible together.">
          <SegmentedControl
            size="xs"
            value={scale}
            onChange={(v) => setScale(v as 'log' | 'linear')}
            data={[
              { value: 'log', label: 'Log scale' },
              { value: 'linear', label: 'Linear' },
            ]}
          />
        </Tooltip>
        <Text size="xs" c="dimmed">
          {done} of {runs.length} runs finished · click a cell to open that run
        </Text>
      </Group>
      <Paper withBorder p="xs" radius="md">
        <FragilityHeatmap runs={runs} signals={used} metric={metric} scale={scale} onCellClick={(runId, signalId) => navigate(`/runs/${runId}?signal=${signalId}`)} />
      </Paper>
      <Paper withBorder p="xs" radius="md">
        <Group justify="flex-end" px="xs" pt={4}>
          {levels.length > 1 && (
            <Select
              size="xs"
              w={190}
              value={facet}
              onChange={(v) => v && setFacet(v)}
              allowDeselect={false}
              data={[{ value: 'all', label: 'All levels side by side' }, ...levels.map((l) => ({ value: l, label: `${l} only` }))]}
              aria-label="Consistency level"
            />
          )}
        </Group>
        {done === 0 ? (
          <Text size="sm" c="dimmed" p="md">
            The metric-vs-delay chart appears once at least one run has finished.
          </Text>
        ) : (
          <MetricVsDelayChart runs={runs} signals={used} metric={metric} scale={scale} levels={facet === 'all' ? levels : [facet as Consistency]} />
        )}
      </Paper>
    </Stack>
  );
}

export function ExperimentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const exp = useExperiment(id);
  const runs = useRuns(id);
  const signals = useSignals();
  const { cassandraUp } = useStoreStatus();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exporting, setExporting] = useState(false);
  const { clone, remove, launch } = useExperimentActions({ afterDelete: () => navigate('/experiments') });

  if (exp.isPending) return <LoadingState rows={8} height={36} />;
  if (exp.isError)
    return exp.error instanceof ApiError && exp.error.status === 404 ? (
      <EmptyState
        title="Experiment not found"
        message="It may have been deleted."
        action={
          <Button component={Link} to="/experiments">
            Back to experiments
          </Button>
        }
      />
    ) : (
      <ErrorState error={exp.error} onRetry={() => exp.refetch()} />
    );

  const e = exp.data.data;
  const runList = runs.data?.data ?? [];
  const active = runList.some(isActiveRun);

  const exportCsv = async () => {
    setExporting(true);
    try {
      downloadBlob(await api.exportExperimentCsv(e.id), `${e.id}.csv`);
    } catch (err) {
      notifyError(err, exportCsv);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title={e.name}
        servedBy={exp.data.servedBy}
        badges={
          <>
            <ExperimentStatusBadge status={e.status} />
            {e.tags.map((t) => (
              <Badge key={t} size="sm" variant="default" tt="none">
                {t}
              </Badge>
            ))}
          </>
        }
        subtitle={
          <>
            <Anchor component={Link} to="/experiments" size="sm">Experiments</Anchor> / <span className="mono">{e.id}</span>
          </>
        }
        actions={
          <>
            <Button variant="default" size="xs" component={Link} to={`/experiments/${e.id}/edit`}>
              Edit
            </Button>
            <Button variant="default" size="xs" onClick={() => clone.mutate(e)} loading={clone.isPending}>
              Clone
            </Button>
            <Tooltip label={active ? 'Runs from this experiment are still queued or running.' : cassandraUp ? `Queue ${gridSize(e.params)} runs` : 'Cassandra is down: runs will queue and start when it is back.'}>
              <Button size="xs" disabled={active} loading={launch.isPending} onClick={() => launch.mutate(e.id)}>
                Launch
              </Button>
            </Tooltip>
            <Button variant="default" size="xs" leftSection={<IconDownload size={14} />} onClick={exportCsv} loading={exporting} disabled={runList.length === 0}>
              Export CSV
            </Button>
            <Button variant="subtle" color="red" size="xs" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          </>
        }
      />

      {signals.isError ? <ErrorState error={signals.error} onRetry={() => signals.refetch()} title="Couldn't load signals" /> : <Summary e={e} signals={signals.data?.data ?? []} />}

      <Tabs defaultValue="results" mt="lg" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="results">Results</Tabs.Tab>
          <Tabs.Tab value="runs">Runs ({runList.length})</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="results" pt="md">
          {runs.isPending || signals.isPending ? (
            <LoadingState rows={4} height={60} />
          ) : runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => runs.refetch()} title="Couldn't load runs" />
          ) : (
            <Results e={e} runs={runList} signals={signals.data?.data ?? []} />
          )}
        </Tabs.Panel>
        <Tabs.Panel value="runs" pt="md">
          {runs.isPending ? (
            <LoadingState />
          ) : runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => runs.refetch()} title="Couldn't load runs" />
          ) : runList.length === 0 ? (
            <EmptyState title="No runs yet" message={`Launching creates ${gridSize(e.params)} runs, one per combination of settings.`} action={<Button onClick={() => launch.mutate(e.id)}>Launch</Button>} />
          ) : (
            <RunsTable runs={runList} />
          )}
        </Tabs.Panel>
      </Tabs>

      <SectionTitle> </SectionTitle>
      <Annotations targetType="experiment" targetId={e.id} />

      <ConfirmModal
        opened={confirmDelete}
        title="Delete experiment?"
        message={
          <>
            Delete <b>{e.name}</b> and all {e.run_count} of its runs and results? This cannot be undone.
          </>
        }
        loading={remove.isPending}
        onConfirm={() => remove.mutate(e)}
        onClose={() => setConfirmDelete(false)}
      />
    </>
  );
}
