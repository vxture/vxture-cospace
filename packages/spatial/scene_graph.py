"""D0 synthetic spatial facts, not navigation or verified real-scene geometry."""
from copy import deepcopy
from datetime import datetime
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROFILE = 'cospace.synthetic-scene-graph/0.1'
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
Identity = Annotated[str, Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$')]
Coordinate = Annotated[float, Field(ge=-1_000_000, le=1_000_000)]
Vector = Annotated[list[Coordinate], Field(min_length=3, max_length=3)]
References = Annotated[list[Identity], Field(min_length=1, max_length=32)]
Kind = Literal['building', 'level', 'space', 'element', 'asset']


class Fixed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Frame(Fixed):
    id: Identity
    unit: Literal['m']
    axes: Literal['right_forward_up']


class TypeDefinition(Fixed):
    id: Identity
    kind: Kind
    role: Literal['building', 'level', 'room', 'corridor', 'door', 'stair', 'cabinet']


class Ontology(Fixed):
    id: Identity
    version: Literal['0.1.0']
    types: Annotated[list[TypeDefinition], Field(min_length=1, max_length=64)]


class Evidence(Fixed):
    id: Identity
    kind: Literal['synthetic_fixture']
    description: Annotated[str, Field(min_length=1, max_length=512)]


class Entity(Fixed):
    id: Identity
    kind: Kind
    type_id: Identity
    name: Annotated[str, Field(min_length=1, max_length=160)]
    revision: Annotated[int, Field(ge=1, le=1_000_000)]
    geometry_ids: References
    evidence_ids: References
    assessment: Literal['unverified']


class Bounds(Fixed):
    shape: Literal['aabb']
    bounds: Annotated[list[Vector], Field(min_length=2, max_length=2)]

    @model_validator(mode='after')
    def positive_extent(self):
        if any(a >= b for a, b in zip(*self.bounds)):
            raise ValueError('invalid_bounds')
        return self


class Point(Fixed):
    shape: Literal['point']
    position: Vector


def subtract(a, b):
    return [x-y for x, y in zip(a, b)]


class Rectangle(Fixed):
    shape: Literal['rectangle']
    vertices: Annotated[list[Vector], Field(min_length=4, max_length=4)]

    @model_validator(mode='after')
    def rectangle(self):
        a, b, c, d = self.vertices
        u, v = subtract(b, a), subtract(d, a)
        uu, vv = sum(x*x for x in u), sum(x*x for x in v)
        if (min(uu, vv) <= 1e-12
                or abs(sum(x*y for x, y in zip(u, v))) > 1e-8 * math.sqrt(uu*vv)
                or any(abs(c[i] - (a[i]+u[i]+v[i])) > 1e-8 for i in range(3))):
            raise ValueError('invalid_rectangle')
        return self


class Geometry(Fixed):
    id: Identity
    entity_id: Identity
    frame_id: Identity
    role: Literal['approximate_bounds', 'reference_point', 'connection_port']
    value: Annotated[Bounds | Point | Rectangle, Field(discriminator='shape')]
    evidence_ids: References

    @model_validator(mode='after')
    def role_shape(self):
        expected = {'approximate_bounds': 'aabb', 'reference_point': 'point',
                    'connection_port': 'rectangle'}
        if self.value.shape != expected[self.role]:
            raise ValueError('geometry_role_shape')
        return self


class Relation(Fixed):
    id: Identity
    type: Literal['contains', 'part_of', 'adjacent_to', 'bounds_space', 'installed_on']
    source_id: Identity
    target_id: Identity
    evidence_ids: References
    assessment: Literal['unverified']


class Port(Fixed):
    space_id: Identity
    geometry_id: Identity


class Connection(Fixed):
    id: Identity
    connector_id: Identity
    mode: Literal['opening', 'stair_transition']
    ports: Annotated[list[Port], Field(min_length=2, max_length=2)]
    evidence_ids: References
    assessment: Literal['unverified']


class Observation(Fixed):
    id: Identity
    entity_id: Identity
    property: Literal['opening_state']
    value: Literal['open', 'closed', 'partially_open', 'unknown']
    observed_at: Annotated[str, Field(min_length=20, max_length=40)]
    received_at: Annotated[str, Field(min_length=20, max_length=40)]
    valid_until: Annotated[str, Field(min_length=20, max_length=40)]
    source_id: Identity
    evidence_ids: References


class Source(Fixed):
    id: Identity
    kind: Literal['synthetic_fixture']


class SceneGraph(Fixed):
    profile: Literal['cospace.synthetic-scene-graph/0.1']
    data_kind: Literal['synthetic']
    scene_id: Identity
    snapshot_id: Identity
    frame: Frame
    ontology: Ontology
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=128)]
    sources: Annotated[list[Source], Field(min_length=1, max_length=64)]
    entities: Annotated[list[Entity], Field(min_length=1, max_length=1000)]
    geometry: Annotated[list[Geometry], Field(min_length=1, max_length=4000)]
    relations: Annotated[list[Relation], Field(max_length=4000)]
    connections: Annotated[list[Connection], Field(max_length=1000)]
    observations: Annotated[list[Observation], Field(max_length=2000)]


