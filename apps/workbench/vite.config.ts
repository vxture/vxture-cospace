import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';
import {cpSync,mkdirSync,createReadStream,statSync} from 'node:fs';
import {resolve} from 'node:path';

export default defineConfig(({mode})=>({
  base: '/',
  // Shareable lab builds never read the developer's private map key.
  envDir: mode==='map-lab'?fileURLToPath(new URL('../../var/map-lab-empty-env/',import.meta.url)):undefined,
  plugins: [tailwindcss(),{
    name:'cesium-assets',
    configureServer(server){server.middlewares.use('/assets/cesium',(request,response,next)=>{
      const root=resolve('node_modules/cesium/Build/Cesium');
      const file=resolve(root,'.'+decodeURIComponent((request.url||'/').split('?')[0]));
      if(!file.startsWith(root+'/')&&!file.startsWith(root+'\\'))return next();
      try{if(!statSync(file).isFile())return next();}catch{return next();}
      const ext=file.split('.').pop();response.setHeader('Content-Type',ext==='js'?'text/javascript':ext==='json'?'application/json':ext==='png'?'image/png':ext==='jpg'?'image/jpeg':ext==='wasm'?'application/wasm':'application/octet-stream');
      createReadStream(file).pipe(response);
    });},
    writeBundle(options){const dest=resolve(options.dir||'dist','assets/cesium');mkdirSync(dest,{recursive:true});for(const name of ['Assets','Workers','ThirdParty','Widgets'])cpSync(resolve('node_modules/cesium/Build/Cesium',name),resolve(dest,name),{recursive:true});},
  }],
  define:{CESIUM_BASE_URL:JSON.stringify('/assets/cesium/')},
  build: { rolldownOptions: { input: (mode==='map-lab'?{mapLab:fileURLToPath(new URL('./map-lab.html',import.meta.url))}:{ main: fileURLToPath(new URL('./index.html', import.meta.url)) }) as Record<string,string> } },
  server: { proxy: { '/scenes': 'http://127.0.0.1:8000', '/query': 'http://127.0.0.1:8000' } },
}));
