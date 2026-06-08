import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        surface: 'var(--surface)',
        'surface-elevated': 'var(--surface-elevated)',
        border: 'var(--border)',
        'border-hover': 'var(--border-hover)',
        primary: {
          DEFAULT: 'var(--primary)',
          hover: 'var(--primary-hover)',
          deep: 'var(--primary-deep)',
          muted: 'var(--primary-muted)',
          glow: 'var(--primary-glow)',
          soft: 'var(--primary-soft)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          deep: 'var(--accent-deep)',
          muted: 'var(--accent-muted)',
          glow: 'var(--accent-glow)',
          soft: 'var(--accent-soft)',
        },
        success: 'var(--success)',
        warning: 'var(--warning)',
        error: 'var(--error)',
      },
      fontFamily: {
        display: ['Space Grotesk', 'Inter', 'system-ui', 'sans-serif'],
        serif: ['Playfair Display', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'monospace'],
      },
      letterSpacing: {
        tesla: '0.18em',
      },
      borderRadius: {
        tesla: '20px',
      },
      boxShadow: {
        primary: '0 4px 14px var(--primary-glow)',
        'primary-lg': '0 8px 30px var(--primary-glow), 0 0 60px rgba(14,165,233,0.08)',
        accent: '0 4px 14px var(--accent-glow)',
        cinematic: '0 24px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03), 0 0 80px rgba(14,165,233,0.02)',
        glass: '0 8px 32px rgba(0,0,0,0.3)',
        'glow-blue': '0 0 40px rgba(14,165,233,0.15)',
        'glow-gold': '0 0 40px rgba(245,158,11,0.15)',
      },
      animation: {
        'fade-in': 'fade-in 0.5s ease-out',
        'slide-up': 'slide-up 0.7s cubic-bezier(0.23, 1, 0.32, 1)',
        'slide-down': 'slide-down 0.5s ease-out',
        'scale-in': 'scale-in 0.4s cubic-bezier(0.23, 1, 0.32, 1)',
        'glow-pulse': 'glow-pulse 4s ease-in-out infinite',
        'glow-breathe': 'glow-breathe 3s ease-in-out infinite',
        float: 'float 8s ease-in-out infinite',
        'float-slow': 'float-slow 12s ease-in-out infinite',
        'orb-drift': 'orb-drift 20s ease-in-out infinite',
      },
      transitionTimingFunction: {
        tesla: 'cubic-bezier(0.23, 1, 0.32, 1)',
      },
      transitionDuration: {
        '400': '400ms',
        '600': '600ms',
        '800': '800ms',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(24px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-down': {
          from: { opacity: '0', transform: 'translateY(-12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        'glow-pulse': {
          '0%, 100%': { boxShadow: '0 0 20px var(--primary-glow)' },
          '50%': { boxShadow: '0 0 40px var(--primary-glow), 0 0 80px rgba(14,165,233,0.08)' },
        },
        'glow-breathe': {
          '0%, 100%': { opacity: '0.5' },
          '50%': { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0px) scale(1)' },
          '50%': { transform: 'translateY(-6px) scale(1.02)' },
        },
        'orb-drift': {
          '0%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(30px, -20px) scale(1.05)' },
          '66%': { transform: 'translate(-20px, 15px) scale(0.98)' },
          '100%': { transform: 'translate(0, 0) scale(1)' },
        },
      },
    },
  },
  plugins: [typography],
}

export default config
