import { buildFftFigure } from './fftHelpers';

export const buildIqFft = buildFftFigure({
  signalCol: 'i_q_meas',
  traceName: '|\\text{FFT}(i_q^{\\,meas})|',
  yLabel: 'mag [A, norm]',
  pwmGuides: [1, 2, 3],
  pwmGuideLabel: (k) => `${k}·f_pwm`,
});
