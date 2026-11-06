"""Compare fixed same-space candidates. Surface differences never establish free space."""
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field
from packages.construction.preview_model import PreviewModel, digest
from packages.lifecycle.preview_scope import scope, match

PROFILE = 'cospace.preview-candidate-comparison/0.1'
MAX_CELLS = 500_000


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    space_id: str | None = Field(default=None, min_length=1, max_length=100)
    candidate_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)


class ReviewRequest(CompareRequest):
    comparison_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_unverified: bool
    note: str = Field(min_length=1, max_length=500)


def checksum(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fixed(model):
    if model is None:
        return None
    return {'candidate_id': model.manifest['id'], 'model_manifest_sha256': digest(model.root/'model.json')}


def surface_delta(cells, resolution):
    ordered = sorted(cells)
    bounds = None
    if ordered:
        bounds = [[min(c[i] for c in ordered)*resolution for i in range(3)],
                  [(max(c[i] for c in ordered)+1)*resolution for i in range(3)]]
    return {'count': len(ordered), 'sample_cell_indices': [list(c) for c in ordered[:20]],
            'sample_limit': 20, 'cell_bounds_m': bounds}


def compare_models(base, target, revision, ownership):
    match(target.manifest, ownership)
    if base:
        match(base.manifest, ownership)
    same_frame = base is None or (all(base.manifest.get(k) == target.manifest.get(k) for k in ('frame_id','axes','unit'))
        and base.manifest.get('construction',{}).get('coordinate_scope')==target.manifest.get('construction',{}).get('coordinate_scope'))
    same_grid = base is None or base.resolution == target.resolution
    comparable = same_frame and same_grid
    old_binding=base.manifest.get('source',{}).get('input_binding',{}) if base else {}
    new_binding=target.manifest.get('source',{}).get('input_binding',{})
    revision_only=bool(base and same_grid and new_binding.get('coordinate_revision')
        and old_binding.get('format')==new_binding.get('format')=='ply_pointcloud'
        and all(old_binding.get(k)==new_binding.get(k) and new_binding.get(k) for k in ('id','space_id','snapshot_sha256','cloud_sha256'))
        and old_binding.get('coordinate_revision')!=new_binding.get('coordinate_revision')
        and base.manifest['members']['spatial.npz']['sha256']==target.manifest['members']['spatial.npz']['sha256'])
    if len(target.cells) > MAX_CELLS or (base and len(base.cells) > MAX_CELLS):
        raise ValueError('comparison_cell_limit')
    old = {obj['object_id']: obj for obj in base.semantic_snapshot['objects']} if base and base.semantic_snapshot else {}
    new = {obj['object_id']: obj for obj in target.semantic_snapshot['objects']} if target.semantic_snapshot else {}
    old_ref = base.semantic_snapshot['ontology_ref'] if base and base.semantic_snapshot else None
    new_ref = target.semantic_snapshot['ontology_ref'] if target.semantic_snapshot else None
    added = [new[key] for key in sorted(new.keys()-old.keys())]
    removed = [old[key] for key in sorted(old.keys()-new.keys())]
    modified = []
    for key in sorted(old.keys() & new.keys()):
        fields = [field for field in sorted(new[key]) if old[key][field] != new[key][field]]
        if fields:
            modified.append({'object_id': key, 'fields': fields, 'before': old[key], 'after': new[key]})
    previous = base.cells if base else set()
    def business_links(model):
        doc=getattr(model,'business_snapshot',None)
        if not doc:return {}
        return {b['object_id']:b['ledger_ref'] for b in doc['bindings']}
    before_links=business_links(base);after_links=business_links(target)
    business={'base_available':getattr(base,'business_snapshot',None) is not None,
              'target_available':getattr(target,'business_snapshot',None) is not None,
              'added':[{'object_id':k,'ledger_ref':after_links[k]} for k in sorted(after_links.keys()-before_links.keys())],
              'removed':[{'object_id':k,'ledger_ref':before_links[k]} for k in sorted(before_links.keys()-after_links.keys())],
              'modified':[{'object_id':k,'before':before_links[k],'after':after_links[k]} for k in sorted(before_links.keys()&after_links.keys()) if before_links[k]!=after_links[k]]}
    def relations(model):
        doc=getattr(model,'relation_snapshot',None)
        return {r['relation_id']:r for r in doc['relations']} if doc else {}
    before_rel=relations(base);after_rel=relations(target)
    relation_changes={'base_available':getattr(base,'relation_snapshot',None) is not None,
                      'target_available':getattr(target,'relation_snapshot',None) is not None,
                      'added':[after_rel[k] for k in sorted(after_rel.keys()-before_rel.keys())],
                      'removed':[before_rel[k] for k in sorted(before_rel.keys()-after_rel.keys())],
                      'modified':[{'relation_id':k,'before':before_rel[k],'after':after_rel[k]} for k in sorted(before_rel.keys()&after_rel.keys()) if before_rel[k]!=after_rel[k]]}
    report = {'profile': PROFILE, **ownership, 'selection_revision': revision,
              'base_ref': fixed(base), 'target_ref': fixed(target),
              'coordinate': {'same_frame': same_frame, 'same_resolution': same_grid,
                             'frame_id': target.manifest['frame_id'], 'resolution_m': target.resolution},
              'geometry': {'same_source_model': bool(base and base.manifest['members']['spatial.npz']['sha256'] == target.manifest['members']['spatial.npz']['sha256']),
                           'base_surface_cells': len(previous), 'target_surface_cells': len(target.cells),
                           'cell_comparison': 'comparable' if comparable else 'unavailable_coordinate_or_resolution_changed',
                           'added_surface': surface_delta(target.cells-previous, target.resolution) if comparable else None,
                           'removed_surface': surface_delta(previous-target.cells, target.resolution) if comparable else None,
                           'unlisted_state': 'unknown', 'removed_surface_meaning': 'evidence_removed_not_free_space'},
              'ontology': {'base_ref': old_ref, 'target_ref': new_ref, 'changed': old_ref != new_ref},
              'objects': {'base_available': bool(base and base.semantic_snapshot), 'target_available': bool(target.semantic_snapshot),
                          'added': added, 'removed': removed, 'modified': modified,
                          'unchanged_count': len(old.keys() & new.keys())-len(modified),
                          'meaning': 'annotation_changes_not_confirmed_physical_changes'},
              'business':business,
              'relations':relation_changes,
              'dual_view_impact': {'human': 'target_geometry_and_object_snapshot', 'agent': 'target_surface_and_object_snapshot'},
              'comparison_scope': 'declared_coordinates_not_independent_registration_or_field_change_detection',
              'review_allowed': comparable or revision_only, 'quality': 'unverified', 'robot_ready': False}
    if revision_only:report['coordinate_revision_only']=True
    return report


def compare(jobs, request):
    ownership = scope(jobs.directory, request.space_id)
    selection = jobs.selection(request.space_id)
    if selection['revision'] != request.expected_revision:
        raise ValueError('selection_changed_refresh_required')
    target = jobs.model(request.candidate_id)
    base = jobs.model(selection['candidate_id']) if selection['candidate_id'] else None
    if base and fixed(base)['model_manifest_sha256'] != selection['model_manifest_sha256']:
        raise ValueError('selected_model_integrity_changed')
    report = compare_models(base, target, selection['revision'], ownership)
    return {**report, 'comparison_sha256': checksum(report)}


def confirm(jobs, request):
    if not request.acknowledge_unverified or not request.note.strip():
        raise ValueError('manual_review_acknowledgement_required')
    report = compare(jobs, request)
    if report['comparison_sha256'] != request.comparison_sha256:
        raise ValueError('comparison_changed_refresh_required')
    if not report['review_allowed']:
        raise ValueError('coordinate_or_resolution_review_blocked')
    return jobs.select(request.candidate_id, request.expected_revision, request.space_id,
                       review={'comparison': report, 'note': request.note.strip(),
                               'acknowledge_unverified': True, 'reviewer': 'local_engineer_unverified_identity'})


def validate_review(jobs, previous, model, ownership, review):
    """Called inside the selection lock; reload full snapshots before pointer commit."""
    target = PreviewModel(model.root)
    base = PreviewModel(jobs.root/previous['candidate_id']/'output') if previous['candidate_id'] else None
    if base and fixed(base)['model_manifest_sha256'] != previous['model_manifest_sha256']:
        raise ValueError('selected_model_integrity_changed')
    current = compare_models(base, target, previous['revision'], ownership)
    report = review['comparison']
    if not current['review_allowed'] or checksum(current) != report['comparison_sha256'] or current != {k:v for k,v in report.items() if k!='comparison_sha256'}:
        raise ValueError('comparison_changed_refresh_required')
