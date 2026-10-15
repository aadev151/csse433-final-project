import type { Config, Layout } from 'plotly.js';
import type { useChartColors } from '../../hooks/useSignalColor';

type Colors = ReturnType<typeof useChartColors>;

/** Shared Plotly layout: transparent background, recessive grid, theme-aware ink. */
export function baseLayout(c: Colors, overrides: Partial<Layout> = {}): Partial<Layout> {
  const axis = {
    gridcolor: c.grid,
    linecolor: c.axis,
    zerolinecolor: c.axis,
    tickfont: { color: c.inkSecondary, size: 11 },
    title: { font: { color: c.inkSecondary, size: 12 } },
    automargin: true,
  };
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter, system-ui, sans-serif', color: c.ink, size: 12 },
    margin: { l: 60, r: 20, t: 40, b: 50 },
    hoverlabel: { bgcolor: c.surface, bordercolor: c.axis, font: { color: c.ink, size: 12 } },
    legend: { font: { color: c.inkSecondary, size: 11 }, orientation: 'h', y: -0.2 },
    title: { font: { size: 14, color: c.ink }, x: 0, xanchor: 'left', y: 0.98 },
    ...overrides,
    xaxis: { ...axis, ...(overrides.xaxis ?? {}) },
    yaxis: { ...axis, ...(overrides.yaxis ?? {}) },
  } as Partial<Layout>;
}

export function axisStyle(c: Colors) {
  return {
    gridcolor: c.grid,
    linecolor: c.axis,
    zerolinecolor: c.axis,
    tickfont: { color: c.inkSecondary, size: 11 },
    automargin: true,
  };
}

export const plotConfig: Partial<Config> = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
};
