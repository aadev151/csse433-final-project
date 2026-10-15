import { useMemo } from 'react';
import type { Annotation as Annotations, Data, Shape } from 'plotly.js';
import type { Run, Signal } from '../../api/types';
import { useChartColors } from '../../hooks/useSignalColor';
import { SEQUENTIAL_BLUE } from '../../lib/colors';
import { compareConfigs, configLabel } from '../../lib/grid';
import { fmtMetric, metricLabel, metricValue, orderSignals, reportTooltip, type MetricKey } from '../../lib/metrics';
import { baseLayout, plotConfig } from './layout';
import { Plot } from './Plot';

interface Props {
  runs: Run[];
  signals: Signal[];
  metric: MetricKey;
  scale: 'log' | 'linear';
  onCellClick: (runId: string, signalId: string) => void;
}

/**
 * Rows = signals (latest-value block, then running-total block), columns = run
 * configs ordered by consistency then delay. Unfinished runs are gray "pending".
 */
export function FragilityHeatmap({ runs, signals, metric, scale, onCellClick }: Props) {
  const c = useChartColors();
  const rows = useMemo(() => orderSignals(signals), [signals]);
  const cols = useMemo(() => [...runs].sort((a, b) => compareConfigs(a.config, b.config)), [runs]);

  const { trace, annotations, shapes, height, tickText } = useMemo(() => {
    const m = metricLabel(metric);
    const raw: (number | null)[][] = [];
    const text: string[][] = [];
    const hover: string[][] = [];
    let min = Infinity;
    let max = -Infinity;
    for (const s of rows) {
      const zr: (number | null)[] = [];
      const tr: string[] = [];
      const hr: string[] = [];
      for (const r of cols) {
        const rep = r.status === 'done' ? r.report?.[s.id] : undefined;
        const header = `${configLabel(r.config)} · <i>click to open run</i>`;
        if (rep) {
          const v = metricValue(metric, rep);
          zr.push(v);
          if (v > 0) min = Math.min(min, v);
          max = Math.max(max, v);
          tr.push(fmtMetric(metric, rep[metric]));
          hr.push(reportTooltip(s, rep, header));
        } else {
          zr.push(null);
          tr.push(r.status === 'failed' || r.status === 'cancelled' ? r.status : 'pending');
          hr.push(`<b>${s.name}</b><br>${configLabel(r.config)}<br>run ${r.status.replace(/_/g, ' ')} — no report yet`);
        }
      }
      raw.push(zr);
      text.push(tr);
      hover.push(hr);
    }
    if (!Number.isFinite(min)) min = 1e-6;
    if (!Number.isFinite(max)) max = 1;
    const useLog = scale === 'log' && max / min > 20;
    const z = raw.map((r) => r.map((v) => (v === null ? null : useLog ? Math.log10(Math.max(v, min)) : v)));
    const zmin = useLog ? Math.log10(min) : 0;
    const zmax = useLog ? Math.log10(max) : max;
    const ticks: number[] = [];
    if (useLog) for (let e = Math.ceil(zmin); e <= Math.floor(zmax); e++) ticks.push(e);

    const unit = metric === 'wrong_call_rate' ? '%' : metric === 'avg_error' ? '' : ' ms';
    const fmtTick = (v: number) => {
      const x = 10 ** v;
      return `${x >= 1 ? +x.toPrecision(3) : x.toPrecision(1)}${unit}`;
    };

    const tickText = rows.map((s) => `<span style="color:${c.byType(s.type)}">■</span> ${s.name}`);
    const trace: Data = {
      type: 'heatmap',
      z,
      x: cols.map((_, i) => i),
      y: rows.map((_, i) => i),
      text,
      customdata: hover as unknown as string[],
      texttemplate: '%{text}',
      textfont: { size: 11 },
      hovertemplate: '%{customdata}<extra></extra>',
      colorscale: SEQUENTIAL_BLUE,
      zmin,
      zmax: zmax === zmin ? zmin + 1 : zmax,
      xgap: 2,
      ygap: 2,
      hoverongaps: true,
      colorbar: {
        title: { text: m.label + (useLog ? ' (log)' : ''), side: 'right', font: { color: c.inkSecondary, size: 11 } },
        tickfont: { color: c.inkSecondary, size: 10 },
        thickness: 12,
        outlinewidth: 0,
        ...(useLog ? { tickvals: ticks, ticktext: ticks.map(fmtTick) } : {}),
      },
    } as Data;

    const nLatest = rows.filter((s) => s.type === 'latest-value').length;
    const shapes: Partial<Shape>[] = [];
    const annotations: Partial<Annotations>[] = [];
    if (nLatest > 0 && nLatest < rows.length) {
      shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: nLatest - 0.5, y1: nLatest - 0.5, line: { color: c.ink, width: 2 } });
    }
    const blocks: [string, number, number, string][] = [
      ['latest-value', 0, nLatest - 1, c.latest],
      ['running-total', nLatest, rows.length - 1, c.running],
    ];
    for (const [label, a, b, color] of blocks) {
      if (b < a) continue;
      annotations.push({
        xref: 'paper',
        x: 1.0,
        xanchor: 'left',
        xshift: 6,
        yref: 'y',
        y: (a + b) / 2,
        text: `<b>${label}</b>`,
        textangle: 90,
        showarrow: false,
        font: { color, size: 11 },
      });
    }
    // pending cells get a neutral gray background via shapes under the heatmap
    raw.forEach((r, yi) =>
      r.forEach((v, xi) => {
        if (v === null)
          shapes.push({ type: 'rect', layer: 'below', xref: 'x', yref: 'y', x0: xi - 0.5 + 0.03, x1: xi + 0.5 - 0.03, y0: yi - 0.5 + 0.04, y1: yi + 0.5 - 0.04, fillcolor: c.pending, line: { width: 0 } });
      }),
    );
    // gray "pending" text: draw via annotations since null cells have no texttemplate
    raw.forEach((r, yi) =>
      r.forEach((v, xi) => {
        if (v === null) annotations.push({ x: xi, y: yi, xref: 'x', yref: 'y', text: text[yi][xi], showarrow: false, font: { size: 10, color: c.muted } });
      }),
    );

    return { trace, annotations, shapes, tickText, height: Math.max(260, rows.length * 34 + 170) };
  }, [rows, cols, metric, scale, c]);

  const layout = baseLayout(c, {
    height,
    margin: { l: 10, r: 40, t: 36, b: 10 },
    title: { text: `Fragility: ${metricLabel(metric).label.toLowerCase()} per signal and run configuration` },
    xaxis: {
      tickvals: cols.map((_, i) => i),
      ticktext: cols.map((r) => configLabel(r.config, { compact: true })),
      tickangle: -45,
      side: 'bottom',
      showgrid: false,
      zeroline: false,
      title: { text: 'Run configuration (consistency · network delay · other faults)' },
    },
    yaxis: {
      tickvals: rows.map((_, i) => i),
      ticktext: tickText,
      autorange: 'reversed',
      showgrid: false,
      zeroline: false,
      title: { text: 'Signal' },
    },
    shapes,
    annotations,
  });

  return (
    <Plot
      data={[trace]}
      layout={layout}
      config={{ ...plotConfig, displayModeBar: false }}
      style={{ width: '100%' }}
      useResizeHandler
      onClick={(ev) => {
        const p = ev.points?.[0];
        if (!p) return;
        const run = cols[Number(p.x)];
        const sig = rows[Number(p.y)];
        if (run && sig) onCellClick(run.id, sig.id);
      }}
    />
  );
}