def unique(items, name):
    result = {item.id: item for item in items}
    if len(result) != len(items):
        raise ValueError('duplicate_' + name)
    return result


def utc(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value):
        raise ValueError('utc_required')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError('invalid_timestamp') from exc
    return parsed


def _type_roles(types):
    expected_kind = {'building': 'building', 'level': 'level', 'room': 'space',
                     'corridor': 'space', 'door': 'element', 'stair': 'element', 'cabinet': 'asset'}
    if any(t.kind != expected_kind[t.role] for t in types.values()):
        raise ValueError('ontology_role_kind')


def _evidence_references(graph, evidence):
    for item in [*graph.entities, *graph.geometry, *graph.relations,
                 *graph.connections, *graph.observations]:
        if len(set(item.evidence_ids)) != len(item.evidence_ids) or set(item.evidence_ids) - evidence.keys():
            raise ValueError('invalid_evidence_reference')


def _geometry_references(graph, types, entities, geometry):
    for entity in entities.values():
        if entity.type_id not in types or types[entity.type_id].kind != entity.kind:
            raise ValueError('entity_type_kind')
        if len(set(entity.geometry_ids)) != len(entity.geometry_ids):
            raise ValueError('duplicate_geometry_reference')
        if any(g not in geometry or geometry[g].entity_id != entity.id for g in entity.geometry_ids):
            raise ValueError('entity_geometry_binding')
    for item in geometry.values():
        if item.frame_id != graph.frame.id:
            raise ValueError('geometry_frame_mismatch')
        if item.entity_id not in entities or item.id not in entities[item.entity_id].geometry_ids:
            raise ValueError('geometry_entity_binding')


def _references(graph):
    types = unique(graph.ontology.types, 'type')
    entities = unique(graph.entities, 'entity')
    geometry = unique(graph.geometry, 'geometry')
    evidence = unique(graph.evidence, 'evidence')
    for name in ('relations', 'connections', 'observations', 'sources'):
        unique(getattr(graph, name), name[:-1])
    _type_roles(types)
    _evidence_references(graph, evidence)
    _geometry_references(graph, types, entities, geometry)
    return types, entities, geometry


def _relation_endpoints(relation, entities):
    a, b = relation.source_id, relation.target_id
    if a not in entities or b not in entities or a == b:
        raise ValueError('relation_endpoint')
    allowed = {
        'contains': {('building', 'level'), ('building', 'element'), ('level', 'space'),
                     ('level', 'element'), ('level', 'asset'), ('space', 'element'), ('space', 'asset')},
        'part_of': {('element', 'element'), ('element', 'building')},
        'adjacent_to': {('space', 'space')},
        'bounds_space': {('element', 'space')},
        'installed_on': {('asset', 'element')},
    }
    if (entities[a].kind, entities[b].kind) not in allowed[relation.type]:
        raise ValueError('relation_endpoint_kind')
    return a, b


def _remember(assertions, key, error):
    if key in assertions:
        raise ValueError(error)
    assertions.add(key)


def _record_parent(parents, relation, a, b):
    if relation.type not in parents:
        return
    parent, child = (a, b) if relation.type == 'contains' else (b, a)
    family = parents[relation.type]
    if child in family and family[child] != parent:
        raise ValueError('multiple_parents')
    family[child] = parent


