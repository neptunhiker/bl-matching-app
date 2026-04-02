/** @type {import('tailwindcss').Config} */

// ─────────────────────────────────────────────────────────────────────────────
// BeginnerLuft design system — single source of truth for all design tokens.
//
// Color family usage:
//   primary   — core CTAs, focus rings, active states, interactive highlights
//   secondary — decorative accents, soft section tints, secondary badges
//   tertiary  — headings, high-contrast body text, dark button variant
//   neutral   — borders, dividers, placeholder text, generic UI scaffolding
//
// Brand anchor values:
//   primary-500   #948AFC  ← gradient start, badge background base
//   secondary-400 #FFACE4  ← gradient end, secondary button background
//   tertiary-700  #1A1B41  ← headings, body text, tertiary button background
//   tertiary-600  #4B0082  (dark purple accent, use sparingly)
//
// Gradients (see backgroundImage section below):
//   bg-bl-gradient     — 90° horizontal: primary → secondary (navbar, accents)
//   bg-bl-gradient-br  — 135° diagonal:  primary → secondary (hero, cards)
//   Text clip usage:   bg-bl-gradient bg-clip-text text-transparent
//
// Components (HTML partials included via {% include %}):
//   templates/components/_button.html    — buttons and link buttons
//   templates/components/_badge.html     — status pill badges
//   templates/components/_card.html      — content cards
//   templates/components/_navbar.html    — sticky top navigation
//   templates/components/_layout.html    — page section wrapper with header
//   profiles/templates/profiles/_form_field.html — styled Django form fields
//
// Full reference: docs/design_system_guide.md
// ─────────────────────────────────────────────────────────────────────────────

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
        // Primary brand family: use for main CTA and interaction emphasis.
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

        // Secondary accent family: use sparingly for supportive highlights.
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

        // Tertiary family: use for strong text, headers, and dark surfaces.
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

        // Neutral family: use for base text, borders, and general UI scaffolding.
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
        // Branded gradients for nav bars, section headers, and visual separators.
        'bl-gradient': 'linear-gradient(90deg, #948AFC, #FFACE4)',
        'bl-gradient-br': 'linear-gradient(135deg, #948AFC, #FFACE4)',
      },

      fontFamily: {
        sans: ['"Source Serif 4"', 'Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        serif: ['"Source Serif 4"', 'Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif'],
        jakarta: ['"Source Serif 4"', 'serif'],
        dm_sans: ['"Source Serif 4"', 'serif'],
        manrope: ['"Source Serif 4"', 'serif'],
        source_serif: ['"Source Serif 4"', 'serif'],
        inter: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
    },
  },

  plugins: [],
}