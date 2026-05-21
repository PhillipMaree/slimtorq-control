import FFT from 'fft.js';

// Real-input FFT magnitude, mirroring numpy.fft.rfft semantics used by
// src/plots.py figure_iq_fft / figure_fft_omega / figure_iabc_fft.
// Returns { freqs, mag } where freqs is in Hz given dt (sample period).

export interface FftResult {
  freqs: Float64Array;
  mag: Float64Array;
}

function nextPow2(n: number): number {
  let p = 1;
  while (p < n) p <<= 1;
  return p;
}

export function rfftMagnitude(signal: Float64Array, dt: number): FftResult {
  if (signal.length === 0) {
    return { freqs: new Float64Array(0), mag: new Float64Array(0) };
  }
  const N = nextPow2(signal.length);
  const fft = new FFT(N);
  const input = fft.createComplexArray();
  for (let i = 0; i < signal.length; i++) {
    input[2 * i] = signal[i];
    input[2 * i + 1] = 0;
  }
  const out = fft.createComplexArray();
  fft.transform(out, input);
  const half = Math.floor(N / 2) + 1;
  const mag = new Float64Array(half);
  const freqs = new Float64Array(half);
  const fs = 1 / dt;
  for (let k = 0; k < half; k++) {
    const re = out[2 * k];
    const im = out[2 * k + 1];
    mag[k] = Math.sqrt(re * re + im * im) / signal.length;
    freqs[k] = (k * fs) / N;
  }
  return { freqs, mag };
}

// Trailing-window slice used by the FFT figures: the last `frac` fraction of
// a signal. src/plots.py uses 80% trailing for steady-state analysis.
export function tail(signal: Float64Array, frac = 0.8): Float64Array {
  const start = Math.floor(signal.length * (1 - frac));
  return signal.subarray(start);
}
