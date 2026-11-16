// Independent byte consumer. Integrity/reference checks are not full Python domain validation.
import { open, realpath } from 'node:fs/promises';
import { resolve, relative, isAbsolute } from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const roles = ['entities', 'geometry', 'structure', 'observations'];
const dependencies = { entities: [], geometry: ['entities'], structure: ['entities', 'geometry'], observations: ['entities'] };
const idPattern = /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$/;
function requireThat(test, message) { if (!test) throw new Error(message); }
function identity(value) { requireThat(typeof value === 'string' && idPattern.test(value), 'invalid_identity'); return value; }
function array(value, maximum) { requireThat(Array.isArray(value) && value.length <= maximum, 'array_budget'); return value; }
function parse(raw) {
  const value = JSON.parse(raw), pending = [[value, 0]];
  let count = 0;
  while (pending.length) {
    const [item, depth] = pending.pop();
    requireThat(depth <= 64 && ++count <= 500000, 'json_structure_budget');
    if (typeof item === 'number') requireThat(Number.isFinite(item), 'finite_number_required');
    if (item && typeof item === 'object') for (const child of Object.values(item)) pending.push([child, depth + 1]);
  }
  return value;
}
function indexed(value, maximum) {
  const rows = array(value, maximum), result = new Map();
  for (const row of rows) { identity(row.id); requireThat(!result.has(row.id), 'duplicate_identity'); result.set(row.id, row); }
  return result;
}
async function bytes(path, maximum) {
  const file = await open(path, 'r');
  try {
    requireThat((await file.stat()).isFile(), 'file_required');
    const buffer = Buffer.alloc(maximum + 1);
    let length = 0;
    while (length <= maximum) {
      const read = await file.read(buffer, length, buffer.length - length, null);
      if (!read.bytesRead) break;
      length += read.bytesRead;
    }
    requireThat(length <= maximum, 'byte_budget');
    return buffer.subarray(0, length);
  } finally { await file.close(); }
}
async function member(root, name) {
  const path = await realpath(resolve(root, name)), rel = relative(root, path);
  requireThat(rel !== '..' && !rel.startsWith('../') && !rel.startsWith('..\\') && !isAbsolute(rel), 'member_outside_root');
  return path;
}
function pin(value) {
  identity(value.scene_id); identity(value.snapshot_id);
  requireThat(typeof value.sha256 === 'string' && /^[a-f0-9]{64}$/.test(value.sha256), 'invalid_source_pin');
  return [value.scene_id, value.snapshot_id, value.sha256];
}
function references(payloads, manifest) {
  const catalog = payloads.entities;
  requireThat(catalog.profile === 'cospace.synthetic-scene-graph/0.1' && catalog.data_kind === 'synthetic', 'synthetic_only');
  requireThat(catalog.scene_id === manifest.source.scene_id && catalog.snapshot_id === manifest.subset_snapshot_id, 'snapshot_binding');
  requireThat(catalog.frame?.unit === 'm', 'frame_unit');
  const entities = indexed(catalog.entities, 1000), geometry = indexed(payloads.geometry, 4000);
  const included = [...array(manifest.requested_ids, 128), ...array(manifest.dependency_ids, 1000)];
  requireThat(new Set(included).size === included.length && included.length === entities.size, 'selection_identity');
  for (const id of included) requireThat(entities.has(identity(id)), 'selection_reference');
  for (const entity of entities.values()) {
    for (const id of array(entity.geometry_ids, 32)) requireThat(geometry.get(id)?.entity_id === entity.id, 'entity_geometry_reference');
  }
  for (const row of geometry.values()) {
    requireThat(entities.get(row.entity_id)?.geometry_ids.includes(row.id), 'geometry_entity_reference');
    requireThat(row.frame_id === catalog.frame.id, 'geometry_frame');
  }
  const structure = payloads.structure;
  for (const row of indexed(structure.relations, 4000).values()) {
    requireThat(entities.has(row.source_id) && entities.has(row.target_id), 'relation_reference');
  }
  for (const row of indexed(structure.connections, 1000).values()) {
    requireThat(entities.has(row.connector_id) && array(row.ports, 2).length === 2, 'connection_reference');
    for (const port of row.ports) {
      requireThat(entities.get(port.space_id)?.kind === 'space', 'port_space');
      requireThat(geometry.get(port.geometry_id)?.entity_id === row.connector_id, 'port_geometry');
    }
  }
  const sources = indexed(catalog.sources, 64);
  for (const row of indexed(payloads.observations, 2000).values()) {
    requireThat(entities.has(row.entity_id) && sources.has(row.source_id), 'observation_reference');
  }
  return entities;
}

export async function consume(directory, expectedSource, operation, identityValue) {
  const root = await realpath(directory);
  const wrapper = parse(await bytes(await member(root, 'manifest.json'), 1024 * 1024));
  requireThat(wrapper.profile === 'cospace.synthetic-subset-files/0.1', 'exchange_profile');
  const manifest = wrapper.manifest;
  requireThat(manifest.profile === 'cospace.synthetic-scene-subset/0.1' && manifest.data_kind === 'synthetic', 'synthetic_only');
  requireThat(JSON.stringify(pin(manifest.source)) === JSON.stringify(pin(expectedSource)), 'source_binding');
  const components = array(manifest.components, 4);
  requireThat(components.length === 4 && new Set(components.map(c => c.role)).size === 4, 'component_roles');
  const payloads = {};
  let total = 0;
  for (const component of components) {
    requireThat(roles.includes(component.role), 'unsupported_component');
    requireThat(JSON.stringify(component.depends_on) === JSON.stringify(dependencies[component.role]), 'component_dependencies');
    requireThat(Number.isInteger(component.bytes) && component.bytes > 0 && component.bytes <= 2 * 1024 * 1024, 'component_byte_budget');
    const raw = await bytes(await member(root, `${component.role}.json`), component.bytes);
    total += raw.length;
    requireThat(total <= 4 * 1024 * 1024, 'package_byte_budget');
    requireThat(raw.length === component.bytes && createHash('sha256').update(raw).digest('hex') === component.sha256, 'component_integrity');
    payloads[component.role] = parse(raw);
  }
  const entities = references(payloads, manifest);
  const id = identity(identityValue);
  requireThat(['entity', 'connections'].includes(operation), 'unsupported_operation');
  let items = [];
  if (entities.has(id)) {
    items = operation === 'entity' ? [{entity: entities.get(id), geometry: payloads.geometry.filter(g => g.entity_id === id)}] :
      payloads.structure.connections.filter(c => c.connector_id === id || c.ports.some(p => p.space_id === id));
  }
  return { outcome: !entities.has(id) ? 'out_of_scope' : items.length ? 'found' : 'no_match', items,
    source: manifest.source, subset_snapshot_id: manifest.subset_snapshot_id, data_kind: 'synthetic',
    validation_scope: 'byte_integrity_and_reference_closure_only', query_scope: 'package_only',
    source_content_verified: false, incident_connections_complete: false, full_scene_coverage: false,
    real_release_ready: false, robot_ready: false };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const [directory, expectedFile, operation, id] = process.argv.slice(2);
    requireThat(process.argv.length === 6, 'usage: read-subset.mjs DIRECTORY TRUSTED_PIN entity|connections ID');
    const expected = parse(await bytes(expectedFile, 4096));
    console.log(JSON.stringify(await consume(directory, expected, operation, id), null, 2));
  } catch (error) { console.error(JSON.stringify({error: error.message})); process.exitCode = 2; }
}
