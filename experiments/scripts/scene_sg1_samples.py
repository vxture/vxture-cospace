"""Reproducible synthetic SG1 fixtures; never import or alter runtime data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from experiments.scripts.scene_graph_sample import sample
from packages.spatial.scene_identity import snapshot_ref, validate_identity_changes
from packages.spatial.scene_legacy import project_legacy_anchors
from packages.views.agent.scene_subset import build_scene_subset


def merged_sample(base):
    merged = deepcopy(base)
    merged['snapshot_id'] = 'synthetic-snapshot-03'
    entity = next(e for e in merged['entities'] if e['id'] == 'room-l1')
    entity.update(id='room-l1-merged', name='合成合并空间', geometry_ids=['room-l1-merged-bounds'])
    geometry = next(g for g in merged['geometry'] if g['entity_id'] == 'room-l1')
    geometry.update(id='room-l1-merged-bounds', entity_id=entity['id'])
    merged['relations'] = [r for r in merged['relations']
                           if 'room-l1' not in {r['source_id'], r['target_id']}]
    merged['connections'] = [c for c in merged['connections']
                             if not any(p['space_id'] == 'room-l1' for p in c['ports'])]
    return merged


def identity_samples():
    base = sample()
    target = deepcopy(base)
    target['snapshot_id'] = 'synthetic-snapshot-02'
    original = next(e for e in base['entities'] if e['id'] == 'room-l1')
    target['entities'] = [e for e in target['entities'] if e['id'] != original['id']]
    target['geometry'] = [g for g in target['geometry'] if g['entity_id'] != original['id']]
    target['relations'] = [r for r in target['relations']
                           if original['id'] not in {r['source_id'], r['target_id']}]
    for suffix, bounds in [('a', [[0., 2., 0.], [4., 8., 3.]]),
                           ('b', [[4., 2., 0.], [8., 8., 3.]])]:
        entity = deepcopy(original)
        entity.update(id='room-l1-'+suffix, name='合成拆分空间 '+suffix,
                       geometry_ids=['room-l1-'+suffix+'-bounds'])
        geometry = deepcopy(next(g for g in base['geometry'] if g['entity_id'] == original['id']))
        geometry.update(id=entity['geometry_ids'][0], entity_id=entity['id'])
        geometry['value']['bounds'] = bounds
        target['entities'].append(entity)
        target['geometry'].append(geometry)
    # No containment or door-side relation is guessed for the newly split spaces.
    # The previous door-to-room connection is withdrawn until its endpoints are reviewed.
    target['connections'] = [c for c in target['connections']
                             if not any(p['space_id'] == original['id'] for p in c['ports'])]
    drafts = {}
    for kind, before, after, before_ids, after_ids in [
        ('split', base, target, ['room-l1'], ['room-l1-a', 'room-l1-b']),
        ('merge', target, merged_sample(base), ['room-l1-a', 'room-l1-b'], ['room-l1-merged']),
        ('unresolved', base, target, ['room-l1'], ['room-l1-a', 'room-l1-b']),
    ]:
        draft = {'profile': 'cospace.synthetic-identity-changes/0.1', 'data_kind': 'synthetic',
                 'base': snapshot_ref(before), 'target': snapshot_ref(after),
                 'events': [{'id': 'proposal-'+kind, 'kind': kind, 'before_ids': before_ids,
                             'after_ids': after_ids, 'assessment': 'unverified',
                             'reason': 'Synthetic alternative proposal; not an identity approval.'}]}
        validate_identity_changes(draft, before, after)
        drafts[kind] = draft
    return base, target, drafts


def legacy_sample():
    digest = 'a'*64
    document = {
        'profile': 'cospace.preview-objects/0.1', 'model_id': 'build-'+'1'*16,
        'annotation_id': 'annotation-'+'2'*16, 'created_at': '2026-11-16T00:00:00Z',
        'frame_id': 'synthetic-local', 'unit': 'm', 'space_id': 'space-'+'3'*16,
        'project_id': 'project-'+'4'*16, 'source_model_sha256': digest,
        'ontology_ref': {'ontology_id': 'synthetic-old', 'version': '0.1.0', 'sha256': 'b'*64},
        'base_candidate_ref': {'candidate_id': 'build-'+'5'*16, 'model_manifest_sha256': 'c'*64},
        'objects': [{'object_id': 'cabinet', 'type_id': 'old-cabinet', 'properties': {},
                     'anchor_m': [1., 6., 0.], 'confirmation': 'unverified',
                     'evidence': {'kind': 'model_point', 'member': 'spatial.npz',
                                  'sha256': digest, 'point_index': 0}}],
    }
    raw = (json.dumps(document, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    mapping = {'profile': 'cospace.legacy-anchor-mapping/0.1',
               'source_document_sha256': hashlib.sha256(raw).hexdigest(),
               'source_space_id': document['space_id'], 'source_model_id': document['model_id'],
               'source_model_sha256': digest, 'source_frame_id': document['frame_id'],
               'mappings': [{'source_type_id': 'old-cabinet', 'target_type_id': 'cabinet'}]}
    return raw, mapping


def write_samples(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base, target, drafts = identity_samples()
    raw, mapping = legacy_sample()
    docs = {'target.synthetic.json': target, 'merged.synthetic.json': merged_sample(base),
            **{kind+'.synthetic.json': draft for kind, draft in drafts.items()},
            'legacy-mapping.synthetic.json': mapping,
            'legacy-projection.synthetic.json': project_legacy_anchors(raw, mapping),
            'corridor-subset.synthetic.json': build_scene_subset(base, ['corridor-l1'])}
    for name, document in docs.items():
        (output/name).write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'legacy-objects.synthetic.json').write_bytes(raw)
