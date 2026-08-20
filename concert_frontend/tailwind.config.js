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
      },
    },
  },
  plugins: [],
}
