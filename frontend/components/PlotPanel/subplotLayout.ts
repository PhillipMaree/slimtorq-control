import type { EChartsOption } from 'echarts';
import type { SimMeta } from '@/types/sim';
import { RED_LIMIT } from '@/lib/palette';
import { axisLog, axisTime, axisValue } from './theme';
import { metaNum, metaStr } from './figures/types';

// -----------------------------------------------------------------------------
// Layout constants. One source of truth for grid padding so info-box overlays
// and titles stay aligned with the chart area.
// -----------------------------------------------------------------------------
const GRID_LEFT_PX = 72;
const GRID_RIGHT_PX = 24;
const TITLE_HEIGHT_PX = 18;
const ROW_GAP_PX = 14;
const SHARED_X_LABEL_PX = 26; // extra bottom padding on the last subplot for `t [ms]`
const TOP_PAD_PX = 10;
const BOTTOM_PAD_PX = 8;

export interface StackedGridOpts {
  count: number;
  // y-axis labels for each subplot (top-to-bottom).
  yLabels: string[];
  // centered title for each subplot (top-to-bottom).
  titles: string[];
  // shared x-axis label (only rendered on bottom subplot). Default 't [ms]'.
  sharedXLabel?: string;
  // per-row plot height in px.
  rowHeight?: number;
}

export interface StackedGridResult {
  title: NonNullable<EChartsOption['title']>;
  grid: NonNullable<EChartsOption['grid']>;
  xAxis: NonNullable<EChartsOption['xAxis']>;
  yAxis: NonNullable<EChartsOption['yAxis']>;
  axisPointer: NonNullable<EChartsOption['axisPointer']>;
  // inside-type dataZoom so users can scroll-to-zoom and drag-to-pan on every
  // subplot in the card. X-axes are linked so all stacked panels zoom in sync.
  dataZoom: NonNullable<EChartsOption['dataZoom']>;
  // top px of each grid (used by cornerInfoBox to anchor overlays).
  gridTops: number[];
  // total card height (px) including the shared x-axis label band.
  cardHeight: number;
}

