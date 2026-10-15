import { useEffect, useMemo, useState } from 'react';
import { Alert, Anchor, Badge, Button, Grid, Group, Paper, Select, Stack, Table, Text, Tooltip } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { ApiError, isCassandraDown } from '../api/client';
import type { Run, Signal, SignalReport } from '../api/types';
import { Annotations } from '../components/Annotations';
import { ConfirmModal } from '../components/ConfirmModal';
import { Mono, RunStatusBadge, SignalTypeBadge } from '../components/badges';
import { ReadingsChart } from '../components/charts/ReadingsChart';
import { StalenessHistogram } from '../components/charts/StalenessHistogram';
import { IconDownload } from '../components/icons';
import { LiveMonitor } from '../components/LiveMonitor';
import { EmptyState, ErrorState, LoadingState, PageHeader, SectionTitle } from '../components/states';
import { isActiveRun, qk, useExperiment, useSignals } from '../hooks/queries';
import { useStoreStatus } from '../hooks/useHealth';
import { useWriteMutation } from '../hooks/useWriteMutation';
import { downloadBlob, fmtDuration, fmtInt, fmtMs, fmtPct, fmtTime } from '../lib/format';
import { fmtMetric, orderSignals } from '../lib/metrics';
import { notifyError } from '../lib/notify';

const CASSANDRA_DOWN_TEXT = 'Step-by-step readings are stored only in Cassandra and are unavailable while it is down. The summary below is still available.';

type SortKey = 'name' | 'type' | keyof SignalReport;
const COLS: { key: SortKey; label: string; fmt?: (r: SignalReport) => string }[] = [
  { key: 'name', label: 'Signal' },
  { key: 'type', label: 'Type' },
  { key: 'avg_error', label: 'Avg error', fmt: (r) => fmtMetric('avg_error', r.avg_error) },
  { key: 'max_error', label: 'Max error', fmt: (r) => fmtMetric('avg_error', r.max_error) },
  { key: 'wrong_call_rate', label: 'Wrong-call rate', fmt: (r) => fmtPct(r.wrong_call_rate, 2) },
  { key: 'staleness_p50_ms', label: 'Staleness p50', fmt: (r) => fmtMs(r.staleness_p50_ms) },
  { key: 'staleness_p99_ms', label: 'Staleness p99', fmt: (r) => fmtMs(r.staleness_p99_ms) },
  { key: 'latency_p50_ms', label: 'Latency p50', fmt: (r) => fmtMs(r.latency_p50_ms) },
  { key: 'latency_p99_ms', label: 'Latency p99', fmt: (r) => fmtMs(r.latency_p99_ms) },
  { key: 'readings_count', label: 'Readings', fmt: (r) => fmtInt(r.readings_count) },
];

