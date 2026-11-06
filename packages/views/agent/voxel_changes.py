"""F06b2 synthetic chunk candidates, deliberately not installable F05 packages."""
import copy
import json
import math
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from packages.service.sample import read_json
from packages.spatial.changes import canonical, digest
from packages.views.agent.voxel import VoxelSession

SCHEMA=Path(__file__).resolve().parents[3]/'contracts/schemas/voxel-change-v0.1.schema.json'


def build_voxel_candidate(base_files, expected_source, change, resources):
    base_files=dict(base_files)
    expected_source=copy.deepcopy(expected_source)
    change=copy.deepcopy(change)
    resources=dict(resources)
    schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
    if list(Draft202012Validator(schema).iter_errors(change)):
        raise ValueError('voxel_change_structure')
    base_session=VoxelSession(base_files,expected_source)
    manifest=read_json(base_files['agent-voxel.json'])
    if (change['base_package_id']!=manifest['package_id']
            or change['base_package_sha256']!=base_session.manifest_sha256):
        raise ValueError('base_package_conflict')
    if change['candidate_package_id']==manifest['package_id']:
        raise ValueError('candidate_identity_reuse')
    if len(resources)>272 or any(type(raw) is not bytes or len(raw)>8388608 for raw in resources.values()):
        raise ValueError('resource_budget')
    if sum(map(len,resources.values()))>33554432:
        raise ValueError('resource_budget')
    paths=set()
    for path in resources:
        if (not isinstance(path,str) or not path or '\\' in path or re.search(r'[:\x00-\x1f]',path)
                or any(p in ('','.','..') or p.endswith((' ','.')) for p in path.split('/'))):
            raise ValueError('unsafe_resource_path')
        if path.casefold() in paths:
            raise ValueError('resource_path_collision')
        paths.add(path.casefold())
    used=set()
    def member(ref):
        path=ref['path']
        if path not in resources:
            raise ValueError('resource_missing')
        if path in used:
            raise ValueError('duplicate_resource_reference')
        raw=resources[path]
        if type(ref['bytes']) is not int or len(raw)!=ref['bytes'] or digest(raw)!=ref['sha256']:
            raise ValueError('resource_integrity_mismatch')
        used.add(path)
        return raw

    evidence={ref['path']:member(ref) for ref in change['evidence']}
    original={tuple(c['index']):c for c in manifest['chunks']}
    payloads={index:base_files[c['member']['path']] for index,c in original.items()}
    touched=set()
    impacts=[]
    for operation in change['operations']:
        index=tuple(operation['index'])
        if any(type(i) is not int for i in index):
            raise ValueError('literal_index_required')
        if index in touched:
            raise ValueError('duplicate_chunk_operation')
        touched.add(index)
        if any(i>=d//n for i,d,n in zip(index,manifest['dimensions'],manifest['chunk_shape'])):
            raise ValueError('chunk_out_of_scope')
        previous=original.get(index)
        if operation['op']=='chunk.add':
            if previous is not None:
                raise ValueError('chunk_expected_absent_conflict')
        elif previous is None or previous['member']['sha256']!=operation['expected_sha256']:
            raise ValueError('chunk_old_digest_conflict')
        if operation['op']=='chunk.remove':
            del payloads[index]
            after=None
        else:
            raw=member(operation['replacement'])
            if len(raw)!=math.prod(manifest['chunk_shape']) or any(v>4 for v in raw):
                raise ValueError('invalid_occupancy_payload')
            if previous is not None and previous['member']['sha256']==digest(raw):
                raise ValueError('no_op_chunk_replace')
            payloads[index]=raw
            after=digest(raw)
        low=[o+i*n*manifest['resolution_m'] for o,i,n in zip(manifest['origin_m'],index,manifest['chunk_shape'])]
        high=[a+n*manifest['resolution_m'] for a,n in zip(low,manifest['chunk_shape'])]
        impacts.append({'index':list(index),'op':operation['op'],'bounds':[low,high],
            'before_sha256':previous['member']['sha256'] if previous else None,'after_sha256':after,
            'after_missing':operation['op']=='chunk.remove'})
    if used!=set(resources):
        raise ValueError('unreferenced_resources')

    # Paths derive from logical indices; untouched bytes retain their original values.
    files={}
    chunks=[]
    for index,raw in sorted(payloads.items()):
        path='chunks/'+'-'.join(map(str,index))+'.u8'
        files[path]=raw
        chunks.append({'index':list(index),'member':{'path':path,'bytes':len(raw),'sha256':digest(raw)}})
    target=copy.deepcopy(manifest)
    target.update(package_id=change['candidate_package_id'],chunks=chunks)
    # Validate candidate payload by F05 rules in a temporary inspection-only projection.
    # This projection is never returned or persisted as an installable package.
    temporary={**files,'agent-voxel.json':canonical(target)}
    VoxelSession(temporary,expected_source)
    target.update(schema_version='cospace.agent-voxel-candidate/0.1',stage='candidate_only')
    files['agent-voxel-candidate.json']=canonical(target)
    result={
        'candidate_id':change['candidate_package_id'],
        'base_package_sha256':base_session.manifest_sha256,
        'candidate_manifest_sha256':digest(files['agent-voxel-candidate.json']),
        'change_sha256':digest(canonical(change)),
        'base_source':copy.deepcopy(manifest['source']),
        'impacts':impacts,'unchanged_chunks':len(set(original)-touched),
        'changed_chunk_count':len(touched),
        'required_rechecks':['source_geometry_consistency','coverage_quality','machine_view_derivation','human_view_impact'],
        'publication_status':'candidate_only','authorized':False,'robot_ready':False,
        'source_geometry_consistency_verified':False,
        'files':files,'evidence':evidence}
    return result


class VoxelCandidatePreview:
    """Rebuild from original pinned inputs before previewing candidate state changes."""
    def __init__(self, base_files, expected_source, change, resources, candidate):
        expected=build_voxel_candidate(base_files,expected_source,change,resources)
        if candidate!=expected:
            raise ValueError('candidate_rebuild_mismatch')
        files=dict(expected['files'])
        manifest=read_json(files.pop('agent-voxel-candidate.json'))
        manifest['schema_version']='cospace.agent-voxel/0.1'
        del manifest['stage']
        files['agent-voxel.json']=canonical(manifest)
        self._session=VoxelSession(files,expected_source)
        self._digest=expected['candidate_manifest_sha256']
        self._id=expected['candidate_id']

    def query(self, point):
        result=self._session.query(point)
        # Do not return the temporary projection's package digest or imply a new release.
        return {'candidate_id':self._id,'candidate_manifest_sha256':self._digest,
                'state':result['state'],'reason':result['reason'],
                'base_source':result['source'],'publication_status':'candidate_only',
                'authorized':False,'robot_ready':False,'source_geometry_consistency_verified':False}
