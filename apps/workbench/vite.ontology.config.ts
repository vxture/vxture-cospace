import tailwindcss from '@tailwindcss/vite';
import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vite';

export default defineConfig({
  root: fileURLToPath(new URL('./ontology-standalone', import.meta.url)),
  envDir: false,
  publicDir: false,
  plugins: [tailwindcss()],
  resolve: {dedupe: ['react', 'react-dom']},
  build: {outDir: fileURLToPath(new URL('../../var/ontology-workbench', import.meta.url)), emptyOutDir: true},
});
