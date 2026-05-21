'use client';

import type { EChartsOption } from 'echarts';
import { EChart } from './EChart';

export interface FigureSpec {
  title: string;
  option: EChartsOption;
  // Card minimum height in px. Grids are positioned in percentages (see
  // subplotLayout.ts), so the card can stretch above this minimum to fill
  // any leftover viewport space without leaving blank canvas.
  height?: number;
}

export function FigureCard({ figure }: { figure: FigureSpec }) {
  const minH = figure.height ?? 320;
  return (
    <div
      className="bg-alva-panel border border-alva-border rounded-sm p-3 shadow-sm flex flex-col"
      style={{ minHeight: `${minH}px`, flex: '1 1 auto' }}
    >
      <div className="flex-1 min-h-0">
        <EChart option={figure.option} style={{ height: '100%', width: '100%' }} />
      </div>
    </div>
  );
}
