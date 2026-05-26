import type { EChartsOption } from 'echarts';
import { PALETTE } from '@/lib/palette';

// Common ECharts option fragments. Each figure spreads `base` and overrides
// only what differs — keeps the 12 modules small and visually consistent.

const AXIS_NAME_STYLE = { color: '#1A1A1A', fontSize: 14 };

export const base: EChartsOption = {
  animation: false,
  color: [...PALETTE],
  textStyle: {
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    color: '#1A1A1A',
  },
  grid: { left: 60, right: 20, top: 28, bottom: 36, containLabel: false },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'line', lineStyle: { color: '#999' } },
    backgroundColor: '#FFFFFF',
    borderColor: '#E4E2DC',
    textStyle: { fontSize: 13, color: '#1A1A1A' },
  },
  legend: {
    top: 0,
    right: 10,
    textStyle: { fontSize: 13, color: '#5B5B5B' },
    icon: 'roundRect',
  },
};

export function axisTime(name?: string) {
  return {
    type: 'value' as const,
    name,
    nameLocation: 'middle' as const,
    nameGap: 26,
    nameTextStyle: AXIS_NAME_STYLE,
    splitLine: { lineStyle: { color: '#EFEDE8' } },
    axisLine: { lineStyle: { color: '#B6B4AE' } },
    axisLabel: { color: '#5B5B5B', fontSize: 13 },
  };
}

export function axisValue(name?: string) {
  return {
    type: 'value' as const,
    name,
    nameLocation: 'middle' as const,
    nameGap: 50,
    nameTextStyle: AXIS_NAME_STYLE,
    scale: true,
    splitLine: { lineStyle: { color: '#EFEDE8' } },
    axisLine: { lineStyle: { color: '#B6B4AE' } },
    axisLabel: { color: '#5B5B5B', fontSize: 13 },
  };
}

export function axisLog(name?: string) {
  return {
    type: 'log' as const,
    name,
    nameLocation: 'middle' as const,
    nameGap: 50,
    nameTextStyle: AXIS_NAME_STYLE,
    splitLine: { lineStyle: { color: '#EFEDE8' } },
    axisLine: { lineStyle: { color: '#B6B4AE' } },
    axisLabel: { color: '#5B5B5B', fontSize: 13 },
  };
}
