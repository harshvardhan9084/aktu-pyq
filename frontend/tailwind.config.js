/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-display)', 'serif'],
        body:    ['var(--font-body)', 'sans-serif'],
        mono:    ['var(--font-mono)', 'monospace'],
      },
      colors: {
        ink: {
          900: '#0a0a0f', 800: '#12121a', 700: '#1c1c28', 600: '#2a2a3d',
          500: '#3d3d58', 400: '#6b6b8a', 300: '#9494b0', 200: '#c4c4d8',
          100: '#e8e8f0', 50:  '#f5f5fa',
        },
        gold: { 500: '#e8b84b', 400: '#f0ca6e', 300: '#f5da96' },
        jade: { 500: '#2ec4a0', 400: '#4fd4b4', 300: '#7de3cc' },
        rose: { 600: '#c94040', 500: '#e05252', 400: '#ea7070' },
      },
      animation: {
        'fade-up': 'fadeUp 0.5s ease forwards',
        'fade-in': 'fadeIn 0.4s ease forwards',
        'shimmer': 'shimmer 2s linear infinite',
        'ping':    'ping 1.5s cubic-bezier(0,0,0.2,1) infinite',
      },
      keyframes: {
        fadeUp:   { '0%': { opacity: 0, transform: 'translateY(16px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        fadeIn:   { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        shimmer:  { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        ping:     { '75%,100%': { transform: 'scale(2)', opacity: '0' } },
      },
    },
  },
  plugins: [],
}
