import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildPhaseCurrents: FigureBuilder = ({ table }) => {
  const t = tMs(col(table, 't'));
  const phases = ['a', 'b', 'c'] as const;
  const option: EChartsOption = {
    ...base,
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: axisTime('t [ms]'),
    yAxis: axisValue('phase current [A]'),
    series: phases.map((p, i) => ({
      type: 'line' as const,
      name: `i_${p}`,
      data: xyPairs(t, col(table, `i_${p}`)),
      showSymbol: false,
      sampling: 'lttb' as const,
      lineStyle: { color: PALETTE[i % PALETTE.length], width: 1.2 },
    })),
  };
  return { title: 'Phase currents (abc)', option, height: 340 };
};
