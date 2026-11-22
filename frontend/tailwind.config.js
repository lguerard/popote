/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // Titres du tableau de bord : police arrondie du système, sans
      // dépendance externe (serveur auto-hébergé).
      fontFamily: {
        display: ['ui-rounded', '"SF Pro Rounded"', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#fff7ed',
          100: '#ffedd5',
          500: '#f97316',
          600: '#ea580c',
          700: '#c2410c',
        },
      },
    },
  },
  plugins: [],
}
