import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        bg: '#fafafa',
        surface: '#ffffff',
        border: '#e5e7eb',
        text: '#111111',
        muted: '#6b7280',
        accent: '#0071e3',
        success: '#34c759',
        warning: '#ff9500',
        danger: '#ff3b30',
        // Platform colors
        linkedin: '#0a66c2',
        naukri: '#ff7555',
        internshala: '#00c6ae',
        unstop: '#6c2dc7',
      },
      borderRadius: {
        DEFAULT: '12px',
        sm: '8px',
        lg: '16px',
        xl: '20px',
      },
    },
  },
  plugins: [],
} satisfies Config
