import type { EChartsOption, LineSeriesOption } from 'echarts';
import { col, xyPairs } from '@/lib/arrow';
import { PALETTE } from '@/lib/palette';
import { base } from '../theme';
import { cornerInfoBox, stackedGrid } from '../subplotLayout';
import type { FigureBuilder } from './types';
import { metaNum, refTrackingErrPct } from './types';
import { buildFftFigure } from './fftHelpers';

const tMs = (t: Float64Array) => Float64Array.from(t, (v) => v * 1e3);

// 1. Time-domain tracking: Torque, i_q, i_d (ref vs measured) with err%.
export const buildTrackingTime: FigureBuilder = ({ table, meta }) => {
  const t = tMs(col(table, 't'));
  const TL = col(table, 'TL_ref');
  const Te = col(table, 'T_e');
  const iqRef = col(table, 'i_q_ref');
  const iqM = col(table, 'i_q_meas');
  const idRef = col(table, 'i_d_ref');
  const idM = col(table, 'i_d_meas');

  // Peak normalizations from parquet meta: currents → i_q_peak = sqrt(2)·i_cont,
  // torque → te_peak_1s. Both are motor-relative constants.
  const iqPeak = metaNum(meta, 'slimtorq.i_q_peak', NaN);
  const tePeak = metaNum(meta, 'slimtorq.te_peak_1s', NaN);
  const errT = refTrackingErrPct(table, 'T_e', 'TL_ref', tePeak).toFixed(2);
  const errQ = refTrackingErrPct(table, 'i_q_meas', 'i_q_ref', iqPeak).toFixed(2);
  const errD = refTrackingErrPct(table, 'i_d_meas', 'i_d_ref', iqPeak).toFixed(2);

  const layout = stackedGrid({
    count: 3,
    titles: ['Torque tracking', 'q-axis current tracking', 'd-axis current tracking'],
    yLabels: ['Torque [N·m]', 'i_q [A]', 'i_d [A]'],
  });

  const line = (gi: number, name: string, data: Iterable<[number, number]>, color: string, dashed = false, width = 1.4): LineSeriesOption => ({
    type: 'line',
    name,
    xAxisIndex: gi,
    yAxisIndex: gi,
    data: data as [number, number][],
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
      cornerInfoBox([`err = ${errT} % of |T_L_ref|_max`], layout.gridTops[0]),
      cornerInfoBox([`err = ${errQ} % of |i_q_ref|_max`], layout.gridTops[1]),
      cornerInfoBox([`err = ${errD} % of i_q_peak`], layout.gridTops[2]),
    ],
    series: [
      line(0, 'T_L_ref', xyPairs(t, TL), PALETTE[0], true, 1.2),
      line(0, 'T_e', xyPairs(t, Te), PALETTE[0]),
      line(1, 'i_q_ref', xyPairs(t, iqRef), PALETTE[1], true, 1.2),
      line(1, 'i_q', xyPairs(t, iqM), PALETTE[1]),
      line(2, 'i_d_ref', xyPairs(t, idRef), PALETTE[2], true, 1.2),
      line(2, 'i_d', xyPairs(t, idM), PALETTE[2]),
    ],
  };
  return { title: '', option, height: layout.cardHeight };
};

// 2. FFTs of the realized tracking signals: T_e, i_q_meas, i_d_meas.
// FFT(i_d_meas) is included to verify dq decoupling — with i_d_ref = 0 the
// spectrum should be ripple-only (no fundamental at the rotor electrical
// frequency).
export const buildTrackingFft = buildFftFigure([
  { title: 'FFT(T_e)',      yLabel: 'mag [N·m, norm]', traces: [{ signalCol: 'T_e',       name: '|FFT(T_e)|' }] },
  { title: 'FFT(i_q_meas)', yLabel: 'mag [A, norm]',   traces: [{ signalCol: 'i_q_meas',  name: '|FFT(i_q^meas)|' }] },
  { title: 'FFT(i_d_meas)', yLabel: 'mag [A, norm]',   traces: [{ signalCol: 'i_d_meas',  name: '|FFT(i_d^meas)|' }] },
]);
