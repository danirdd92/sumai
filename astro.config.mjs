// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: 'https://danirdd92.github.io',
  base: '/sumai',
  vite: {
    plugins: [tailwindcss()]
  }
});