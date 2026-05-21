import type { EChartsOption } from 'echarts';
import { boolCol, col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildSpeedAndSaturation: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const omegaTrue = col(table, 'omega_m_true');
  const omegaMeas = col(table, 'omega_m_meas');
  const satD = boolCol(table, 'sat_d');
  const satQ = boolCol(table, 'sat_q');

  const satDPts: [number, number][] = [];
  const satQPts: [number, number][] = [];
  for (let i = 0; i < t.length; i++) {
    if (satD[i]) satDPts.push([t[i], 0]);
    if (satQ[i]) satQPts.push([t[i], 1]);
  }

  const option: EChartsOption = {
    ...base,
    title: [
      { text: 'Speed [rad/s]', top: '0%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: 'PI saturation flags', top: '72%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
    ],
    legend: { top: 0, right: 8, textStyle: { fontSize: 10 } },
    grid: [
      { left: 60, right: 20, top: '6%', height: '60%' },
      { left: 60, right: 20, top: '78%', height: '16%' },
    ],
    xAxis: [
      { ...axisTime(), gridIndex: 0 },
      { ...axisTime('t [ms]'), gridIndex: 1 },
    ],
    yAxis: [
      { ...axisValue('ω [rad/s]'), gridIndex: 0 },
      {
        ...axisValue(),
        gridIndex: 1,
        min: -0.5,
        max: 1.5,
        axisLabel: { formatter: (v: number) => (v === 0 ? 'sat_d' : v === 1 ? 'sat_q' : ''), color: '#5B5B5B', fontSize: 10 },
        splitNumber: 2,
      },
    ],
    series: [
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'ω_true', data: xyPairs(t, omegaTrue), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1.3 } },
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'ω_meas', data: xyPairs(t, omegaMeas), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], type: 'dashed', width: 1.2 } },
      { type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, name: 'sat_d', data: satDPts, symbol: 'rect', symbolSize: [2, 14], itemStyle: { color: '#E0A23F' } },
      { type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, name: 'sat_q', data: satQPts, symbol: 'rect', symbolSize: [2, 14], itemStyle: { color: '#D33A2C' } },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
  };
  return { title: 'Speed tracking + PI saturation', option, height: 420 };
};
