/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        clinical: {
          bg: '#F4F8F5',
          surface: '#FFFFFF',
          secondary: '#EEF7F1',
          primary: '#047857',
          primaryDark: '#064E3B',
          text: '#172033',
          muted: '#667085',
          border: '#E4E7EC',
          cgm: '#0F766E',
          success: '#16A34A',
          warning: '#D97706',
          critical: '#DC2626',
        },
      },
      boxShadow: {
        clinical: '0 1px 2px rgba(16, 24, 40, 0.06)',
      },
    },
  },
  plugins: [],
};
