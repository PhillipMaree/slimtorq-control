import type { EChartsOption } from 'echarts';
import type { SimMeta } from '@/types/sim';
import { RED_LIMIT } from '@/lib/palette';
import { axisLog, axisTime, axisValue } from './theme';
import { metaNum, metaStr } from './figures/types';

// -----------------------------------------------------------------------------
// Layout constants. Grid positions are percentages so the chart canvas can
// flex with its container (the figure card stretches to fill empty viewport
// space — see PlotPanel/index.tsx). The pixel-row-height props are converted
// to a *minimum* card height in px so plots stay readable when many cards
// stack in a tall tab.
// -----------------------------------------------------------------------------
const GRID_LEFT_PX = 72;
const GRID_RIGHT_PX = 24;
const TITLE_HEIGHT_PX = 18;
const ROW_GAP_PX = 14;
const SHARED_X_LABEL_PX = 26;
const TOP_PAD_PX = 10;
const BOTTOM_PAD_PX = 8;

// Percentages used inside the chart canvas. ECharts accepts string '%'
// values for grid.top / grid.height / title.top, so the grid scales with
// the container height.
const TITLE_PCT = 4.0;
const TITLE_GAP_PCT = 1.0;
const ROW_GAP_PCT = 2.0;
const SHARED_X_PCT = 6.0;
const TOP_PCT = 1.5;
const BOTTOM_PCT = 1.0;

export interface StackedGridOpts {
  count: number;
  yLabels: string[];
  titles: string[];
  sharedXLabel?: string;
  // Minimum row height in px (used to size each card's CSS `min-height`).
  rowHeight?: number;
}

export interface StackedGridResult {
  title: NonNullable<EChartsOption['title']>;
  grid: NonNullable<EChartsOption['grid']>;
  xAxis: NonNullable<EChartsOption['xAxis']>;
  yAxis: NonNullable<EChartsOption['yAxis']>;
  axisPointer: NonNullable<EChartsOption['axisPointer']>;
  dataZoom: NonNullable<EChartsOption['dataZoom']>;
  // Percentage `top` of each grid (used by cornerInfoBox to anchor overlays).
  gridTops: string[];
  // Card minimum height in px (used as `min-height` on the FigureCard so the
  // ECharts canvas is always at least this tall; flex-grow handles taller).
  cardHeight: number;
}

function buildInsideZoom(count: number): NonNullable<EChartsOption['dataZoom']> {
  const xAxisIndex = Array.from({ length: count }, (_, i) => i);
  const yAxisIndex = Array.from({ length: count }, (_, i) => i);
  return [
    {
      type: 'inside',
      xAxisIndex,
      filterMode: 'none',
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
    },
    {
      type: 'inside',
      yAxisIndex,
      filterMode: 'none',
      zoomOnMouseWheel: 'shift',
      moveOnMouseMove: false,
      moveOnMouseWheel: false,
    },
  ];
}

interface PercentLayout {
  titles: { top: string }[];
  grids: { top: string; height: string }[];
  gridTops: string[]; // top of each grid in '%' for the info-box overlay
  cardHeightPx: number;
}

function percentLayout(count: number, rowHeightPx: number): PercentLayout {
  const titleH = TITLE_PCT;
  const titleGap = TITLE_GAP_PCT;
  const rowGap = ROW_GAP_PCT;
  const usable = 100 - TOP_PCT - BOTTOM_PCT - SHARED_X_PCT - count * (titleH + titleGap) - (count - 1) * rowGap;
  const rowPct = usable / count;

  const titles: { top: string }[] = [];
  const grids: { top: string; height: string }[] = [];
  const gridTops: string[] = [];
  for (let i = 0; i < count; i++) {
    const blockTop = TOP_PCT + i * (titleH + titleGap + rowPct + rowGap);
    const gridTop = blockTop + titleH + titleGap;
    titles.push({ top: `${blockTop}%` });
    grids.push({ top: `${gridTop}%`, height: `${rowPct}%` });
    gridTops.push(`${gridTop}%`);
  }

  const rowBlockH = TITLE_HEIGHT_PX + rowHeightPx;
  const cardHeightPx = TOP_PAD_PX + count * rowBlockH + (count - 1) * ROW_GAP_PX + SHARED_X_LABEL_PX + BOTTOM_PAD_PX;
  return { titles, grids, gridTops, cardHeightPx };
}

/**
 * Build the title / grid / xAxis / yAxis fragments for a vertically-stacked
 * set of time-domain subplots that share a common `t [ms]` x-axis. Grids
 * are positioned in percentages so the canvas can flex with its container;
 * the bottom subplot gets the shared `t [ms]` axis-name label.
 */
export function stackedGrid(opts: StackedGridOpts): StackedGridResult {
  const { count, yLabels, titles } = opts;
  const sharedXLabel = opts.sharedXLabel ?? 't [ms]';
  const rowHeightPx = opts.rowHeight ?? 170;
  const pct = percentLayout(count, rowHeightPx);

  const titleFragments: NonNullable<EChartsOption['title']> = [];
  const grids: NonNullable<EChartsOption['grid']> = [];
  const xAxes: NonNullable<EChartsOption['xAxis']> = [];
  const yAxes: NonNullable<EChartsOption['yAxis']> = [];

  for (let i = 0; i < count; i++) {
    titleFragments.push({
      text: titles[i] ?? '',
      top: pct.titles[i].top,
      left: 'center',
      textStyle: { fontSize: 12, color: '#1A1A1A', fontWeight: 'normal' },
    });
    grids.push({
      left: GRID_LEFT_PX,
      right: GRID_RIGHT_PX,
      top: pct.grids[i].top,
      height: pct.grids[i].height,
    });
    const isLast = i === count - 1;
    xAxes.push({ ...axisTime(isLast ? sharedXLabel : undefined), gridIndex: i, nameGap: 26 });
    yAxes.push({ ...axisValue(yLabels[i]), gridIndex: i, nameGap: 50 });
  }

  return {
    title: titleFragments,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: buildInsideZoom(count),
    gridTops: pct.gridTops,
    cardHeight: pct.cardHeightPx,
  };
}

