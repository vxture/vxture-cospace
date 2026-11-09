import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig(({mode})=>({
  base: '/',
  // Shareable lab builds never read the developer's private map key.
  envDir: mode==='map-lab'?fileURLToPath(new URL('../../var/map-lab-empty-env/',import.meta.url)):undefined,
  plugins: [tailwindcss()],
  build: { rolldownOptions: { input: (mode==='map-lab'?{mapLab:fileURLToPath(new URL('./map-lab.html',import.meta.url))}:{ main: fileURLToPath(new URL('./index.html', import.meta.url)) }) as Record<string,string> } },
  server: { proxy: { '/scenes': 'http://127.0.0.1:8000', '/query': 'http://127.0.0.1:8000' } },
}));
