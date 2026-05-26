import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE, RED_LIMIT } from '@/lib/palette';
import { base } from '../theme';
import { cornerInfoBox, stackedGrid } from '../subplotLayout';
import type { FigureBuilder } from './types';
import { metaNum } from './types';
import { buildFftFigure } from './fftHelpers';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);
const PI = Math.PI;
const TWO_PI = 2 * PI;

// Wrap (a − b) to the principal range (−π, π].
function wrappedDiff(a: Float64Array, b: Float64Array): Float64Array {
  const n = Math.min(a.length, b.length);
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let d = a[i] - b[i];
    d = ((d + PI) % TWO_PI + TWO_PI) % TWO_PI - PI;
    out[i] = d;
  }
  return out;
}

function rms(x: Float64Array): number {
  let s = 0;
  for (let i = 0; i < x.length; i++) s += x[i] * x[i];
  return Math.sqrt(s / Math.max(x.length, 1));
}

// -----------------------------------------------------------------------------
// Mechanical-tab time-domain panel:
//   1. Mechanical angle (θ_m_true vs θ_m_meas)
//   2. Electrical angle (θ_e_true vs θ_e_meas)
//   3. Mechanical speed (ω_m_true vs ω_m_meas)
//   4. Δθ_m = wrap(θ_m_true − θ_m_meas) in mrad + ZOH envelope
//   5. Δθ_e = wrap(θ_e_true − θ_e_meas) in mrad
// -----------------------------------------------------------------------------
export const buildMechanicalTime: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const thM = col(table, 'theta_m_true');
  const thMm = col(table, 'theta_m_meas');
  const thE = col(table, 'theta_e_true');
  const thEm = col(table, 'theta_e_meas');
  const wm = col(table, 'omega_m_true');
  const wmm = col(table, 'omega_m_meas');
  const tsEnc = metaNum(meta, 'slimtorq.ts_enc', 1e-4);

  const dMech = wrappedDiff(thM, thMm);
  const dElec = wrappedDiff(thE, thEm);
  const dMechMrad = Float64Array.from(dMech, (v) => v * 1e3);
  const dElecMrad = Float64Array.from(dElec, (v) => v * 1e3);
  const rmsMech = rms(dMechMrad);
  const rmsElec = rms(dElecMrad);

  // ZOH envelope on the mechanical-error subplot: ±ω·Ts_enc in mrad.
  const n = t.length;
  const envHi = new Float64Array(n);
  const envLo = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const b = Math.abs(wm[i]) * tsEnc * 1e3;
    envHi[i] = b;
    envLo[i] = -b;
  }

  const layout = stackedGrid({
    count: 5,
    titles: [
      'Mechanical angle',
      'Electrical angle',
      'Mechanical speed',
      'Δθ_m (mechanical encoder error)',
      'Δθ_e (electrical encoder error)',
    ],
    yLabels: ['θ_m [rad]', 'θ_e [rad]', 'ω_m [rad/s]', 'Δθ_m [mrad]', 'Δθ_e [mrad]'],
    rowHeight: 130,
  });

  const line = (gi: number, name: string, data: [number, number][], color: string, dashed = false, width = 1.3): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    data,
    showSymbol: false,
    sampling: 'lttb',
    lineStyle: { color, width, type: dashed ? 'dashed' : 'solid' },
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
      cornerInfoBox([`RMS Δθ_m = ${rmsMech.toFixed(3)} mrad`, `ZOH ±ω·Ts_enc`], layout.gridTops[3]),
      cornerInfoBox([`RMS Δθ_e = ${rmsElec.toFixed(3)} mrad`], layout.gridTops[4]),
    ],
    series: [
      line(0, 'θ_m_true', xyPairs(t, thM), PALETTE[0]),
      line(0, 'θ_m_meas', xyPairs(t, thMm), PALETTE[1], true, 1.1),
      line(1, 'θ_e_true', xyPairs(t, thE), PALETTE[0]),
      line(1, 'θ_e_meas', xyPairs(t, thEm), PALETTE[1], true, 1.1),
      line(2, 'ω_m_true', xyPairs(t, wm), PALETTE[0]),
      line(2, 'ω_m_meas', xyPairs(t, wmm), PALETTE[1], true, 1.1),
      line(3, 'Δθ_m', xyPairs(t, dMechMrad), PALETTE[2]),
      line(3, '+ZOH', xyPairs(t, envHi), RED_LIMIT, true, 0.8),
      line(3, '-ZOH', xyPairs(t, envLo), RED_LIMIT, true, 0.8),
      line(4, 'Δθ_e', xyPairs(t, dElecMrad), PALETTE[2]),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// -----------------------------------------------------------------------------
// Mechanical-tab FFTs: θ_e_meas and ω_m_meas.
// -----------------------------------------------------------------------------
export const buildMechanicalFft = buildFftFigure([
  { title: 'FFT(θ_e_meas)', yLabel: 'mag [rad, norm]',   traces: [{ signalCol: 'theta_e_meas', name: '|FFT(θ_e_meas)|' }] },
  { title: 'FFT(ω_m_meas)', yLabel: 'mag [rad/s, norm]', traces: [{ signalCol: 'omega_m_meas', name: '|FFT(ω_m_meas)|' }] },
]);