export interface FreqGridOpts {
  count: number;
  yLabels: string[];
  titles: string[];
  sharedXLabel?: string;
  rowHeight?: number;
}

/**
 * Same layout pattern as stackedGrid but using log-frequency x-axes. FFT
 * plots span 5+ decades of magnitude — the percentage rows keep them
 * readable as the card grows.
 */
export function freqGrid(opts: FreqGridOpts): StackedGridResult {
  const { count, yLabels, titles } = opts;
  const sharedXLabel = opts.sharedXLabel ?? 'f [Hz]';
  const rowHeightPx = opts.rowHeight ?? 240;
  const pct = percentLayout(count, rowHeightPx);

  const titleFragments: NonNullable<EChartsOption['title']> = [];
  const grids: NonNullable<EChartsOption['grid']> = [];
  const xAxes: NonNullable<EChartsOption['xAxis']> = [];
  const yAxes: NonNullable<EChartsOption['yAxis']> = [];

  for (let i = 0; i < count; i++) {
    titleFragments.push({
      text: titles[i] ?? '',
      top: pct.titles[i].top,
      left: 'center',
      textStyle: { fontSize: 12, color: '#1A1A1A', fontWeight: 'normal' },
    });
    grids.push({
      left: GRID_LEFT_PX,
      right: GRID_RIGHT_PX,
      top: pct.grids[i].top,
      height: pct.grids[i].height,
    });
    const isLast = i === count - 1;
    xAxes.push({ ...axisLog(isLast ? sharedXLabel : undefined), gridIndex: i, nameGap: 26 });
    yAxes.push({ ...axisLog(yLabels[i]), gridIndex: i, nameGap: 50 });
  }

  return {
    title: titleFragments,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    axisPointer: { link: [] },
    dataZoom: buildInsideZoom(count),
    gridTops: pct.gridTops,
    cardHeight: pct.cardHeightPx,
  };
}

/**
 * A small text box anchored to the upper-left corner of subplot `gridIdx`.
 * Uses pixel-left so it lines up with `grid.left`, percentage-top so it
 * tracks the subplot as the canvas resizes.
 */
export function cornerInfoBox(lines: string[], gridTopPct: string) {
  const text = lines.join('\n');
  return {
    type: 'text',
    left: GRID_LEFT_PX + 8,
    top: gridTopPct,
    silent: true,
    style: {
      text,
      fill: '#1A1A1A',
      fontSize: 10,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      lineHeight: 12,
      backgroundColor: 'rgba(255, 255, 255, 0.82)',
      borderColor: '#E4E2DC',
      borderWidth: 1,
      padding: [3, 5, 3, 5],
    },
    z: 10,
  };
}

// -----------------------------------------------------------------------------
// Frequency-guide overlays (every FFT subplot).
// -----------------------------------------------------------------------------
export interface FreqGuide {
  freq: number;
  label: string;
  color: string;
  type: 'dashed' | 'dotted';
}

/**
 *   f_BW   = foc_kp / (2π · L_s)    -- closed-loop current bandwidth
 *   N·f_pwm (N = 1, 2, 3)           -- PWM harmonics
 *   f_c                              -- LCL cutoff, only when filter is on
 */
export function freqGuides(meta: SimMeta): FreqGuide[] {
  const fPwm = metaNum(meta, 'slimtorq.f_pwm', 50000);
  const Kp = metaNum(meta, 'slimtorq.foc_kp', NaN);
  const Ls = metaNum(meta, 'slimtorq.l_s', NaN);
  const fBw = Number.isFinite(Kp) && Number.isFinite(Ls) && Ls > 0 ? Kp / (2 * Math.PI * Ls) : NaN;
  const filterOn = metaStr(meta, 'slimtorq.filter_enabled', '0') === '1';
  const fC = filterOn ? metaNum(meta, 'slimtorq.filter_fc', NaN) : NaN;

  const out: FreqGuide[] = [];
  if (Number.isFinite(fBw) && fBw > 1) {
    out.push({ freq: fBw, label: `f_BW=${fmtHz(fBw)}`, color: '#5B5B5B', type: 'dashed' });
  }
  out.push({ freq: fPwm, label: `f_pwm=${fmtHz(fPwm)}`, color: RED_LIMIT, type: 'dotted' });
  out.push({ freq: 2 * fPwm, label: '2·f_pwm', color: RED_LIMIT, type: 'dotted' });
  out.push({ freq: 3 * fPwm, label: '3·f_pwm', color: RED_LIMIT, type: 'dotted' });
  if (Number.isFinite(fC) && fC > 1) {
    out.push({ freq: fC, label: `f_c=${fmtHz(fC)}`, color: '#3B7CC4', type: 'dotted' });
  }
  return out;
}

function fmtHz(f: number): string {
  if (f >= 1000) return `${(f / 1000).toFixed(1)}kHz`;
  return `${f.toFixed(0)}Hz`;
}

export function freqGuideMarkLines(guides: FreqGuide[]) {
  return guides.map((g) => ({
    xAxis: g.freq,
    lineStyle: { color: g.color, type: g.type, width: 1 },
    label: {
      formatter: g.label,
      color: g.color,
      fontSize: 9,
      position: 'insideEndTop' as const,
    },
  }));
}
