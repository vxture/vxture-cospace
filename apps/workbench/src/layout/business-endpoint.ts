// Authorized workbenches always use their own origin; the old 8766 layout host
// keeps its separate local preview backend. Never forward platform cookies to it.
export const businessEndpoint=(import.meta.env.VITE_MODEL_PREVIEW_URL||
 (location.protocol==='file:'||location.port==='8766'?'http://127.0.0.1:8767':location.origin)).replace(/\/$/,'');
