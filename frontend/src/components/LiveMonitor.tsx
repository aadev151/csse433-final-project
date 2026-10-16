import { useMemo, useState } from 'react';
import { Alert, Badge, Group, Paper, Progress, ScrollArea, SegmentedControl, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import type { ActiveFault, Experiment, Run, RunStatus, Signal } from '../api/types';
import { useLiveRun, type LiveSeries } from '../hooks/useLiveRun';
import { useChartColors } from '../hooks/useSignalColor';
import { FAULT_COLOR } from '../lib/colors';
import { faultText, fmtMs, fmtTime } from '../lib/format';
import { orderSignals } from '../lib/metrics';
import { axisStyle, baseLayout } from './charts/layout';
import { Plot } from './charts/Plot';

export function FaultChips({ faults, emptyText = 'No faults active right now' }: { faults: ActiveFault[]; emptyText?: string }) {
  if (!faults.length)
    return (
      <Text size="xs" c="dimmed">
        {emptyText}
      </Text>
    );
  return (
    <Group gap={6}>
      {faults.map((f, i) => (
        <Badge key={i} size="sm" radius="sm" variant="light" color={FAULT_COLOR[f.kind]} tt="none" leftSection={<span style={{ width: 7, height: 7, borderRadius: 7, background: FAULT_COLOR[f.kind], display: 'inline-block' }} />}>
          {faultText(f)}
        </Badge>
      ))}
    </Group>
  );
}

function MiniChart({ signal, series, revision }: { signal: Signal; series: LiveSeries | undefined; revision: number }) {
  const c = useChartColors();
  const color = c.byType(signal.type);
  const layout = useMemo(
    () =>
      baseLayout(c, {
        height: 150,
        margin: { l: 52, r: 8, t: 26, b: 24 },
        title: { text: signal.name, font: { size: 12, color: c.ink }, x: 0.02, xanchor: 'left' },
        showlegend: false,
        xaxis: { ...axisStyle(c), type: 'date', showgrid: false, tickfont: { size: 9, color: c.inkSecondary }, nticks: 3 },
        yaxis: { ...axisStyle(c), tickfont: { size: 9, color: c.inkSecondary }, nticks: 4 },
        uirevision: signal.id,
      }),
    [c, signal],
  );
  return (
    <Paper withBorder radius="sm" p={2}>
      <Plot
        data={[
          { type: 'scatter', mode: 'lines', name: 'read value', x: series?.t ?? [], y: series?.value ?? [], line: { color, width: 1.5 }, hovertemplate: '%{y:.6g}<extra>read</extra>' },
          { type: 'scatter', mode: 'lines', name: 'truth', x: series?.t ?? [], y: series?.truth ?? [], line: { color: c.muted, width: 1.5, dash: 'dash' }, hoverinfo: 'skip' },
        ]}
        layout={{ ...layout, datarevision: revision }}
        revision={revision}
        config={{ displayModeBar: false, responsive: true, staticPlot: false }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </Paper>
  );
}

/**
 * Live view of a running run over the WebSocket: progress, active faults,
 * rolling read latency and one mini chart per signal (value vs truth).
 */
export function LiveMonitor({ run, experiment, signals, onStatus }: { run: Run; experiment: Experiment; signals: Signal[]; onStatus: (s: RunStatus) => void }) {
  const live = useLiveRun(run.id, true, { onStatus });
  const [symbol, setSymbol] = useState(experiment.symbols[0]);
  const used = orderSignals(signals.filter((s) => experiment.signal_ids.includes(s.id)));
  const progress = live.progress ?? run.progress;

  if (live.connection === 'unavailable') {
    return (
      <Alert color="yellow" variant="light" title="Live view unavailable">
        Live view unavailable while Redis is down. Results will appear when the run finishes. This page refreshes the run's progress every 5 seconds instead.
        <Group mt="sm" gap="sm" wrap="nowrap">
          <Progress value={run.progress.pct} style={{ flex: 1 }} color="yellow" />
          <Text size="xs" w={44} ta="right">
            {Math.round(run.progress.pct)}%
          </Text>
        </Group>
      </Alert>
    );
  }

  const connBadge =
    live.connection === 'open' ? (
      <Badge color="green" variant="dot" tt="none">
        live
      </Badge>
    ) : live.connection === 'reconnecting' ? (
      <Badge color="yellow" variant="dot" tt="none">
        reconnecting{live.retryIn !== null ? ` in ${live.retryIn}s` : '…'}
      </Badge>
    ) : (
      <Badge color="gray" variant="dot" tt="none">
        connecting…
      </Badge>
    );

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={600}>Live monitor</Text>
            {connBadge}
          </Group>
          <Group gap="lg">
            <Tooltip label="Median read latency over the last 10 seconds of live readings">
              <Text size="sm">
                Read latency p50 (10 s):{' '}
                <Text span fw={600}>
                  {fmtMs(live.latencyP50)}
                </Text>
              </Text>
            </Tooltip>
            {experiment.symbols.length > 1 && <SegmentedControl size="xs" data={experiment.symbols} value={symbol} onChange={(v) => setSymbol(v as typeof symbol)} />}
          </Group>
        </Group>
        <Group gap="sm" wrap="nowrap">
          <Progress value={progress.pct} style={{ flex: 1 }} animated />
          <Text size="xs" w={44} ta="right">
            {progress.pct.toFixed(1)}%
          </Text>
        </Group>
        <Text size="xs" c="dimmed">
          Replayed until <span className="mono">{fmtTime(progress.replayed_until)}</span> UTC
        </Text>
        <Group gap="xs" align="center">
          <Text size="xs" fw={600}>
            Active faults:
          </Text>
          <FaultChips faults={live.faults} />
        </Group>
        <ScrollArea.Autosize mah={used.length > 8 ? 2 * 160 + 16 : undefined} type="auto">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="xs">
            {used.map((s) => (
              <MiniChart key={s.id} signal={s} series={live.series[`${s.id}|${symbol}`]} revision={live.revision} />
            ))}
          </SimpleGrid>
        </ScrollArea.Autosize>
        <Text size="xs" c="dimmed">
          Solid = value read from Cassandra (blue latest-value, orange running-total) · dashed gray = ground truth · last {600} readings per signal.
        </Text>
      </Stack>
    </Paper>
  );
}
