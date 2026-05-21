import { buildFftFigure } from './fftHelpers';

export const buildIabcFft = buildFftFigure({
  signalCol: 'i_a',
  traceName: '|\\text{FFT}(i_a)|',
  yLabel: 'mag [A, norm]',
  pwmGuides: [1],
  pwmGuideLabel: () => 'f_pwm',
});
