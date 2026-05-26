import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { base } from '../theme';

// Observer plots overlay 4 traces per axis (measured + i1/im/ic). The shared
// PALETTE only carries 3 colors, so add a local fourth for ic_hat.
const IC_COLOR = '#2F7FB5';
const OBSERVER_COLORS = [PALETTE[0], PALETTE[1], PALETTE[2], IC_COLOR] as const;
import { stackedGrid } from '../subplotLayout';
import type { FigureBuilder } from './types';
import { buildFftFigure } from './fftHelpers';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

// -----------------------------------------------------------------------------
// Observer tab — LCL state-observer estimates per dq axis. Top panel d-axis
// (i_d_meas vs estimated i1/im/ic), bottom panel q-axis. The estimated
// capacitor current ic_hat = i1_hat - im_hat is the load-bearing signal for
// future active LCL damping. Tab is gated on filterEnabled upstream.
// -----------------------------------------------------------------------------
export const buildObserverTime: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const id_meas = col(table, 'i_d_meas');
  const i1_d = col(table, 'i1_d_hat');
  const im_d = col(table, 'im_d_hat');
  const ic_d = col(table, 'ic_d_hat');
  const iq_meas = col(table, 'i_q_meas');
  const i1_q = col(table, 'i1_q_hat');
  const im_q = col(table, 'im_q_hat');
  const ic_q = col(table, 'ic_q_hat');

  const layout = stackedGrid({
    count: 2,
    titles: ['d-axis observer (i_d_meas vs estimated states)', 'q-axis observer (i_q_meas vs estimated states)'],
    yLabels: ['i [A]', 'i [A]'],
  });

  const line = (gi: number, name: string, data: [number, number][], color: string, width = 1.0): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    data,
    showSymbol: false,
    sampling: 'lttb',
    lineStyle: { color, width },
  });

  const option: EChartsOption = {
    ...base,
    title: layout.title,
    grid: layout.grid,
    xAxis: layout.xAxis,
    yAxis: layout.yAxis,
    axisPointer: layout.axisPointer,
    dataZoom: layout.dataZoom,
    legend: { top: 0, right: 8, textStyle: { fontSize: 13 } },
    series: [
      line(0, 'i_d_meas', xyPairs(t, id_meas), OBSERVER_COLORS[0], 1.4),
      line(0, 'i1_d_hat', xyPairs(t, i1_d), OBSERVER_COLORS[1]),
      line(0, 'im_d_hat', xyPairs(t, im_d), OBSERVER_COLORS[2]),
      line(0, 'ic_d_hat', xyPairs(t, ic_d), OBSERVER_COLORS[3]),
      line(1, 'i_q_meas', xyPairs(t, iq_meas), OBSERVER_COLORS[0], 1.4),
      line(1, 'i1_q_hat', xyPairs(t, i1_q), OBSERVER_COLORS[1]),
      line(1, 'im_q_hat', xyPairs(t, im_q), OBSERVER_COLORS[2]),
      line(1, 'ic_q_hat', xyPairs(t, ic_q), OBSERVER_COLORS[3]),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// FFT of the estimated capacitor currents — energy near LCL resonance is what
// active damping would target.
export const buildObserverFft = buildFftFigure([
  { title: 'FFT(ic_d_hat) — estimated capacitor current, d-axis', yLabel: 'mag [A, norm]', traces: [{ signalCol: 'ic_d_hat', name: '|FFT(ic_d_hat)|' }] },
  { title: 'FFT(ic_q_hat) — estimated capacitor current, q-axis', yLabel: 'mag [A, norm]', traces: [{ signalCol: 'ic_q_hat', name: '|FFT(ic_q_hat)|' }] },
]);
