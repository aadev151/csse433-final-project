import { useMemo } from 'react';
import type { Annotation, Data, Layout, Shape } from 'plotly.js';
import type { FaultWindow, ReadingPoint, Signal } from '../../api/types';
import { useChartColors } from '../../hooks/useSignalColor';
import { FAULT_COLOR, FAULT_LABEL } from '../../lib/colors';
import { axisStyle, baseLayout, plotConfig } from './layout';
import { Plot } from './Plot';

/** Plotly gives relayout ranges as "YYYY-MM-DD HH:mm:ss.sss" in the axis' (UTC) time. */
function plotlyTimeToIso(v: string | number): string {
  if (typeof v === 'number') return new Date(v).toISOString();
  const s = v.includes('T') ? v : v.replace(' ', 'T');
  return new Date(s.endsWith('Z') ? s : `${s}Z`).toISOString();
}

interface Props {
  signal: Signal;
  symbol: string;
  points: ReadingPoint[];
  faults: FaultWindow[];
  onRangeChange: (range: [string, string] | null) => void;
}

/**
 * Top: value (solid, signal-type colour) vs truth (dashed neutral) over time.
 * Bottom: error = value − truth on a shared x axis. Fault windows are shaded.
 */
export function ReadingsChart({ signal, symbol, points, faults, onRangeChange }: Props) {
  const c = useChartColors();
  const color = c.byType(signal.type);

  const { data, layout } = useMemo(() => {
    const t = points.map((p) => p.t);
    const data: Data[] = [
      { type: 'scatter', mode: 'lines', name: 'value read', x: t, y: points.map((p) => p.value), line: { color, width: 1.5 }, hovertemplate: 'read %{y:.6g}<extra></extra>' },
      { type: 'scatter', mode: 'lines', name: 'truth', x: t, y: points.map((p) => p.truth), line: { color: c.muted, width: 1.5, dash: 'dash' }, hovertemplate: 'truth %{y:.6g}<extra></extra>' },
      {
        type: 'scatter',
        mode: 'lines',
        name: 'error (value − truth)',
        x: t,
        y: points.map((p) => p.value - p.truth),
        yaxis: 'y2',
        line: { color, width: 1 },
        fill: 'tozeroy',
        fillcolor: `${color}33`,
        hovertemplate: 'error %{y:.4g}<extra></extra>',
      },
    ];

    const shapes: Partial<Shape>[] = [];
    const annotations: Partial<Annotation>[] = [];
    const labelled = new Set<string>();
    const kindRow = [...new Set(faults.map((f) => f.kind))];
    for (const f of faults) {
      shapes.push({ type: 'rect', xref: 'x', yref: 'paper', x0: f.start, x1: f.end, y0: 0, y1: 1, fillcolor: FAULT_COLOR[f.kind], opacity: 0.12, line: { width: 0 }, layer: 'below' });
      const key = `${f.kind}|${f.start}`;
      if (labelled.has(key)) continue;
      labelled.add(key);
      const v = f.value === null ? '' : f.kind === 'packet_loss' ? ` ${f.value}%` : ` ${f.value} ms`;
      annotations.push({
        xref: 'x',
        yref: 'paper',
        x: f.start,
        y: 1,
        xanchor: 'left',
        yanchor: 'top',
        xshift: 3,
        yshift: -2 - 13 * kindRow.indexOf(f.kind),
        text: `${FAULT_LABEL[f.kind]}${v} · ${f.target}`,
        showarrow: false,
        font: { size: 10, color: FAULT_COLOR[f.kind] },
      });
    }

    const layout: Partial<Layout> = baseLayout(c, {
      height: 520,
      margin: { l: 70, r: 20, t: 80, b: 20 },
      title: { text: `${signal.name} on ${symbol}: value read vs ground truth, and the error between them`, y: 0.985 },
      legend: { orientation: 'h', x: 1, xanchor: 'right', y: 1.1, font: { color: c.inkSecondary, size: 11 } },
      hovermode: 'x unified',
      uirevision: `${signal.id}|${symbol}`,
      shapes,
      annotations,
      xaxis: { ...axisStyle(c), type: 'date', title: { text: 'Replay time (UTC)', font: { color: c.inkSecondary, size: 12 } }, rangeslider: { visible: true, thickness: 0.07, bgcolor: c.surface, bordercolor: c.axis } },
      yaxis: { ...axisStyle(c), domain: [0.42, 1], title: { text: `${signal.name} (signal units)`, font: { color: c.inkSecondary, size: 12 } } },
      yaxis2: { ...axisStyle(c), domain: [0, 0.32], title: { text: 'Error (value − truth)', font: { color: c.inkSecondary, size: 12 } }, zeroline: true, zerolinecolor: c.axis },
    } as Partial<Layout>);
    return { data, layout };
  }, [points, faults, c, color, signal, symbol]);

  return (
    <Plot
      data={data}
      layout={layout}
      config={plotConfig}
      style={{ width: '100%' }}
      useResizeHandler
      onRelayout={(ev) => {
        const e = ev as Record<string, unknown>;
        if (e['xaxis.autorange']) return onRangeChange(null);
        const a = (e['xaxis.range[0]'] ?? (e['xaxis.range'] as unknown[] | undefined)?.[0]) as string | undefined;
        const b = (e['xaxis.range[1]'] ?? (e['xaxis.range'] as unknown[] | undefined)?.[1]) as string | undefined;
        if (a !== undefined && b !== undefined) onRangeChange([plotlyTimeToIso(a), plotlyTimeToIso(b)]);
      }}
    />
  );
}
