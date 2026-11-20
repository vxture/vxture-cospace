"""Rebuild explicitly synthetic B02 fixtures; never reads customer or runtime data.

Default checks checked-in examples. --write explicitly re-pins the current draft
definitions; it is fixture authoring, never an instance migration mechanism.
"""
import argparse
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from packages.ontology.kernel import builtin_catalog, canonical_bytes  # noqa: E402

STAMP = '2026-11-20T00:00:00Z'
PERIOD = {'start': '2026-01-01T00:00:00Z', 'end': '2027-01-01T00:00:00Z'}
VARIANTS = {
    'research-office': ('研发办公园（合成）', '研发实验', 'built_environment:room'),
    'manufacturing': ('制造工业园（合成）', '生产配套', 'built_environment:room'),
    'logistics': ('仓储物流园（合成）', '仓储装卸', 'operations:loading_region'),
}


def sample(kind):
    title, use, space_type = VARIANTS[kind]
    catalog = builtin_catalog().describe()
    wanted = {'core', 'built_environment', 'operations', 'electrical', 'monitoring'}
    refs = [e['reference'] for e in catalog['modules'] if e['reference']['module_id'] in wanted]
    evidence = ['basis']

    def value(v, **extra):
        return {'value': v, 'source_id': 'register', 'evidence_ids': evidence, **extra}

    def entity(identity, concept, name, **properties):
        result = {'id': identity, 'type': concept, 'properties': {'name': value(name), **properties},
                  'source_bindings': [{'source_id': 'register', 'external_id': identity}],
                  'evidence_ids': evidence}
        if concept in {'operations:space_use', 'operations:occupancy_assignment', 'operations:responsibility_assignment'}:
            result['valid_time'] = PERIOD
        return result

    entities = [
        entity('site', 'built_environment:site_region', title),
        entity('building', 'built_environment:building', '一号楼'),
        entity('building-space', 'built_environment:building_region', '一号楼空间范围'),
        entity('level', 'built_environment:level', '一层'),
        entity('work-space', space_type, '作业空间'),
        entity('management', 'operations:management_region', '公共设施管理范围'),
        entity('operator', 'core:organization', '运营单位（合成）'),
        entity('occupant', 'core:organization', '使用单位（合成）'),
        entity('occupancy', 'operations:occupancy_assignment', '空间使用安排'),
        entity('use', 'operations:space_use', '空间用途安排', use_label=value(use)),
        entity('responsibility', 'operations:responsibility_assignment', '设施维护职责', responsibility_kind=value('维护')),
        entity('cabinet', 'electrical:distribution_cabinet', '配电柜', rated_voltage=value(380, unit='V', quantity='electric_potential')),
        entity('electrical-system', 'electrical:electrical_system', '公共供配电系统'),
        entity('asset', 'operations:asset_record', '配电柜台账', record_key=value('asset-001')),
        entity('sensor', 'monitoring:sensor', '环境传感器'),
    ]
    entities[13]['source_bindings'][0]['external_id'] = 'asset-001'
    triples = [
        ('built_environment:region_of_building', 'building-space', 'building'),
        ('built_environment:spatial_part_of', 'building-space', 'site'),
        ('built_environment:spatial_part_of', 'level', 'building-space'),
        ('built_environment:spatial_part_of', 'work-space', 'level'),
        ('core:located_in', 'building', 'site'),
        ('operations:occupancy_organization', 'occupancy', 'occupant'),
        ('operations:occupancy_space', 'occupancy', 'work-space'),
        ('operations:use_space', 'use', 'work-space'),
        ('operations:responsible_organization', 'responsibility', 'operator'),
        ('operations:responsibility_target', 'responsibility', 'electrical-system'),
        ('operations:management_scope', 'responsibility', 'management'),
        ('operations:asset_object', 'asset', 'cabinet'),
        ('operations:asset_custodian', 'asset', 'operator'),
        ('core:located_in', 'cabinet', 'work-space'),
        ('core:member_of', 'cabinet', 'electrical-system'),
        ('core:located_in', 'sensor', 'work-space'),
        ('monitoring:monitors', 'sensor', 'work-space'),
    ]
    assertions = [{'id': f'a{i:02}', 'relation': r, 'subject_id': s, 'object_id': o,
                   'source_id': 'register', 'evidence_ids': evidence, 'valid_time': PERIOD,
                   'epistemic_status': 'reported'} for i, (r, s, o) in enumerate(triples, 1)]
    geometry = [
        {'id': 'site-extent', 'frame_id': 'local', 'shape': {'kind': 'box3', 'min': [0, 0, 0], 'max': [200, 160, 30]}},
        {'id': 'building-extent', 'frame_id': 'local', 'shape': {'kind': 'box3', 'min': [10, 10, 0], 'max': [80, 60, 20]}},
        {'id': 'work-extent', 'frame_id': 'local', 'shape': {'kind': 'box3', 'min': [12, 12, 0], 'max': [40, 35, 4]}},
        {'id': 'cabinet-position', 'frame_id': 'local', 'shape': {'kind': 'point3', 'coordinates': [13, 14, 0]}},
    ]
    bindings = [{'entity_id': e, 'geometry_id': g, 'purpose': purpose, 'source_id': 'register', 'evidence_ids': evidence}
                for e, g, purpose in [('site', 'site-extent', 'extent'), ('building-space', 'building-extent', 'extent'),
                                      ('work-space', 'work-extent', 'extent'), ('cabinet', 'cabinet-position', 'placement')]]
    return {'profile': 'vxture.ontology-instances/0.1', 'package_id': f'{kind}-b02',
            'namespace': f'urn:vxture:synthetic:park:{kind}', 'synthetic': True, 'title': title,
            'generated_at': STAMP, 'definition_refs': refs,
            'sources': [{'id': 'register', 'system': 'synthetic-park-register', 'scope': kind,
                         'revision': 'fixture-b02-1', 'synthetic': True}],
            'evidence': [{'id': 'basis', 'source_id': 'register', 'record_key': 'fixture-design-001',
                          'recorded_at': STAMP, 'description': '手工编制的合成园区示例依据，无客户采集或现场核验。'}],
            'entities': entities, 'assertions': assertions,
            'frames': [{'id': 'local', 'kind': 'local_cartesian', 'unit': 'm',
                        'axes': ['x', 'y', 'z'], 'description': '合成右手局部坐标；原点为样例西南角地面，Z 向上，无地理配准。'}],
            'geometries': geometry, 'geometry_bindings': bindings,
            'coverage': [{'id': 'facility-survey', 'scope_entity_ids': ['site'],
                          'concepts': ['core:physical_object'], 'relations': ['core:member_of'],
                          'status': 'partial', 'valid_time': PERIOD, 'source_id': 'register', 'evidence_ids': evidence}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    for kind in VARIANTS:
        path = ROOT / 'examples' / 'ontology' / 'parks' / f'{kind}.json'
        expected = sample(kind)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        elif canonical_bytes(json.loads(path.read_text(encoding='utf-8'))) != canonical_bytes(expected):
            raise SystemExit(f'Fixture changed: {path.name}; review before explicit --write')
    print('3 synthetic park fixtures ' + ('written' if args.write else 'match'))


if __name__ == '__main__':
    main()
