import {defineConfig} from 'vite';
import {createRequire} from 'node:module';
import {cpSync,mkdirSync} from 'node:fs';
import {join,dirname,resolve} from 'node:path';
const require=createRequire(import.meta.url);
const cesium=join(dirname(require.resolve('cesium/package.json')),'Build/Cesium');
function copyAssets(){
 const destination=resolve('public/assets/cesium');mkdirSync(destination,{recursive:true});
 for(const directory of ['Assets','Workers','Widgets','ThirdParty'])cpSync(join(cesium,directory),join(destination,directory),{recursive:true});
}
copyAssets();
export default defineConfig({define:{CESIUM_BASE_URL:JSON.stringify('/assets/cesium/')},server:{port:18894,strictPort:true}});
