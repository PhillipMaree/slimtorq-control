import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { metaNum } from './types';

export const buildIqZoom: FigureBuilder = ({ table, meta }) => {
  const fPwm = metaNum(meta, 'slimtorq.f_pwm', 20000);
  const Tpwm = 1 / fPwm;
  const tFull = col(table, 't');
  const iq = col(table, 'i_q_meas');
  const iqRef = col(table, 'i_q_ref');
  const n = tFull.length;
  if (n < 8) {
    return { title: 'i_q zoom skipped: signal too short', option: { ...base, series: [] } };
  }
  const dt = tFull[1] - tFull[0];
  const cyclesToShow = 5;
  const samplesPerCycle = Math.round(Tpwm / dt);
  const start = Math.max(0, n - cyclesToShow * samplesPerCycle);
  const winLen = n - start;
  const tWin = new Float64Array(winLen);
  const iqWin = new Float64Array(winLen);
  const iqRefWin = new Float64Array(winLen);
  for (let i = 0; i < winLen; i++) {
    tWin[i] = tFull[start + i] * 1e3;
    iqWin[i] = iq[start + i];
    iqRefWin[i] = iqRef[start + i];
  }
  // Carrier valleys at integer multiples of T_pwm.
  const firstValley = Math.ceil(tFull[start] / Tpwm) * Tpwm;
  const lastValley = Math.floor(tFull[n - 1] / Tpwm) * Tpwm;
  const valleys: { xAxis: number }[] = [];
  for (let v = firstValley; v <= lastValley + 1e-15; v += Tpwm) {
    valleys.push({ xAxis: v * 1e3 });
  }

  const option: EChartsOption = {
    ...base,
    grid: { left: 60, right: 20, top: 36, bottom: 40 },
    xAxis: axisTime('t [ms]'),
    yAxis: axisValue('i_q [A]'),
    series: [
      { type: 'line', name: 'i_q_ref', data: xyPairs(tWin, iqRefWin), showSymbol: false, lineStyle: { color: PALETTE[1], type: 'dashed', width: 1.2 } },
      {
        type: 'line',
        name: 'i_q',
        data: xyPairs(tWin, iqWin),
        showSymbol: false,
        lineStyle: { color: PALETTE[1], width: 1.4 },
        markLine: {
          symbol: 'none',
          lineStyle: { color: '#000', type: 'dotted', width: 0.5, opacity: 0.4 },
          label: { show: false },
          data: valleys,
          silent: true,
        },
      },
    ],
  };
  return { title: `i_q zoom (~${cyclesToShow} \\times T_{pwm} @ f_{pwm} = ${fPwm.toFixed(0)}\\,\\text{Hz})`, option, height: 320 };
};
