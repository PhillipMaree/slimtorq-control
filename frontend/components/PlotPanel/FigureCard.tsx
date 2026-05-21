'use client';

import type { EChartsOption } from 'echarts';
import { EChart } from './EChart';

export interface FigureSpec {
  title: string;
  option: EChartsOption;
  height?: number;
}

// Subplot titles now live inside the ECharts option (centered above each
// grid via subplotLayout). The outer card no longer renders its own header.
export function FigureCard({ figure }: { figure: FigureSpec }) {
  return (
    <div className="bg-alva-panel border border-alva-border rounded-sm p-3 shadow-sm">
      <EChart option={figure.option} style={figure.height ? { height: `${figure.height}px` } : undefined} />
    </div>
  );
}
