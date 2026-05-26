import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { base } from '../theme';
import { stackedGrid } from '../subplotLayout';
import type { FigureBuilder } from './types';
import { buildFftFigure } from './fftHelpers';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

// -----------------------------------------------------------------------------
// Signal-Processing tab — pre/post-LCL voltages, time + frequency. Only
// meaningful when the LCL filter is enabled; the tab is gated upstream so
// these builders aren't invoked otherwise.
// -----------------------------------------------------------------------------
export const buildSignalProcessingTime: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const va = col(table, 'v_a');
  const vb = col(table, 'v_b');
  const vc = col(table, 'v_c');
  const vam = col(table, 'v_a_motor');
  const vbm = col(table, 'v_b_motor');
  const vcm = col(table, 'v_c_motor');

  const layout = stackedGrid({
    count: 2,
    titles: ['v_abc pre-filter (inverter terminals)', 'v_abc post-filter (motor terminals)'],
    yLabels: ['v [V]', 'v [V]'],
  });

  const line = (gi: number, name: string, data: [number, number][], color: string): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    data,
    showSymbol: false,
    sampling: 'lttb',
    lineStyle: { color, width: 1.0 },
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
      line(0, 'v_a', xyPairs(t, va), PALETTE[0]),
      line(0, 'v_b', xyPairs(t, vb), PALETTE[1]),
      line(0, 'v_c', xyPairs(t, vc), PALETTE[2]),
      line(1, 'v_a_motor', xyPairs(t, vam), PALETTE[0]),
      line(1, 'v_b_motor', xyPairs(t, vbm), PALETTE[1]),
      line(1, 'v_c_motor', xyPairs(t, vcm), PALETTE[2]),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// FFT pre/post the filter — verifies the f_c roll-off.
export const buildSignalProcessingFft = buildFftFigure([
  { title: 'FFT(v_a) pre-filter',  yLabel: 'mag [V, norm]', traces: [{ signalCol: 'v_a',       name: '|FFT(v_a)|' }] },
  { title: 'FFT(v_a) post-filter', yLabel: 'mag [V, norm]', traces: [{ signalCol: 'v_a_motor', name: '|FFT(v_a_motor)|' }] },
]);