function buildInsideZoom(count: number): NonNullable<EChartsOption['dataZoom']> {
  const xAxisIndex = Array.from({ length: count }, (_, i) => i);
  const yAxisIndex = Array.from({ length: count }, (_, i) => i);
  return [
    // Scroll wheel zooms the linked x-axes; drag pans them.
    {
      type: 'inside',
      xAxisIndex,
      filterMode: 'none',
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
    },
    // Hold shift + scroll to zoom y on the hovered subplot.
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

/**
 * Build the title / grid / xAxis / yAxis fragments for a vertically-stacked
 * set of time-domain subplots that share a common `t [ms]` x-axis.
 *
 * Each subplot gets:
 *   - a centered title above its grid (text from `titles[i]`)
 *   - its own y-axis with label `yLabels[i]`
 *   - tick labels on every x-axis (so each panel reads independently), but only
 *     the bottom panel gets the `t [ms]` axis-name label rendered.
 */
export function stackedGrid(opts: StackedGridOpts): StackedGridResult {
  const { count, yLabels, titles } = opts;
  const sharedXLabel = opts.sharedXLabel ?? 't [ms]';
  const rowH = opts.rowHeight ?? 140;
  const rowBlockH = TITLE_HEIGHT_PX + rowH;
  const cardHeight = TOP_PAD_PX + count * rowBlockH + (count - 1) * ROW_GAP_PX + SHARED_X_LABEL_PX + BOTTOM_PAD_PX;

  const gridTops: number[] = [];
  const titleFragments: NonNullable<EChartsOption['title']> = [];
  const grids: NonNullable<EChartsOption['grid']> = [];
  const xAxes: NonNullable<EChartsOption['xAxis']> = [];
  const yAxes: NonNullable<EChartsOption['yAxis']> = [];

  for (let i = 0; i < count; i++) {
    const blockTop = TOP_PAD_PX + i * (rowBlockH + ROW_GAP_PX);
    const gridTop = blockTop + TITLE_HEIGHT_PX;
    gridTops.push(gridTop);

    titleFragments.push({
      text: titles[i] ?? '',
      top: blockTop,
      left: 'center',
      textStyle: { fontSize: 12, color: '#1A1A1A', fontWeight: 'normal' },
    });

    const isLast = i === count - 1;
    grids.push({
      left: GRID_LEFT_PX,
      right: GRID_RIGHT_PX,
      top: gridTop,
      height: rowH,
    });
    xAxes.push({
      ...axisTime(isLast ? sharedXLabel : undefined),
      gridIndex: i,
      nameGap: 26,
    });
    yAxes.push({
      ...axisValue(yLabels[i]),
      gridIndex: i,
      nameGap: 50,
    });
  }

  return {
    title: titleFragments,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: buildInsideZoom(count),
    gridTops,
    cardHeight,
  };
}

export interface FreqGridOpts {
  count: number;
  yLabels: string[];
  titles: string[];
  // shared x-axis label, default 'f [Hz]'.
  sharedXLabel?: string;
  rowHeight?: number;
}

/**
 * Same layout pattern as stackedGrid but using log-frequency x-axes. Each FFT
 * subplot gets its own log x-axis (so axis-pointer hover stays accurate per
 * panel) and the shared `f [Hz]` axis label is rendered only on the bottom.
 */
export function freqGrid(opts: FreqGridOpts): StackedGridResult {
  const { count, yLabels, titles } = opts;
  const sharedXLabel = opts.sharedXLabel ?? 'f [Hz]';
  const rowH = opts.rowHeight ?? 160;
  const rowBlockH = TITLE_HEIGHT_PX + rowH;
  const cardHeight = TOP_PAD_PX + count * rowBlockH + (count - 1) * ROW_GAP_PX + SHARED_X_LABEL_PX + BOTTOM_PAD_PX;

  const gridTops: number[] = [];
  const titleFragments: NonNullable<EChartsOption['title']> = [];
  const grids: NonNullable<EChartsOption['grid']> = [];
  const xAxes: NonNullable<EChartsOption['xAxis']> = [];
  const yAxes: NonNullable<EChartsOption['yAxis']> = [];

  for (let i = 0; i < count; i++) {
    const blockTop = TOP_PAD_PX + i * (rowBlockH + ROW_GAP_PX);
    const gridTop = blockTop + TITLE_HEIGHT_PX;
    gridTops.push(gridTop);

    titleFragments.push({
      text: titles[i] ?? '',
      top: blockTop,
      left: 'center',
      textStyle: { fontSize: 12, color: '#1A1A1A', fontWeight: 'normal' },
    });

    const isLast = i === count - 1;
    grids.push({
      left: GRID_LEFT_PX,
      right: GRID_RIGHT_PX,
      top: gridTop,
      height: rowH,
    });
    xAxes.push({
      ...axisLog(isLast ? sharedXLabel : undefined),
      gridIndex: i,
      nameGap: 26,
    });
    yAxes.push({
      ...axisLog(yLabels[i]),
      gridIndex: i,
      nameGap: 50,
    });
  }

  return {
    title: titleFragments,
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    axisPointer: { link: [] },
    dataZoom: buildInsideZoom(count),
    gridTops,
    cardHeight,
  };
}

/**
 * A small text box anchored to the upper-left corner of subplot `gridIdx`.
 * Returns a `graphic` group fragment to spread into `option.graphic = [...]`.
 *
 * The box uses absolute pixel positioning so it lines up with grid.left /
 * grid.top from stackedGrid / freqGrid. `lines` are joined with newlines.
 */
export function cornerInfoBox(lines: string[], gridTopPx: number) {
  const text = lines.join('\n');
  return {
    type: 'text',
    left: GRID_LEFT_PX + 8,
    top: gridTopPx + 4,
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
 * Single source of truth for FFT vertical reference lines. Returns the list
 * derived from parquet metadata; FFT figure builders pass these into each
 * series' `markLine.data`.
 *
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

/**
 * Convert a list of FreqGuides into an ECharts markLine `data` array, with the
 * label rendered above the line (rotated and small to avoid clutter).
 */
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
