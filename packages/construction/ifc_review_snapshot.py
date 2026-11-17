"""Compose fixed review inputs; never adopt candidates as field facts."""
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from packages.construction.ifc_structure_review import structure_review
from packages.ontology.ifc_mapping import Mapping, propose_structure_types
from packages.spatial.ifc_annotations import Area, ConnectionAnnotation, Evidence, Worksheet, seed, validate_annotations
from packages.spatial.scene_graph import Fixed
from packages.spatial.scene_identity import Digest, canonical, content_digest
from packages.views.agent.ifc_offline_package import export_design_package, read_design_package
from packages.views.agent.ifc_structure_exchange import SourcePin, _unique

MAX_BYTES = 8 * 1024 * 1024


class AnnotationLayer(Fixed):
    original_worksheet_sha256: Digest
    original_review_sha256: Digest
    # Reuse field types and limits, with provenance separate from snapshot source context.
    evidence: Annotated[list[Evidence], Field(max_length=1024)]
    areas: Annotated[list[Area], Field(max_length=512)]
    connections: Annotated[list[ConnectionAnnotation], Field(max_length=10_000)]


class ReviewSnapshot(Fixed):
    profile: Literal['cospace.ifc-review-snapshot/0.1']
    source: SourcePin
    design_package_sha256: Digest
    structure_sha256: Digest
    frame_id: Annotated[str, Field(pattern=r'^ifc_world_[a-f0-9]{16}$')]
    annotations: AnnotationLayer
    mapping: Mapping | None
    type_proposals_sha256: Digest | None
    data_kind: Literal['ifc_design_candidate']
    assessment: Literal['unverified']
    alignment_verified: Literal[False]
    ontology_bound: Literal[False]
    real_release_ready: Literal[False]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _annotation_context(structure):
    # Only explicit source classes become tasks; no inferred connections or levels.
    entities = structure['entities']
    return {'frame_id': structure['frame_id'],
            'declared_levels': [{'global_id': e['entity_id']} for e in entities if e['ifc_type'] == 'IfcBuildingStorey'],
            'tasks': [{'source_entity_id': e['entity_id'], 'source': {'ifc_type': e['ifc_type']}}
                      for e in entities if e['ifc_type'] in ('IfcDoor', 'IfcStair')]}


def _check_annotations(snapshot, structure):
    context = _annotation_context(structure)
    layer = snapshot.annotations
    # Explicit internal projection: original worksheet/review pins remain separate.
    document = {'profile': 'cospace.ifc-spatial-annotation/0.1', 'source_review_sha256': content_digest(context),
                'frame_id': snapshot.frame_id, 'unit': 'm', 'assessment': 'unverified',
                **{key: getattr(layer, key) for key in ('evidence', 'areas', 'connections')}}
    document = Worksheet.model_validate(document).model_dump()
    return validate_annotations(document, context)


def _types(snapshot, package, ontology_raw):
    if snapshot.mapping is None:
        if snapshot.type_proposals_sha256 is not None or ontology_raw is not None:
            raise ValueError('review_mapping_context_unexpected')
        return None
    result = propose_structure_types(
        package['members']['structure.json'], expected_structure_sha256=snapshot.structure_sha256,
        expected_source=snapshot.source.model_dump(), ontology_raw=ontology_raw,
        mapping_document=snapshot.mapping.model_dump())
    if content_digest(result) != snapshot.type_proposals_sha256:
        raise ValueError('review_type_proposals_changed')
    return result


def inspect_review_snapshot(raw, *, expected_sha256, design_package, expected_source, ontology_raw=None):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('review_snapshot_byte_budget')
    if _sha(raw) != expected_sha256:
        raise ValueError('review_snapshot_digest')
    try:
        snapshot = ReviewSnapshot.model_validate(json.loads(raw, object_pairs_hook=_unique))
    except (RecursionError, UnicodeError) as exc:
        raise ValueError('review_snapshot_json_invalid') from exc
    if canonical(snapshot.model_dump()) != raw:
        raise ValueError('review_snapshot_canonical_required')
    if snapshot.source != SourcePin.model_validate(expected_source):
        raise ValueError('review_snapshot_source_binding')
    package = read_design_package(design_package, expected_sha256=snapshot.design_package_sha256,
                                  expected_source=expected_source)
    if (snapshot.structure_sha256 != package['manifest']['structure_sha256']
            or snapshot.frame_id != package['structure']['frame_id']):
        raise ValueError('review_snapshot_structure_binding')
    annotations = _check_annotations(snapshot, package['structure'])
    types = _types(snapshot, package, ontology_raw)
    return {'snapshot': snapshot.model_dump(), 'structure': package['structure'], 'annotation_check': annotations,
            'annotation_check_context': 'snapshot_source_projection', 'type_proposals': types,
            'summary': {'profile': snapshot.profile, 'snapshot_sha256': expected_sha256,
                        'source': snapshot.source.model_dump(), 'source_entities': len(package['structure']['entities']),
                        'areas': len(snapshot.annotations.areas),
                        'complete_annotation_ids': annotations['complete_annotation_ids'],
                        'pending_annotation_ids': annotations['pending_annotation_ids'],
                        'proposed_types': types['proposed_count'] if types else 0,
                        'evidence_content_verified': False, 'alignment_verified': False,
                        'ontology_bound': False, 'confirmed_connections': [], 'real_release_ready': False}}


def build_review_snapshot(workspace, space, pin, *, worksheet=None, mapping=None, ontology_raw=None):
    """Caller authorizes scene access; return bytes plus existing fixed design package.

    This is a review-input snapshot, not a released map or approval record.
    """
    design = export_design_package(workspace, space, pin)
    binding, catalog = workspace.catalog(space, pin)
    if binding is None:
        raise ValueError('ifc_not_configured')
    review = structure_review(Path(binding.root), expected_catalog_sha256=pin)
    document = seed(review) if worksheet is None else worksheet
    validate_annotations(document, review)
    normalized = Worksheet.model_validate(document).model_dump()
    source = {'space_id': space, 'catalog_sha256': pin, 'ifc_sha256': catalog['source']['sha256'],
              'ifc_bytes': catalog['source']['bytes']}
    package = read_design_package(design, expected_sha256=_sha(design), expected_source=source)
    types = (propose_structure_types(package['members']['structure.json'],
              expected_structure_sha256=package['manifest']['structure_sha256'], expected_source=source,
              ontology_raw=ontology_raw, mapping_document=mapping) if mapping is not None else None)
    value = {'profile': 'cospace.ifc-review-snapshot/0.1', 'source': source,
             'design_package_sha256': _sha(design), 'structure_sha256': package['manifest']['structure_sha256'],
             'frame_id': package['structure']['frame_id'],
             'annotations': {'original_worksheet_sha256': content_digest(document),
                             'original_review_sha256': content_digest(review),
                             **{key: normalized[key] for key in ('evidence', 'areas', 'connections')}},
             'mapping': mapping, 'type_proposals_sha256': content_digest(types) if types else None,
             'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
             'alignment_verified': False, 'ontology_bound': False, 'real_release_ready': False}
    raw = canonical(ReviewSnapshot.model_validate(value).model_dump())
    inspect_review_snapshot(raw, expected_sha256=_sha(raw), design_package=design,
                            expected_source=source, ontology_raw=ontology_raw)
    # Recheck source/config after composing, before publishing any result to caller.
    if export_design_package(workspace, space, pin) != design:
        raise ValueError('review_snapshot_source_changed')
    return {'snapshot': raw, 'design_package': design}
