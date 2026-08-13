/** @type {import('tailwindcss').Config} */
export default {
  content: ['./parquet/ui/index.html', './parquet/ui/src/**/*.{ts,tsx}'],
  theme: { extend: { colors: { parquet: { green: '#00ff88', red: '#ff3957', amber: '#f5a623' } } } },
  plugins: [],
}
