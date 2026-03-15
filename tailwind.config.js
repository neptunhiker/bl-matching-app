/** @type {import('tailwindcss').Config} */

// BeginnerLuft design system
// --bl-primary-color   : #948afc  → primary-500
// --bl-secondary-color : #FFACE4  → secondary-400
// --bl-tertiary-color  : #1A1B41  → tertiary-700
// --bl-dark-purple     : #4B0082  → tertiary-600
// --bl-exciting-bg-img : linear-gradient(90deg, primary → secondary)

module.exports = {
  content: [
    "./templates/**/*.html",       // project templates
    "./**/templates/**/*.html",    // templates inside Django apps
    "./**/*.py",                   // class names sometimes appear in Python
    "./static/src/**/*.js",        // if you ever add Alpine/JS components
  ],

  theme: {
    extend: {
      colors: {
        primary: {
          50:  '#F4F3FF',
          100: '#E9E6FF',
          200: '#D7D2FF',
          300: '#BDB5FF',
          400: '#A79EFF',
          500: '#948AFC',
          600: '#7A70E8',
          700: '#6258C7',
          800: '#4C449F',
          900: '#37327A',
        },

        secondary: {
          50:  '#FFF5FD',
          100: '#FFE6F9',
          200: '#FFD6F3',
          300: '#FFBCEB',
          400: '#FFACE4',
          500: '#F98CD4',
          600: '#E56AC1',
          700: '#C84CA7',
          800: '#9F3C86',
          900: '#6F2B5D',
        },

        tertiary: {
          50:  '#EEEFF8',
          100: '#D5D5EF',
          200: '#ABABDE',
          300: '#8182CE',
          400: '#5758BD',
          500: '#3D3E8F',
          600: '#4B0082',
          700: '#1A1B41',
          800: '#13143A',
          900: '#0C0D22',
        },

        neutral: {
          50:  '#F8F7FF',
          100: '#F1F0F7',
          200: '#E5E5EF',
          300: '#D2D2DE',
          400: '#A8A8B8',
          500: '#6B7280',
          600: '#4B5563',
          700: '#374151',
          800: '#2F2F3A',
          900: '#1F1F29',
        },
      },

      backgroundImage: {
        'bl-gradient': 'linear-gradient(90deg, #948AFC, #FFACE4)',
        'bl-gradient-br': 'linear-gradient(135deg, #948AFC, #FFACE4)',
      },

      fontFamily: {
        sans:  ['Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        serif: ['Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        jakarta: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        inter: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
    },
  },

  plugins: [],
}