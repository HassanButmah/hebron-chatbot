/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#006633',
          light: '#008040',
          dark: '#004d26',
        },
      },
      fontFamily: {
        arabic: ['Cairo', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