function ReportTable({ run, signals, onPick }: { run: Run; signals: Signal[]; onPick: (id: string) => void }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'type', dir: 1 });
  const rows = useMemo(() => {
    const list = orderSignals(signals)
      .filter((s) => run.report?.[s.id])
      .map((s) => ({ s, r: run.report![s.id] }));
    const val = (x: (typeof list)[number]) => (sort.key === 'name' ? x.s.name : sort.key === 'type' ? x.s.type : x.r[sort.key]);
    return list.sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb));
      return cmp * sort.dir || a.s.name.localeCompare(b.s.name);
    });
  }, [run.report, signals, sort]);

  if (!run.report)
    return (
      <EmptyState
        title="No report yet"
        message={run.status === 'failed' || run.status === 'cancelled' ? `This run ${run.status} before producing a report.` : 'The per-signal summary is computed when the run finishes.'}
      />
    );

  const toggle = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === 'name' || key === 'type' ? 1 : -1 }));
  return (
    <Table.ScrollContainer minWidth={1000}>
      <Table highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            {COLS.map((c) => (
              <Table.Th key={c.key} className={`sort-th ${c.fmt ? 'num' : ''}`} onClick={() => toggle(c.key)} aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                {c.label}
                {sort.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map(({ s, r }) => (
            <Table.Tr key={s.id} className="clickable-row" onClick={() => onPick(s.id)}>
              <Table.Td fw={500}>{s.name}</Table.Td>
              <Table.Td>
                <SignalTypeBadge type={s.type} size="xs" />
              </Table.Td>
              {COLS.slice(2).map((c) => (
                <Table.Td key={c.key} className="num">
                  {c.fmt!(r)}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

function ReadingsExplorer({ run, signals, symbols, signalId, setSignalId }: { run: Run; signals: Signal[]; symbols: string[]; signalId: string | null; setSignalId: (id: string) => void }) {
  const [symbol, setSymbol] = useState(symbols[0]);
  const [range, setRange] = useState<[string, string] | null>(null);
  const [debounced] = useDebouncedValue(range, 400);
  const signal = signals.find((s) => s.id === signalId) ?? null;
  const live = run.status === 'running';

  useEffect(() => setRange(null), [signalId, symbol]);

  const readings = useQuery({
    queryKey: ['readings', run.id, signalId, symbol, debounced?.[0] ?? null, debounced?.[1] ?? null],
    queryFn: () => api.getReadings(run.id, { signal_id: signalId!, symbol, from: debounced?.[0], to: debounced?.[1], max_points: 2000 }),
    enabled: !!signalId && !!symbol,
    placeholderData: keepPreviousData,
    refetchInterval: live && !debounced ? 10_000 : false,
    retry: false,
  });
  const faults = useQuery({ queryKey: qk.faults(run.id), queryFn: () => api.getFaults(run.id), refetchInterval: live ? 10_000 : false });

  const signalOptions = [
    { group: 'latest-value', items: signals.filter((s) => s.type === 'latest-value').map((s) => ({ value: s.id, label: s.name })) },
    { group: 'running-total', items: signals.filter((s) => s.type === 'running-total').map((s) => ({ value: s.id, label: s.name })) },
  ].filter((g) => g.items.length);

  const notStarted = run.status === 'queued' || run.status === 'waiting_for_cassandra';

  return (
    <Stack gap="sm">
      <Group gap="sm" align="flex-end">
        <Select label="Signal" data={signalOptions} value={signalId} onChange={(v) => v && setSignalId(v)} w={260} size="sm" allowDeselect={false} />
        <Select label="Symbol" data={symbols} value={symbol} onChange={(v) => v && setSymbol(v)} w={140} size="sm" allowDeselect={false} />
        {signal && <SignalTypeBadge type={signal.type} />}
        {range && (
          <Button size="xs" variant="subtle" onClick={() => setRange(null)}>
            Reset zoom
          </Button>
        )}
        {readings.isFetching && !readings.isPending && (
          <Text size="xs" c="dimmed">
            loading…
          </Text>
        )}
      </Group>
      {!signal ? (
        <EmptyState title="Pick a signal" message="Choose a signal to explore its step-by-step readings." />
      ) : notStarted ? (
        <EmptyState title="No readings yet" message="This run has not started. Readings appear here as soon as it is replaying." />
      ) : readings.isError && isCassandraDown(readings.error) ? (
        <Alert color="yellow" variant="light" title="Readings unavailable while Cassandra is down">
          {CASSANDRA_DOWN_TEXT}
        </Alert>
      ) : readings.isError ? (
        <ErrorState error={readings.error} onRetry={() => readings.refetch()} title="Couldn't load readings" />
      ) : readings.isPending ? (
        <LoadingState rows={1} height={480} />
      ) : readings.data.data.points.length === 0 ? (
        <EmptyState title="No readings in this range" message="Zoom out or reset the zoom to see readings." action={<Button variant="default" onClick={() => setRange(null)}>Reset zoom</Button>} />
      ) : (
        <>
          <Paper withBorder p="xs" radius="md">
            <ReadingsChart signal={signal} symbol={symbol} points={readings.data.data.points} faults={faults.data?.data ?? []} onRangeChange={setRange} />
            <Text size="xs" c="dimmed" px="xs">
              Shaded bands are injected faults. Drag on the chart or the range slider to zoom; the server returns up to 2,000 points for the visible range.
            </Text>
          </Paper>
          <Paper withBorder p="xs" radius="md">
            <StalenessHistogram signal={signal} points={readings.data.data.points} />
          </Paper>
        </>
      )}
    </Stack>
  );
}

export function RunDetailPage() {
  const { id = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const { redisUp } = useStoreStatus();
  const run = useQuery({
    queryKey: qk.run(id),
    queryFn: () => api.getRun(id),
    // the live socket carries progress; without Redis fall back to polling every 5 s
    refetchInterval: (q) => (q.state.data && isActiveRun(q.state.data.data) ? (redisUp ? 10_000 : 5_000) : false),
  });
  const exp = useExperiment(run.data?.data.experiment_id);
  const signals = useSignals();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [exporting, setExporting] = useState(false);

  const cancel = useWriteMutation({
    mutationFn: () => api.cancelRun(id),
    action: 'Run cancelled',
    invalidate: [qk.run(id), ['runs'], ['queue'], ['experiment']],
    onSuccess: () => setConfirmCancel(false),
  });

  if (run.isPending) return <LoadingState rows={8} height={36} />;
  if (run.isError)
    return run.error instanceof ApiError && run.error.status === 404 ? (
      <EmptyState title="Run not found" message="It may have been deleted with its experiment." action={<Button component={Link} to="/experiments">Back to experiments</Button>} />
    ) : (
      <ErrorState error={run.error} onRetry={() => run.refetch()} />
    );

  const r = run.data.data;
  const e = exp.data?.data;
  const used = orderSignals((signals.data?.data ?? []).filter((s) => !e || e.signal_ids.includes(s.id)));
  const signalId = params.get('signal') ?? used[0]?.id ?? null;
  const setSignalId = (sid: string) => setParams((p) => (p.set('signal', sid), p), { replace: true });
  const cancellable = isActiveRun(r);
  const duration = r.started_at ? (r.finished_at ? Date.parse(r.finished_at) : Date.now()) - Date.parse(r.started_at) : 0;

  const exportCsv = async () => {
    setExporting(true);
    try {
      downloadBlob(await api.exportRunCsv(r.id), `${r.id}.csv`);
    } catch (err) {
      notifyError(isCassandraDown(err) ? new Error('Readings live in Cassandra, which is down. Try the export again when it is back.') : err, exportCsv);
    } finally {
      setExporting(false);
    }
  };

  const chips = [
    r.config.consistency,
    `delay ${r.config.delay_ms} ms`,
    `loss ${r.config.packet_loss_pct}%`,
    `skew ${r.config.clock_skew_ms} ms`,
    r.config.node_outage === 'one_node_down' ? 'one node down' : 'all nodes up',
  ];

  return (
    <>
      <PageHeader
        title={
          <>
            Run <span className="mono" style={{ fontSize: 18 }}>{r.id}</span>
          </>
        }
        servedBy={run.data.servedBy}
        badges={<RunStatusBadge run={r} />}
        subtitle={
          <>
            <Anchor component={Link} to="/experiments" size="sm">
              Experiments
            </Anchor>{' '}
            /{' '}
            <Anchor component={Link} to={`/experiments/${r.experiment_id}`} size="sm">
              {e?.name ?? r.experiment_id}
            </Anchor>
          </>
        }
        actions={
          <>
            {cancellable && (
              <Button size="xs" variant="light" color="red" onClick={() => setConfirmCancel(true)}>
                Cancel run
              </Button>
            )}
            <Button size="xs" variant="default" leftSection={<IconDownload size={14} />} onClick={exportCsv} loading={exporting}>
              Export CSV
            </Button>
          </>
        }
      />

      <Paper withBorder p="sm" radius="md" mb="md">
        <Grid align="center">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Group gap={6}>
              {chips.map((c) => (
                <Badge key={c} variant="default" size="md" radius="sm" tt="none">
                  {c}
                </Badge>
              ))}
              <Tooltip label="Replication factor (fixed)">
                <Badge variant="default" size="md" radius="sm" tt="none" c="dimmed">
                  RF 3
                </Badge>
              </Tooltip>
            </Group>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Group gap="lg" justify="flex-end">
              <Stack gap={0}>
                <Text size="xs" c="dimmed">
                  Started (UTC)
                </Text>
                <Mono>{fmtTime(r.started_at)}</Mono>
              </Stack>
              <Stack gap={0}>
                <Text size="xs" c="dimmed">
                  Finished (UTC)
                </Text>
                <Mono>{fmtTime(r.finished_at)}</Mono>
              </Stack>
              <Stack gap={0}>
                <Text size="xs" c="dimmed">
                  Duration
                </Text>
                <Text size="sm">{r.started_at ? fmtDuration(duration) : '—'}</Text>
              </Stack>
            </Group>
          </Grid.Col>
        </Grid>
        {r.error && (
          <Alert color="red" variant="light" mt="sm" title="Run failed">
            {r.error}
          </Alert>
        )}
      </Paper>

      {r.status === 'running' && e && signals.data && (
        <LiveMonitor
          run={r}
          experiment={e}
          signals={signals.data.data}
          onStatus={(s) => {
            if (s !== 'running') {
              qc.invalidateQueries({ queryKey: qk.run(r.id) });
              qc.invalidateQueries({ queryKey: ['runs'] });
            }
          }}
        />
      )}
      {r.status === 'queued' && (
        <Alert color="gray" variant="light" title="Queued">
          This run is #{r.queue_position ?? '?'} in the <Anchor component={Link} to="/queue">queue</Anchor>. It starts automatically.
        </Alert>
      )}
      {r.status === 'waiting_for_cassandra' && (
        <Alert color="yellow" variant="light" title="Waiting for Cassandra">
          Runs are waiting for Cassandra to come back. They will start automatically{r.progress.pct > 0 ? ` (this one resumes from ${Math.round(r.progress.pct)}%)` : ''}.
        </Alert>
      )}

      <SectionTitle>Report</SectionTitle>
      {signals.isPending ? <LoadingState rows={4} /> : signals.isError ? <ErrorState error={signals.error} onRetry={() => signals.refetch()} /> : <ReportTable run={r} signals={used} onPick={setSignalId} />}

      <SectionTitle>Readings explorer</SectionTitle>
      {signals.isPending || exp.isPending ? (
        <LoadingState rows={1} height={400} />
      ) : exp.isError ? (
        <ErrorState error={exp.error} onRetry={() => exp.refetch()} title="Couldn't load the experiment for this run" />
      ) : (
        <ReadingsExplorer run={r} signals={used} symbols={e?.symbols ?? []} signalId={signalId} setSignalId={setSignalId} />
      )}

      <SectionTitle> </SectionTitle>
      <Annotations targetType="run" targetId={r.id} />

      <ConfirmModal
        opened={confirmCancel}
        title="Cancel this run?"
        message="The run stops and keeps no report. You can launch the experiment again later."
        confirmLabel="Cancel run"
        loading={cancel.isPending}
        onConfirm={() => cancel.mutate(undefined)}
        onClose={() => setConfirmCancel(false)}
      />
    </>
  );
}
