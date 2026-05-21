import { buildFftFigure } from './fftHelpers';

export const buildOmegaFft = buildFftFigure({
  signalCol: 'omega_m_meas',
  traceName: '|\\text{FFT}(\\omega_m^{\\,meas})|',
  yLabel: 'mag [rad/s, norm]',
});
