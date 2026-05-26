import type { Table } from 'apache-arrow';
import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { rfftMagnitude } from '@/lib/fft';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { base } from '../theme';
import { cornerInfoBox, freqGrid, freqGuideMarkLines, freqGuides, stackedGrid } from '../subplotLayout';
import { metaNum } from './types';
import type { FigureBuilder } from './types';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

// -----------------------------------------------------------------------------
// 1. Control-tab time-domain panel: PI errors + v_d (with V_max limits) + v_q.
// |v_dq| vs V_max subplot is intentionally absent (per spec). V_max guides
// stay on the v_d subplot only.
// -----------------------------------------------------------------------------
export const buildControlTime: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const idRef = col(table, 'i_d_ref');
  const idM = col(table, 'i_d_meas');
  const iqRef = col(table, 'i_q_ref');
  const iqM = col(table, 'i_q_meas');
  const vd = col(table, 'v_d_ref');
  const vq = col(table, 'v_q_ref');
  const Vdc = metaNum(meta, 'slimtorq.vdc', 72);
  const Vmax = Vdc / 2;
  const n = t.length;
  const eD = new Float64Array(n);
  const eQ = new Float64Array(n);
  let sumD = 0;
  let sumQ = 0;
  for (let i = 0; i < n; i++) {
    eD[i] = idRef[i] - idM[i];
    eQ[i] = iqRef[i] - iqM[i];
    sumD += eD[i] * eD[i];
    sumQ += eQ[i] * eQ[i];
  }
  const rmsED = Math.sqrt(sumD / Math.max(n, 1));
  const rmsEQ = Math.sqrt(sumQ / Math.max(n, 1));

  const layout = stackedGrid({
    count: 3,
    titles: ['PI errors (time)', 'd-axis voltage', 'q-axis voltage'],
    yLabels: ['e [A]', 'v_d [V]', 'v_q [V]'],
  });

  const line = (gi: number, name: string, data: [number, number][], color: string, width = 1.3): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    data,
    showSymbol: false,
    sampling: 'lttb',
    lineStyle: { color, width },
  });

  const limitLine = (gi: number, y: number, name: string): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    showSymbol: false,
    silent: true,
    data: [
      [t[0], y],
      [t[n - 1], y],
    ],
    lineStyle: { color: RED_LIMIT, type: 'dotted', width: 1 },
    z: -1,
  });

  const option: EChartsOption = {
    ...base,
    title: layout.title,
    grid: layout.grid,
    xAxis: layout.xAxis,
    yAxis: layout.yAxis,
    axisPointer: layout.axisPointer,
    dataZoom: layout.dataZoom,
    legend: { top: 0, right: 8, textStyle: { fontSize: 13 } },
    graphic: [
      cornerInfoBox([`RMS(e_d) = ${rmsED.toExponential(2)} A`, `RMS(e_q) = ${rmsEQ.toExponential(2)} A`], layout.gridTops[0]),
      cornerInfoBox([`V_max = Vdc/2 = ${Vmax.toFixed(1)} V`], layout.gridTops[1]),
    ],
    series: [
      line(0, 'e_d', xyPairs(t, eD), PALETTE[0]),
      line(0, 'e_q', xyPairs(t, eQ), PALETTE[1]),
      line(1, 'v_d_ref', xyPairs(t, vd), PALETTE[0]),
      limitLine(1, +Vmax, '+V_max'),
      limitLine(1, -Vmax, '-V_max'),
      line(2, 'v_q_ref', xyPairs(t, vq), PALETTE[1]),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// -----------------------------------------------------------------------------
// 2. Control-tab FFT panel: |FFT(e_d)|, |FFT(e_q)| overlaid, then |FFT(v_d_ref)|
// and |FFT(v_q_ref)| as separate subplots. Each subplot carries the shared
// freqGuides overlay.
// -----------------------------------------------------------------------------
function fftCentered(signal: Float64Array, dt: number) {
  let mean = 0;
  for (let i = 0; i < signal.length; i++) mean += signal[i];
  mean /= Math.max(signal.length, 1);
  const c = new Float64Array(signal.length);
  for (let i = 0; i < signal.length; i++) c[i] = signal[i] - mean;
  const { freqs, mag } = rfftMagnitude(c, dt);
  const floored = new Float64Array(mag.length);
  for (let i = 0; i < mag.length; i++) floored[i] = Math.max(mag[i], 1e-12);
  return { freqs, mag: floored };
}

function tailDiff(table: Table, refColName: string, measColName: string, frac = 0.8) {
  const tArr = col(table, 't');
  const ref = col(table, refColName);
  const meas = col(table, measColName);
  const n = tArr.length;
  const dt = n >= 2 ? tArr[1] - tArr[0] : 1;
  const start = Math.floor((1 - frac) * n);
  const win = new Float64Array(n - start);
  for (let i = start; i < n; i++) win[i - start] = ref[i] - meas[i];
  return { ...fftCentered(win, dt) };
}

function tailFft(table: Table, colName: string, frac = 0.8) {
  const tArr = col(table, 't');
  const sig = col(table, colName);
  const n = tArr.length;
  const dt = n >= 2 ? tArr[1] - tArr[0] : 1;
  const start = Math.floor((1 - frac) * n);
  return fftCentered(sig.subarray(start), dt);
}

export const buildControlFft: FigureBuilder = ({ table, meta }) => {
  const layout = freqGrid({
    count: 3,
    titles: ['FFT(PI errors)', 'FFT(v_d_ref)', 'FFT(v_q_ref)'],
    yLabels: ['mag [A, norm]', 'mag [V, norm]', 'mag [V, norm]'],
  });
  const guides = freqGuideMarkLines(freqGuides(meta));

  const ed = tailDiff(table, 'i_d_ref', 'i_d_meas');
  const eq = tailDiff(table, 'i_q_ref', 'i_q_meas');
  const fdv = tailFft(table, 'v_d_ref');
  const fqv = tailFft(table, 'v_q_ref');

  const series: LineSeriesOption[] = [
    {
      type: 'line', name: '|FFT(e_d)|', xAxisIndex: 0, yAxisIndex: 0,
      data: xyPairs(ed.freqs.subarray(1), ed.mag.subarray(1)),
      showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1 },
      markLine: { symbol: 'none', silent: true, data: guides },
    },
    {
      type: 'line', name: '|FFT(e_q)|', xAxisIndex: 0, yAxisIndex: 0,
      data: xyPairs(eq.freqs.subarray(1), eq.mag.subarray(1)),
      showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1 },
    },
    {
      type: 'line', name: '|FFT(v_d_ref)|', xAxisIndex: 1, yAxisIndex: 1,
      data: xyPairs(fdv.freqs.subarray(1), fdv.mag.subarray(1)),
      showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[0], width: 1 },
      markLine: { symbol: 'none', silent: true, data: guides },
    },
    {
      type: 'line', name: '|FFT(v_q_ref)|', xAxisIndex: 2, yAxisIndex: 2,
      data: xyPairs(fqv.freqs.subarray(1), fqv.mag.subarray(1)),
      showSymbol: false, sampling: 'lttb', lineStyle: { color: PALETTE[1], width: 1 },
      markLine: { symbol: 'none', silent: true, data: guides },
    },
  ];

  const option: EChartsOption = {
    ...base,
    title: layout.title,
    grid: layout.grid,
    xAxis: layout.xAxis,
    yAxis: layout.yAxis,
    dataZoom: layout.dataZoom,
    legend: { top: 0, right: 8, textStyle: { fontSize: 13 } },
    series,
  };
  return { title: '', option, height: layout.cardHeight };
};
