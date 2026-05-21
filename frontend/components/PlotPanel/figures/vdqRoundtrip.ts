import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';

const SQRT3 = Math.sqrt(3);
const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildVdqRoundtrip: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const va = col(table, 'v_a');
  const vb = col(table, 'v_b');
  const vc = col(table, 'v_c');
  const thetaE = col(table, 'theta_e_meas');
  const vdRef = col(table, 'v_d_ref');
  const vqRef = col(table, 'v_q_ref');
  const n = t.length;
  const errD = new Float64Array(n);
  const errQ = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const vAlpha = (2 / 3) * (va[i] - 0.5 * vb[i] - 0.5 * vc[i]);
    const vBeta = (vb[i] - vc[i]) / SQRT3;
    const c = Math.cos(thetaE[i]);
    const s = Math.sin(thetaE[i]);
    const vdAct = vAlpha * c + vBeta * s;
    const vqAct = -vAlpha * s + vBeta * c;
    errD[i] = vdAct - vdRef[i];
    errQ[i] = vqAct - vqRef[i];
  }
  // Steady-state means over trailing 80%.
  let mD = 0;
  let mQ = 0;
  const start = Math.floor(0.2 * n);
  for (let i = start; i < n; i++) {
    mD += errD[i];
    mQ += errQ[i];
  }
  mD /= n - start;
  mQ /= n - start;

  const option: EChartsOption = {
    ...base,
    title: [
      { text: `Δv_d [V]   mean = ${mD.toFixed(3)}`, top: '0%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
      { text: `Δv_q [V]   mean = ${mQ.toFixed(3)}`, top: '50%', textStyle: { fontSize: 12, color: '#5B5B5B' } },
    ],
    legend: { top: 0, right: 8, textStyle: { fontSize: 10 } },
    grid: [
      { left: 60, right: 20, top: '6%', height: '38%' },
      { left: 60, right: 20, top: '56%', height: '38%' },
    ],
    xAxis: [
      { ...axisTime(), gridIndex: 0 },
      { ...axisTime('t [ms]'), gridIndex: 1 },
    ],
    yAxis: [
      { ...axisValue(), gridIndex: 0 },
      { ...axisValue(), gridIndex: 1 },
    ],
    series: [
      { type: 'line', xAxisIndex: 0, yAxisIndex: 0, name: 'Δv_d', data: xyPairs(t, errD), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1 } },
      { type: 'line', xAxisIndex: 1, yAxisIndex: 1, name: 'Δv_q', data: xyPairs(t, errQ), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1 } },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
  };
  return { title: 'dq voltage round-trip', option, height: 420 };
};
