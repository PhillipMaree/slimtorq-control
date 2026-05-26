import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { base } from '../theme';
import { cornerInfoBox, stackedGrid } from '../subplotLayout';
import type { FigureBuilder } from './types';
import { metaNum } from './types';
import { buildFftFigure } from './fftHelpers';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

// -----------------------------------------------------------------------------
// Power-tab time-domain panel: 3-phase currents + 3-phase post-inverter
// voltages (with ±V_max guide lines). The pre/post LCL split lives in the
// Signal-Processing tab.
// -----------------------------------------------------------------------------
export const buildPowerTime: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const ia = col(table, 'i_a');
  const ib = col(table, 'i_b');
  const ic = col(table, 'i_c');
  const va = col(table, 'v_a');
  const vb = col(table, 'v_b');
  const vc = col(table, 'v_c');
  const Vdc = metaNum(meta, 'slimtorq.vdc', 72);
  const Vmax = Vdc / 2;
  const n = t.length;

  const layout = stackedGrid({
    count: 2,
    titles: ['Phase currents (abc)', 'Phase voltages (post-inverter)'],
    yLabels: ['i [A]', 'v [V]'],
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

  const limitLine = (gi: number, y: number, name: string): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    showSymbol: false,
    silent: true,
    data: [
      [t[0], y],
      [t[n - 1], y],
    ],
    lineStyle: { color: RED_LIMIT, type: 'dotted', width: 1 },
    z: -1,
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
    graphic: [
      cornerInfoBox([`V_max = Vdc/2 = ${Vmax.toFixed(1)} V`], layout.gridTops[1]),
    ],
    series: [
      line(0, 'i_a', xyPairs(t, ia), PALETTE[0]),
      line(0, 'i_b', xyPairs(t, ib), PALETTE[1]),
      line(0, 'i_c', xyPairs(t, ic), PALETTE[2]),
      line(1, 'v_a', xyPairs(t, va), PALETTE[0]),
      line(1, 'v_b', xyPairs(t, vb), PALETTE[1]),
      line(1, 'v_c', xyPairs(t, vc), PALETTE[2]),
      limitLine(1, +Vmax, '+V_max'),
      limitLine(1, -Vmax, '-V_max'),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// FFT of phase-a current — switching ripple verification.
export const buildPowerFft = buildFftFigure([
  { title: 'FFT(i_a)', yLabel: 'mag [A, norm]', traces: [{ signalCol: 'i_a', name: '|FFT(i_a)|' }] },
]);