def _acyclic(parents):
    for family in parents.values():
        for child in family:
            visited = set()
            while child in family:
                if child in visited:
                    raise ValueError('relation_cycle')
                visited.add(child)
                child = family[child]


def _relations(graph, entities):
    parents = {'contains': {}, 'part_of': {}}
    assertions = set()
    for relation in graph.relations:
        a, b = _relation_endpoints(relation, entities)
        key = (relation.type, *sorted((a, b))) if relation.type == 'adjacent_to' else (relation.type, a, b)
        _remember(assertions, key, 'duplicate_relation_assertion')
        _record_parent(parents, relation, a, b)
    _acyclic(parents)


def _connection_spaces(connection, types, entities):
    connector = entities.get(connection.connector_id)
    expected = 'door' if connection.mode == 'opening' else 'stair'
    if connector is None or types[connector.type_id].role != expected:
        raise ValueError('connection_connector_role')
    spaces = [port.space_id for port in connection.ports]
    if len(set(spaces)) != 2 or any(s not in entities or entities[s].kind != 'space' for s in spaces):
        raise ValueError('connection_spaces')
    return spaces


def _connection_ports(connection, geometry):
    if len({port.geometry_id for port in connection.ports}) != 2:
        raise ValueError('duplicate_connection_port')
    for port in connection.ports:
        value = geometry.get(port.geometry_id)
        if value is None or value.entity_id != connection.connector_id or value.role != 'connection_port':
            raise ValueError('connection_port_binding')


def _connections(graph, types, entities, geometry):
    assertions = set()
    for connection in graph.connections:
        spaces = _connection_spaces(connection, types, entities)
        key = (connection.connector_id, *sorted(spaces))
        _remember(assertions, key, 'duplicate_connection_assertion')
        _connection_ports(connection, geometry)


def _observations(graph, types, entities):
    sources = {source.id for source in graph.sources}
    for observation in graph.observations:
        entity = entities.get(observation.entity_id)
        if entity is None or types[entity.type_id].role != 'door':
            raise ValueError('observation_subject_role')
        if utc(observation.valid_until) <= utc(observation.observed_at):
            raise ValueError('invalid_observation_interval')
        if observation.source_id not in sources:
            raise ValueError('observation_source')
        if utc(observation.received_at) < utc(observation.observed_at):
            raise ValueError('observation_received_before_observed')


def validate_scene_graph(document):
    """Validate bounded synthetic metadata and references; verify no field truth."""
    try:
        graph = SceneGraph.model_validate(document)
    except ValidationError as exc:
        raise ValueError('scene_graph_structure:' + str(exc)) from exc
    types, entities, geometry = _references(graph)
    _relations(graph, entities)
    _connections(graph, types, entities, geometry)
    _observations(graph, types, entities)
    return {'profile': PROFILE, 'scene_id': graph.scene_id, 'snapshot_id': graph.snapshot_id,
            'metadata_valid': True, 'data_kind': 'synthetic',
            'counts': {name: len(getattr(graph, name)) for name in
                       ('entities', 'geometry', 'relations', 'connections', 'observations')},
            'evidence_verified': False, 'geometry_verified': False,
            'real_release_ready': False, 'robot_ready': False,
            'limitations': ['synthetic_only', 'approximate_geometry', 'unverified_spatial_assertions',
                            'no_state_resolution', 'no_navigation_or_traversability']}


class SceneGraphReader:
    """Fixed in-memory snapshot. Returned data cannot mutate the pinned graph."""
    def __init__(self, document):
        self._document = deepcopy(document)
        self.report = validate_scene_graph(self._document)

    def entity(self, identity):
        entities = self._document['entities']
        entity = next((item for item in entities if item['id'] == identity), None)
        if entity is None:
            raise ValueError('entity_not_found')
        geometry = [g for g in self._document['geometry'] if g['id'] in entity['geometry_ids']]
        return deepcopy({'entity': entity, 'geometry': geometry,
                         'snapshot_id': self._document['snapshot_id'], 'data_kind': 'synthetic'})

    def connections(self, space_id):
        if self.entity(space_id)['entity']['kind'] != 'space':
            raise ValueError('space_required')
        return deepcopy([c for c in self._document['connections']
                         if any(p['space_id'] == space_id for p in c['ports'])])
