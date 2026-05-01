import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"General Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Genesis primary
        primary: {
          DEFAULT: '#6366F1', // indigo
          hover: '#4F46E5',
        },
        secondary: '#20970B', // green — RESERVED for brand highlight only
        // Surfaces
        bg: '#FAFAFA',
        surface: '#FFFFFF',
        border: '#E8E8EC',
        // Text
        text: {
          DEFAULT: '#0A0A0A', // near-black headings/body
          secondary: '#6B6B6B',
        },
        muted: '#9C9C9C', // placeholders, timestamps, disabled
        // Semantic
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        danger: '#EF4444', // alias for back-compat with existing code that uses 'danger'
        accent: '#6366F1', // alias — many existing components reference 'accent'; map it to primary so they still work
        // Platform colors — keep for badges
        linkedin: '#0A66C2',
        naukri: '#FF7555',
        ats: '#7C3AED',
      },
      borderRadius: {
        DEFAULT: '6px', // buttons, inputs
        sm: '4px',      // chips, tags, inline code
        md: '8px',      // metadata cards, dropdowns, panels
        lg: '12px',     // kit/preview cards, search bar
        xl: '16px',
        full: '9999px',
      },
      boxShadow: {
        'card-hover': '0 8px 30px rgba(0,0,0,0.08)',
        'btn-glow': '0 4px 12px rgba(99,102,241,0.35)',
        'focus-ring': '0 0 0 3px rgba(99,102,241,0.12)',
      },
      fontSize: {
        display: ['72px', { lineHeight: '1.05', letterSpacing: '-0.04em' }],
        headline: ['60px', { lineHeight: '1.1', letterSpacing: '-0.04em' }],
        section: ['32px', { lineHeight: '1.2', letterSpacing: '-0.03em' }],
        subhead: ['24px', { lineHeight: '1.3', letterSpacing: '-0.02em' }],
        body: ['15px', { lineHeight: '1.5' }],
        small: ['13px', { lineHeight: '1.5' }],
        caption: ['12px', { lineHeight: '1.4' }],
        overline: ['11px', { lineHeight: '1.4', letterSpacing: '0.08em' }], // used uppercase
      },
    },
  },
  plugins: [],
} satisfies Config
