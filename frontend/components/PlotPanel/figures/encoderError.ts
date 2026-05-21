import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { metaNum } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);
const TWO_PI = 2 * Math.PI;

export const buildEncoderError: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const thetaTrue = col(table, 'theta_m_true');
  const thetaMeas = col(table, 'theta_m_meas');
  const omega = col(table, 'omega_m_true');
  const tsEnc = metaNum(meta, 'slimtorq.ts_enc', 1e-4);
  const n = t.length;
  const errMrad = new Float64Array(n);
  const zohBoundMrad = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const d = thetaTrue[i] - thetaMeas[i];
    // wrap into [-pi, pi)
    const wrapped = ((d + Math.PI) % TWO_PI + TWO_PI) % TWO_PI - Math.PI;
    errMrad[i] = wrapped * 1e3;
    zohBoundMrad[i] = omega[i] * tsEnc * 1e3;
  }
  const option: EChartsOption = {
    ...base,
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: axisTime('t [ms]'),
    yAxis: axisValue('θ error [mrad]'),
    series: [
      { type: 'line', name: 'θ_true − θ_meas', data: xyPairs(t, errMrad), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1 } },
      { type: 'line', name: 'ω·T_s^enc', data: xyPairs(t, zohBoundMrad), showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], type: 'dashed', width: 1.2 } },
    ],
  };
  return { title: 'Encoder error + ZOH bound', option, height: 340 };
};
