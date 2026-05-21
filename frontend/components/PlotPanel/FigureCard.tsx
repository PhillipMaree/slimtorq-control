'use client';

import type { EChartsOption } from 'echarts';
import { EChart } from './EChart';
import { KatexTitle } from './KatexTitle';

export interface FigureSpec {
  title: string;
  option: EChartsOption;
  height?: number;
}

export function FigureCard({ figure }: { figure: FigureSpec }) {
  return (
    <div className="bg-alva-panel border border-alva-border rounded-sm p-3 shadow-sm">
      <KatexTitle tex={figure.title} />
      <EChart option={figure.option} style={figure.height ? { height: `${figure.height}px` } : undefined} />
    </div>
  );
}
