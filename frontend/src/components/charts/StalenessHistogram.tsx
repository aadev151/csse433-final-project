import type { ReadingPoint, Signal } from '../../api/types';
import { useChartColors } from '../../hooks/useSignalColor';
import { axisStyle, baseLayout, plotConfig } from './layout';
import { Plot } from './Plot';

/** Distribution of how stale each reading was, for the selected signal and time range. */
export function StalenessHistogram({ signal, points }: { signal: Signal; points: ReadingPoint[] }) {
  const c = useChartColors();
  const color = c.byType(signal.type);
  return (
    <Plot
      data={[
        {
          type: 'histogram',
          x: points.map((p) => p.staleness_ms),
          marker: { color, line: { color: c.surface, width: 1 } },
          nbinsx: 40,
          hovertemplate: '%{x} ms: %{y} readings<extra></extra>',
        },
      ]}
      layout={baseLayout(c, {
        height: 300,
        margin: { l: 60, r: 20, t: 40, b: 50 },
        title: { text: `How stale ${signal.name} readings were (${points.length.toLocaleString()} sampled readings in view)` },
        bargap: 0.04,
        showlegend: false,
        xaxis: { ...axisStyle(c), title: { text: 'Staleness (ms)', font: { color: c.inkSecondary, size: 12 } } },
        yaxis: { ...axisStyle(c), title: { text: 'Readings (count)', font: { color: c.inkSecondary, size: 12 } } },
      })}
      config={{ ...plotConfig, displayModeBar: false }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
