"""Small synthetic two-level fixture; all dimensions and identities are invented."""


def sample():
    evidence = ['fixture']
    types = [('building', 'building'), ('level', 'level'), ('room', 'space'),
             ('corridor', 'space'), ('door', 'element'), ('stair', 'element'), ('cabinet', 'asset')]
    graph = {
        'profile': 'cospace.synthetic-scene-graph/0.1', 'data_kind': 'synthetic',
        'scene_id': 'synthetic-building', 'snapshot_id': 'synthetic-snapshot-01',
        'frame': {'id': 'synthetic-local', 'unit': 'm', 'axes': 'right_forward_up'},
        'ontology': {'id': 'synthetic-building-types', 'version': '0.1.0',
                     'types': [{'id': role, 'kind': kind, 'role': role} for role, kind in types]},
        'evidence': [{'id': 'fixture', 'kind': 'synthetic_fixture',
                      'description': 'Invented D0 example; not surveyed, not a real building.'}],
        'sources': [{'id': 'synthetic-source', 'kind': 'synthetic_fixture'}],
        'entities': [], 'geometry': [], 'relations': [], 'connections': [], 'observations': [],
    }
    kinds = dict(types)

    def entity(identity, role, name, bounds):
        graph['entities'].append({'id': identity, 'kind': kinds[role], 'type_id': role,
                                  'name': name, 'revision': 1, 'geometry_ids': [identity+'-bounds'],
                                  'evidence_ids': evidence[:], 'assessment': 'unverified'})
        graph['geometry'].append({'id': identity+'-bounds', 'entity_id': identity,
                                  'frame_id': graph['frame']['id'], 'role': 'approximate_bounds',
                                  'value': {'shape': 'aabb', 'bounds': bounds}, 'evidence_ids': evidence[:]})

    def relation(kind, source, target):
        graph['relations'].append({'id': f'relation-{len(graph["relations"])+1}', 'type': kind,
                                   'source_id': source, 'target_id': target,
                                   'evidence_ids': evidence[:], 'assessment': 'unverified'})

    def port(connector, suffix, vertices):
        identity = connector+'-port-'+suffix
        next(e for e in graph['entities'] if e['id'] == connector)['geometry_ids'].append(identity)
        graph['geometry'].append({'id': identity, 'entity_id': connector,
                                  'frame_id': graph['frame']['id'], 'role': 'connection_port',
                                  'value': {'shape': 'rectangle', 'vertices': vertices},
                                  'evidence_ids': evidence[:]})
        return identity

    entity('building', 'building', '合成建筑', [[0, 0, 0], [12, 10, 6]])
    for level, z in [('l1', 0), ('l2', 3)]:
        entity(level, 'level', '一层' if z == 0 else '二层', [[0, 0, z], [12, 10, z+3]])
        entity('corridor-'+level, 'corridor', '楼道', [[0, 0, z], [12, 2, z+3]])
        entity('room-'+level, 'room', '设备间', [[0, 2, z], [8, 8, z+3]])
        entity('door-'+level, 'door', '设备间门', [[3, 1.9, z], [4, 2.1, z+2.2]])
        relation('contains', 'building', level)
        relation('contains', level, 'corridor-'+level)
        relation('contains', level, 'room-'+level)
        relation('contains', level, 'door-'+level)
        relation('adjacent_to', 'corridor-'+level, 'room-'+level)
        ports = [port('door-'+level, suffix, [[3, y, z], [4, y, z], [4, y, z+2.2], [3, y, z+2.2]])
                 for suffix, y in [('a', 1.9), ('b', 2.1)]]
        graph['connections'].append({'id': 'connection-door-'+level, 'connector_id': 'door-'+level,
                                     'mode': 'opening', 'ports': [
                                         {'space_id': 'corridor-'+level, 'geometry_id': ports[0]},
                                         {'space_id': 'room-'+level, 'geometry_id': ports[1]}],
                                     'evidence_ids': evidence[:], 'assessment': 'unverified'})
    entity('stair', 'stair', '跨层楼梯', [[10, 0, 0], [12, 2, 6]])
    relation('contains', 'building', 'stair')
    endpoints = []
    for level, z in [('l1', 0), ('l2', 3)]:
        identity = port('stair', level, [[10, 0, z], [12, 0, z], [12, 2, z], [10, 2, z]])
        endpoints.append({'space_id': 'corridor-'+level, 'geometry_id': identity})
    graph['connections'].append({'id': 'connection-stair', 'connector_id': 'stair',
                                 'mode': 'stair_transition', 'ports': endpoints,
                                 'evidence_ids': evidence[:], 'assessment': 'unverified'})
    entity('cabinet', 'cabinet', '配电柜', [[1, 6, 0], [2, 7, 2]])
    relation('contains', 'room-l1', 'cabinet')
    graph['observations'].append({'id': 'door-state-01', 'entity_id': 'door-l1',
                                  'property': 'opening_state', 'value': 'closed',
                                  'observed_at': '2026-11-16T00:00:00Z',
                                  'received_at': '2026-11-16T00:00:02Z',
                                  'valid_until': '2026-11-16T00:05:00Z',
                                  'source_id': 'synthetic-source', 'evidence_ids': evidence[:]})
    return graph
