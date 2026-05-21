import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { refTrackingErrPct } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildTracking: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const TL = col(table, 'TL_ref');
  const Te = col(table, 'T_e');
  const iqRef = col(table, 'i_q_ref');
  const iqM = col(table, 'i_q_meas');
  const idRef = col(table, 'i_d_ref');
  const idM = col(table, 'i_d_meas');
  const errT = refTrackingErrPct(table, 'T_e', 'TL_ref').toFixed(2);
  const errQ = refTrackingErrPct(table, 'i_q_meas', 'i_q_ref').toFixed(2);
  const errD = refTrackingErrPct(table, 'i_d_meas', 'i_d_ref').toFixed(2);

  const option: EChartsOption = {
    ...base,
    title: [
      { text: `Torque [N·m]   err = ${errT}%`, top: '0%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: `i_q [A]   err = ${errQ}%`, top: '34%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: `i_d [A]   err = ${errD}%`, top: '67%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
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
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'T_L_ref', data: xyPairs(t, TL), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], type: 'dashed', width: 1.2 } },
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'T_e', data: xyPairs(t, Te), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1.4 } },
      { type: 'line', xAxisIndex: 1, yAxisIndex: 1, name: 'i_q_ref', data: xyPairs(t, iqRef), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], type: 'dashed', width: 1.2 } },
      { type: 'line', xAxisIndex: 1, yAxisIndex: 1, name: 'i_q', data: xyPairs(t, iqM), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1.4 } },
      { type: 'line', xAxisIndex: 2, yAxisIndex: 2, name: 'i_d_ref', data: xyPairs(t, idRef), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[2], type: 'dashed', width: 1.2 } },
      { type: 'line', xAxisIndex: 2, yAxisIndex: 2, name: 'i_d', data: xyPairs(t, idM), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[2], width: 1.4 } },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
  };
  return { title: '\\text{Tracking}', option, height: 480 };
};
