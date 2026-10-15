import Plotly from 'plotly.js-dist-min';
import createPlotlyComponent from 'react-plotly.js/factory';

/** react-plotly bound to the minified Plotly bundle (keeps Vite happy and the bundle small). */
export const Plot = createPlotlyComponent(Plotly);
