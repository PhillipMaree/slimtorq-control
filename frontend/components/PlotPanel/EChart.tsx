'use client';

import dynamic from 'next/dynamic';
import type { EChartsOption } from 'echarts';
import type { CSSProperties } from 'react';

const ReactECharts = dynamic(() => import('echarts-for-react'), { ssr: false });

interface EChartProps {
  option: EChartsOption;
  style?: CSSProperties;
}

export function EChart({ option, style }: EChartProps) {
  return (
    <ReactECharts
      option={option}
      notMerge
      lazyUpdate
      style={{ height: '320px', width: '100%', ...style }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
