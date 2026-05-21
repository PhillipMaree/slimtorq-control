import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        alva: {
          bg: '#FAFAF7',
          panel: '#FFFFFF',
          border: '#E4E2DC',
          text: '#1A1A1A',
          muted: '#5B5B5B',
          coral: '#F76E5C',
          coralDark: '#E0543F',
          ok: '#2E7D32',
        },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
