import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildDuties: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const phases = ['a', 'b', 'c'] as const;
  const option: EChartsOption = {
    ...base,
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: axisTime('t [ms]'),
    yAxis: {
      ...axisValue('duty'),
      min: -0.05,
      max: 1.05,
    },
    series: [
      ...phases.map((p, i) => ({
        type: 'line' as const,
        name: `d_${p}`,
        data: xyPairs(t, col(table, `d_${p}`)),
        showSymbol: false,
        sampling: 'lttb' as const,
        lineStyle: { color: PALETTE[i % PALETTE.length], width: 1.1 },
      })),
      {
        type: 'line' as const,
        name: '0.5',
        data: [
          [t[0], 0.5] as [number, number],
          [t[t.length - 1], 0.5] as [number, number],
        ],
        showSymbol: false,
        silent: true,
        lineStyle: { color: '#000', type: 'dotted' as const, width: 0.5 },
      },
    ],
  };
  return { title: 'PWM duty cycles', option, height: 320 };
};
