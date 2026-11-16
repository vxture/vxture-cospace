"""Extract IFC design declarations alongside the existing offline geometry catalog."""
from collections import Counter
from functools import partial

from packages.data.ifc_inspection import MAX_PRODUCTS, inspect_ifc, native_reader

PROFILE = 'cospace.ifc-structure-candidate/0.1'
KINDS = {
    'IfcBuilding': 'building', 'IfcBuildingStorey': 'level', 'IfcSpace': 'space',
    'IfcDoor': 'door', 'IfcStair': 'stair', 'IfcStairFlight': 'stair_flight',
    'IfcOpeningElement': 'opening', 'IfcWall': 'wall', 'IfcSlab': 'slab',
    'IfcElectricDistributionBoard': 'distribution_board',
}
RULES = (
    ('IfcRelAggregates', 'aggregates', 'RelatingObject', 'RelatedObjects', True),
    ('IfcRelContainedInSpatialStructure', 'contained_in', 'RelatingStructure', 'RelatedElements', True),
    ('IfcRelVoidsElement', 'opening_in', 'RelatingBuildingElement', 'RelatedOpeningElement', False),
    ('IfcRelFillsElement', 'fills', 'RelatingOpeningElement', 'RelatedBuildingElement', False),
    ('IfcRelSpaceBoundary', 'space_boundary', 'RelatingSpace', 'RelatedBuildingElement', False),
)
MAX_RELATIONS = 20_000


def _entities(document):
    selected = {}
    for ifc_type, role in KINDS.items():
        for product in document.by_type(ifc_type):
            identity = product.GlobalId
            if not identity or identity in selected or len(selected) >= MAX_PRODUCTS:
                raise ValueError('invalid_structure_entity_catalog')
            selected[identity] = dict(entity_id=identity, ifc_type=product.is_a(), role=role,
                                      geometry_product_id=identity)
    return selected


def _edge(rel, kind, source, target, selected):
    a = getattr(source, 'GlobalId', None)
    b = getattr(target, 'GlobalId', None)
    if a not in selected or b not in selected:
        return None
    if not rel.GlobalId or a == b:
        raise ValueError('invalid_structure_relation')
    if kind in ('contained_in', 'opening_in', 'fills'):
        a, b = b, a
    return dict(ifc_relation_id=rel.GlobalId, kind=kind, source_id=a, target_id=b)


def _relations(document, selected):
    edges = []
    scanned = 0
    for ifc_type, kind, from_attr, to_attr, multiple in RULES:
        for rel in document.by_type(ifc_type):
            source, targets = getattr(rel, from_attr), getattr(rel, to_attr)
            for target in (targets or ()) if multiple else (targets,):
                scanned += 1
                if scanned > MAX_RELATIONS:
                    raise ValueError('structure_relation_budget')
                edge = _edge(rel, kind, source, target, selected)
                if edge is not None:
                    edges.append(edge)
    keys = {(e['ifc_relation_id'], e['kind'], e['source_id'], e['target_id']) for e in edges}
    if len(keys) != len(edges):
        raise ValueError('duplicate_structure_relation')
    return sorted(edges, key=lambda e: (e['kind'], e['ifc_relation_id'], e['source_id'], e['target_id']))


def structure_metadata(document):
    selected = _entities(document)
    edges = _relations(document, selected)
    counts = Counter(e['role'] for e in selected.values())
    missing = [r for r in ('building', 'level', 'space', 'door', 'stair', 'distribution_board') if not counts[r]]
    return {'structure': {
        'profile': PROFILE, 'data_kind': 'ifc_design_candidate', 'assessment': 'unverified',
        'entities': [selected[k] for k in sorted(selected)], 'relations': edges,
        'role_counts': dict(sorted(counts.items())), 'missing_declared_roles': missing,
        'limitations': ['selected_ifc_classes_only', 'explicit_ifc_relations_only',
                        'geometry_references_may_lack_mesh', 'no_pointcloud_alignment',
                        'no_confirmed_space_connections', 'no_live_state_or_traversability'],
    }}


def inspect_ifc_structure(source, output, *, expected_sha256):
    """Run only in the isolated native parser; results are not a scene publication."""
    reader = partial(native_reader, document_metadata=structure_metadata)
    return inspect_ifc(source, output, expected_sha256=expected_sha256, reader=reader)
