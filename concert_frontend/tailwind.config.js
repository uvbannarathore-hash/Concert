/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        void: '#0B0A10',        // near-black stage background
        stage: '#151320',        // panel/card surface, slightly lifted
        stage2: '#1E1B2E',       // hover/lifted surface
        edge: '#2E2A40',         // hairline borders
        haze: '#8B87A0',         // muted secondary text
        paper: '#F3F1F8',        // primary text on dark
        spot: '#FF3D6E',         // spotlight accent (hot magenta-red)
        spot2: '#FFC857',        // amber follow-spot, secondary accent
        go: '#43D9A3',           // success/confirmed
      },
      fontFamily: {
        display: ['"Anton"', '"Archivo Black"', 'sans-serif'],
        body: ['"Inter"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      backgroundImage: {
        'spot-radial': 'radial-gradient(ellipse 80% 60% at 50% -10%, rgba(255,61,110,0.25), transparent 60%)',
        'glass-gradient': 'linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
        'glow-gradient': 'linear-gradient(90deg, transparent, rgba(255,61,110,0.1), transparent)',
      },
      animation: {
        'fade-in-up': 'fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in': 'fadeIn 0.4s ease-out forwards',
        'scale-in': 'scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
        'shimmer': 'shimmer 2.5s infinite linear',
        'pulse-glow': 'pulseGlow 2.5s infinite ease-in-out',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.15' },
          '50%': { opacity: '0.45' },
        },
      },
    },
  },
  plugins: [],
}
