// Pointer/keyboard intent starts the large engine download before activation.
export const loadGlobe=()=>import('./scene-globe');
export function preloadGlobe(){void loadGlobe().catch(()=>{/* Activation exposes the normal loading/error state. */});}
