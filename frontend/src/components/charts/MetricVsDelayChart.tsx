import { useMemo } from 'react';
import type { Data, Layout } from 'plotly.js';
import { CONSISTENCY_LEVELS, type Consistency, type Run, type Signal } from '../../api/types';
import { useChartColors } from '../../hooks/useSignalColor';
import { fmtMetric, metricLabel, metricValue, orderSignals, type MetricKey } from '../../lib/metrics';
import { axisStyle, baseLayout, plotConfig } from './layout';
import { Plot } from './Plot';

const DASHES = ['solid', 'dash', 'dot', 'dashdot', 'longdash', 'longdashdot'];
const SYMBOLS = ['circle', 'square', 'diamond', 'triangle-up', 'x', 'star'];

interface Props {
  runs: Run[];
  signals: Signal[];
  metric: MetricKey;
  /** Which consistency levels to draw; more than one draws side-by-side facets. */
  levels: Consistency[];
  scale: 'log' | 'linear';
}

/**
 * Selected metric vs network delay, one line per signal coloured by signal
 * type, faceted by consistency level. Runs that share (consistency, delay) but
 * differ in other settings are averaged.
 */
export function MetricVsDelayChart({ runs, signals, metric, levels, scale }: Props) {
  const c = useChartColors();
  const ordered = useMemo(() => orderSignals(signals), [signals]);

  const { data, layout } = useMemo(() => {
    const done = runs.filter((r) => r.status === 'done' && r.report);
    const delays = [...new Set(runs.map((r) => r.config.delay_ms))].sort((a, b) => a - b);
    const facets = CONSISTENCY_LEVELS.filter((l) => levels.includes(l));
    const n = Math.max(1, facets.length);
    const gap = 0.04;
    const w = (1 - gap * (n - 1)) / n;
    const data: Data[] = [];
    const typeIdx: Record<string, number> = { 'latest-value': 0, 'running-total': 0 };
    const style = new Map(ordered.map((s) => [s.id, typeIdx[s.type]++]));

    facets.forEach((level, fi) => {
      const xa = fi === 0 ? 'x' : `x${fi + 1}`;
      for (const s of ordered) {
        const i = style.get(s.id) ?? 0;
        const ys = delays.map((d) => {
          const vals = done
            .filter((r) => r.config.consistency === level && r.config.delay_ms === d && r.report?.[s.id])
            .map((r) => metricValue(metric, r.report![s.id]));
          return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
        });
        data.push({
          type: 'scatter',
          mode: 'lines+markers',
          name: s.name,
          legendgroup: s.id,
          showlegend: fi === 0,
          x: delays.map(String),
          y: ys,
          xaxis: xa,
          yaxis: 'y',
          connectgaps: false,
          line: { color: c.byType(s.type), width: 2, dash: DASHES[i % DASHES.length] as 'solid' },
          marker: { color: c.byType(s.type), size: 8, symbol: SYMBOLS[i % SYMBOLS.length], line: { color: c.surface, width: 1.5 } },
          hovertemplate: `<b>${s.name}</b> (${s.type})<br>${level} · %{x} ms delay<br>${metricLabel(metric).label}: %{customdata}<extra></extra>`,
          customdata: ys.map((y) => (y === null ? 'no data' : fmtMetric(metric, metric === 'wrong_call_rate' ? y / 100 : y))),
        } as Data);
      }
    });

    const layout: Partial<Layout> = baseLayout(c, {
      height: 380,
      margin: { l: 60, r: 10, t: 56, b: 60 },
      title: { text: `${metricLabel(metric).label} vs network delay, by signal (blue = latest-value, orange = running-total)` },
      legend: { orientation: 'v', x: 1.01, y: 1, font: { color: c.inkSecondary, size: 11 } },
      hovermode: 'closest',
      yaxis: { ...axisStyle(c), type: scale === 'log' ? 'log' : 'linear', title: { text: metricLabel(metric).axis, font: { color: c.inkSecondary, size: 12 } } },
      annotations: facets.map((level, fi) => ({
        xref: 'paper',
        yref: 'paper',
        x: fi * (w + gap) + w / 2,
        y: 1.0,
        yanchor: 'bottom',
        text: `<b>${level}</b>`,
        showarrow: false,
        font: { size: 12, color: c.ink },
      })),
    });
    facets.forEach((_, fi) => {
      const key = fi === 0 ? 'xaxis' : `xaxis${fi + 1}`;
      (layout as Record<string, unknown>)[key] = {
        ...axisStyle(c),
        type: 'category',
        domain: [fi * (w + gap), fi * (w + gap) + w],
        anchor: 'y',
        title: { text: 'Network delay (ms)', font: { color: c.inkSecondary, size: 12 } },
      };
    });
    return { data, layout };
  }, [runs, ordered, metric, levels, scale, c]);

  return <Plot data={data} layout={layout} config={{ ...plotConfig, displayModeBar: false }} style={{ width: '100%' }} useResizeHandler />;
}
