// Mirror of the CSS vars in app/globals.css. Plot trace colors come from here.
// Order matches src/plots.py legacy: text (dark), coralDark (accent), muted (gray).
export const PALETTE = ['#1A1A1A', '#E0543F', '#5B5B5B'] as const;

// Specials used by limit guides and saturation shading.
export const RED_LIMIT = '#D33A2C';
export const SAT_SHADE = 'rgba(247, 110, 92, 0.18)';
