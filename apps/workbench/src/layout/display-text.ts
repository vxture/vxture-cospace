// Internal identifiers are transport keys, never user-facing labels.
const internalIdentifier=/\b(?:[a-z][a-z0-9]*[_-])?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b(?:usr|org|ws)_[a-z0-9_-]+\b|\b(?:space|project)-[a-f0-9]{16}\b/gi;
export function displayText(value:string|undefined|null,fallback='名称待补全'){
 const text=value?.replace(internalIdentifier,'').trim();
 return text||fallback;
}
