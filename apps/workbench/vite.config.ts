import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  base: '/workbench/',
  plugins: [tailwindcss()],
  build: { rolldownOptions: { input: { main: fileURLToPath(new URL('./index.html', import.meta.url)), layout: fileURLToPath(new URL('./layout.html', import.meta.url)) } } },
  server: { proxy: { '/scenes': 'http://127.0.0.1:8000', '/query': 'http://127.0.0.1:8000' } },
});
