import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { rfftMagnitude } from '@/lib/fft';
import { PALETTE } from '@/lib/palette';
import { base } from '../theme';
import { freqGrid, freqGuideMarkLines, freqGuides } from '../subplotLayout';
import type { FigureBuilder } from './types';

export interface FftTrace {
  signalCol: string;
  // Series legend name (and series label).
  name: string;
}

export interface FftSubplotOpts {
  // Subplot title (rendered centered above the grid).
  title: string;
  // Y-axis label.
  yLabel: string;
  // One or more signals to FFT and overlay in this subplot.
  traces: FftTrace[];
}

/**
 * Build an FFT figure card with one or more subplots, each carrying the shared
 * frequency-guide overlay (`f_BW`, `1·f_pwm`, `2·f_pwm`, `3·f_pwm`, and `f_c`
 * when the filter is enabled).
 *
 * All subplots share a single log `f [Hz]` x-axis label rendered on the
 * bottom panel.
 */
export function buildFftFigure(subplots: FftSubplotOpts[]): FigureBuilder {
  return ({ table, meta }) => {
    const layout = freqGrid({
      count: subplots.length,
      yLabels: subplots.map((s) => s.yLabel),
      titles: subplots.map((s) => s.title),
    });
    const guides = freqGuideMarkLines(freqGuides(meta));

    const tArr = col(table, 't');
    const n = tArr.length;
    const dt = n >= 2 ? tArr[1] - tArr[0] : 1;
    const start = Math.floor(0.2 * n); // skip the transient
    const series: LineSeriesOption[] = [];

    subplots.forEach((sp, gi) => {
      sp.traces.forEach((tr, ti) => {
        const sig = col(table, tr.signalCol);
        const win = sig.subarray(start);
        // remove DC
        let mean = 0;
        for (let i = 0; i < win.length; i++) mean += win[i];
        mean /= Math.max(win.length, 1);
        const centered = new Float64Array(win.length);
        for (let i = 0; i < win.length; i++) centered[i] = win[i] - mean;
        const { freqs, mag } = rfftMagnitude(centered, dt);
        const mFloor = new Float64Array(mag.length);
        for (let i = 0; i < mag.length; i++) mFloor[i] = Math.max(mag[i], 1e-12);
        series.push({
          type: 'line',
          name: tr.name,
          xAxisIndex: gi,
          yAxisIndex: gi,
          data: xyPairs(freqs.subarray(1), mFloor.subarray(1)),
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { color: PALETTE[ti % PALETTE.length], width: 1 },
          // Attach the freq-guide markLines to the first trace of each subplot
          // so each subplot draws the guides exactly once.
          markLine: ti === 0 ? { symbol: 'none', silent: true, data: guides } : undefined,
        });
      });
    });

    const option: EChartsOption = {
      ...base,
      title: layout.title,
      grid: layout.grid,
      xAxis: layout.xAxis,
      yAxis: layout.yAxis,
      dataZoom: layout.dataZoom,
      legend: { top: 0, right: 8, textStyle: { fontSize: 10 } },
      series,
    };
    return { title: '', option, height: layout.cardHeight };
  };
}
