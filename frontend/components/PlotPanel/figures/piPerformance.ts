import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { metaNum } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildPiPerformance: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const idRef = col(table, 'i_d_ref');
  const idM = col(table, 'i_d_meas');
  const iqRef = col(table, 'i_q_ref');
  const iqM = col(table, 'i_q_meas');
  const vd = col(table, 'v_d_ref');
  const vq = col(table, 'v_q_ref');
  const Vdc = metaNum(meta, 'slimtorq.vdc', 72);
  const Vmax = Vdc / 2;
  const n = t.length;
  const eD = new Float64Array(n);
  const eQ = new Float64Array(n);
  const vMag = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    eD[i] = idRef[i] - idM[i];
    eQ[i] = iqRef[i] - iqM[i];
    vMag[i] = Math.hypot(vd[i], vq[i]);
  }

  const limitLine = (g: number, y: number, label?: string): LineSeriesOption => ({
    type: 'line',
    xAxisIndex: g,
    yAxisIndex: g,
    showSymbol: false,
    data: [
      [t[0], y],
      [t[n - 1], y],
    ],
    lineStyle: { color: RED_LIMIT, type: 'dotted', width: 1 },
    silent: true,
    name: label,
    z: -1,
  });

  const option: EChartsOption = {
    ...base,
    title: [
      { text: 'PI error [A]', top: '0%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: 'v_d_ref, v_q_ref [V]', top: '34%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: `|v_dq| vs V_max=Vdc/2=${Vmax.toFixed(1)} V`, top: '67%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
    ],
    legend: { top: 0, right: 8, textStyle: { fontSize: 10 } },
    grid: [
      { left: 60, right: 20, top: '6%', height: '24%' },
      { left: 60, right: 20, top: '40%', height: '24%' },
      { left: 60, right: 20, top: '73%', height: '22%' },
    ],
    xAxis: [
      { ...axisTime(), gridIndex: 0 },
      { ...axisTime(), gridIndex: 1 },
      { ...axisTime('t [ms]'), gridIndex: 2 },
    ],
    yAxis: [
      { ...axisValue(), gridIndex: 0 },
      { ...axisValue(), gridIndex: 1 },
      { ...axisValue(), gridIndex: 2 },
    ],
    series: [
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'e_d', data: xyPairs(t, eD), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1.2 } },
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'e_q', data: xyPairs(t, eQ), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1.2 } },
      { type: 'line', xAxisIndex: 1, yAxisIndex: 1, name: 'v_d_ref', data: xyPairs(t, vd), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1.2 } },
      { type: 'line', xAxisIndex: 1, yAxisIndex: 1, name: 'v_q_ref', data: xyPairs(t, vq), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1.2 } },
      limitLine(1, Vmax, '+V_max'),
      limitLine(1, -Vmax, '-V_max'),
      { type: 'line', xAxisIndex: 2, yAxisIndex: 2, name: '|v_dq|', data: xyPairs(t, vMag), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[2], width: 1.3 } },
      limitLine(2, Vmax, 'V_max'),
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
  };
  return { title: 'PI performance', option, height: 520 };
};
