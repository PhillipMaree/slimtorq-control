import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { axisTime, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { metaNum } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

export const buildPhaseVoltages: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const Vdc = metaNum(meta, 'slimtorq.vdc', 72);
  const half = Vdc / 2;
  const filterOn = meta.parquet_meta['slimtorq.filter_enabled'] === '1';
  const phases = ['a', 'b', 'c'] as const;

  const series: NonNullable<EChartsOption['series']> = [];
  phases.forEach((p, i) => {
    const c = PALETTE[i % PALETTE.length];
    series.push({
      type: 'line',
      name: `v_${p} (post-inv)`,
      data: xyPairs(t, col(table, `v_${p}`)),
      showSymbol: false,
      sampling: 'lttb',
      lineStyle: { color: c, width: 1, opacity: 0.45 },
    });
    if (filterOn) {
      series.push({
        type: 'line',
        name: `v_${p}^motor`,
        data: xyPairs(t, col(table, `v_${p}_motor`)),
        showSymbol: false,
        sampling: 'lttb',
        lineStyle: { color: c, width: 1.6 },
      });
    }
    series.push({
      type: 'line',
      name: `v_${p}_ref`,
      data: xyPairs(t, col(table, `v_${p}_ref`)),
      showSymbol: false,
      sampling: 'lttb',
      lineStyle: { color: c, type: 'dashed', width: 1.4 },
    });
  });
  // Vdc/2 limit lines.
  series.push({
    type: 'line',
    name: `±Vdc/2 = ${half.toFixed(1)}`,
    data: [
      [t[0], half],
      [t[t.length - 1], half],
    ],
    showSymbol: false,
    silent: true,
    lineStyle: { color: RED_LIMIT, type: 'dotted', width: 1 },
  });
  series.push({
    type: 'line',
    name: '',
    data: [
      [t[0], -half],
      [t[t.length - 1], -half],
    ],
    showSymbol: false,
    silent: true,
    lineStyle: { color: RED_LIMIT, type: 'dotted', width: 1 },
  });

  const option: EChartsOption = {
    ...base,
    legend: { top: 0, right: 8, textStyle: { fontSize: 10 } },
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: axisTime('t [ms]'),
    yAxis: axisValue('phase voltage [V]'),
    series,
  };
  return { title: filterOn ? 'Phase voltages: refs, post-inv, post-LCL' : 'Phase voltages: refs vs post-inv', option, height: 380 };
};
