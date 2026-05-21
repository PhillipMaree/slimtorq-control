import type { EChartsOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { rfftMagnitude } from '@/lib/fft';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { axisLog, axisValue, base } from '../theme';
import type { FigureBuilder } from './types';
import { metaNum } from './types';

interface FftFigureOpts {
  signalCol: string;
  traceName: string;
  yLabel: string;
  pwmGuides?: number[]; // multiples of f_pwm to draw as vertical guides
  pwmGuideLabel?: (k: number) => string;
}

export function buildFftFigure(opts: FftFigureOpts): FigureBuilder {
  return ({ table, meta }) => {
    const tArr = col(table, 't');
    const sig = col(table, opts.signalCol);
    const n = tArr.length;
    if (n < 8) {
      return { title: 'FFT skipped: signal too short', option: { ...base, series: [] } };
    }
    const start = Math.floor(0.2 * n);
    const win = sig.subarray(start);
    // Remove DC.
    let mean = 0;
    for (let i = 0; i < win.length; i++) mean += win[i];
    mean /= win.length;
    const centered = new Float64Array(win.length);
    for (let i = 0; i < win.length; i++) centered[i] = win[i] - mean;
    const dt = tArr[1] - tArr[0];
    const { freqs, mag } = rfftMagnitude(centered, dt);
    // Log floor.
    const magFloored = new Float64Array(mag.length);
    for (let i = 0; i < mag.length; i++) magFloored[i] = Math.max(mag[i], 1e-12);

    const fPwm = metaNum(meta, 'slimtorq.f_pwm', 20000);
    const markLines = (opts.pwmGuides ?? []).map((k) => ({
      xAxis: k * fPwm,
      label: { formatter: opts.pwmGuideLabel ? opts.pwmGuideLabel(k) : `${k}·f_pwm`, color: RED_LIMIT, fontSize: 10 },
      lineStyle: { color: RED_LIMIT, type: 'dotted' as const, width: 1 },
    }));

    const option: EChartsOption = {
      ...base,
      grid: { left: 70, right: 20, top: 30, bottom: 40 },
      xAxis: { ...axisValue('f [Hz]'), min: Math.max(freqs[1] || 1, 1) },
      yAxis: axisLog(opts.yLabel),
      series: [
        {
          type: 'line',
          name: opts.traceName,
          data: xyPairs(freqs.subarray(1), magFloored.subarray(1)),
          showSymbol: false,
          sampling: 'lttb',
          lineStyle: { color: PALETTE[1], width: 1 },
          markLine: {
            symbol: 'none',
            silent: true,
            data: markLines,
          },
        },
      ],
    };
    return { title: opts.traceName, option, height: 360 };
  };
}
