import autoprefixer from 'autoprefixer'
import tailwindcss from 'tailwindcss'
import config from './tailwind.config.mjs'

export default { plugins: [tailwindcss(config), autoprefixer()] }
