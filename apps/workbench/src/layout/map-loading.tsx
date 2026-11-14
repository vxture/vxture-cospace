import {SpatialMotif} from './spatial-motif';
import './map-loading.css';

/** Shared by the eager route, lazy engines and SDK initialization. */
export function MapLoading({overlay=false}:{readonly overlay?:boolean}){
 return <div className={'map-loading'+(overlay?' map-loading-overlay':'')} role="status" aria-live="polite">
  <div className="map-loading-content">
   <SpatialMotif className="map-loading-motif"/>
   <p>正在加载地图<span className="map-loading-dots" aria-hidden="true"><i/><i/><i/></span></p>
  </div>
 </div>;
}
