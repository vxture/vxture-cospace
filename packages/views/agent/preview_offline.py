"""Bounded, read-only offline consumption of real preview surface cells."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np
from packages.construction.preview_model import PreviewModel
from packages.lifecycle.preview_scope import match,owned
from packages.spatial.preview_objects import snapshot
from packages.spatial.preview_business import business_snapshot
from packages.spatial.preview_relations import relation_snapshot
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS

PROFILE = 'cospace.preview-offline/0.1'
MAX_BYTES = 32 * 1024 * 1024
MAX_CELLS = 500_000
MEMBERS = {'package.json', 'publication.json', 'model.json', 'agent.npz'}
SEMANTIC_MEMBERS = {'objects.json','ontology.json'}
SEMANTIC_PROFILE = 'cospace.preview-offline/0.2'
BUSINESS_PROFILE = 'cospace.preview-offline/0.3'
RELATION_PROFILE = 'cospace.preview-offline/0.4'
INSTANCE_PROFILE = 'cospace.preview-offline/0.5'
from packages.service.object_semantic_artifact import MANIFEST as INSTANCE_MANIFEST, MEMBERS as INSTANCE_MEMBERS
INSTANCE_FILES = set(INSTANCE_MEMBERS + (INSTANCE_MANIFEST,))


def bundle_profile(model,record=None):
    if record and record.get('semantic_artifact'):return INSTANCE_PROFILE
    return RELATION_PROFILE if model.manifest.get('object_relations') else BUSINESS_PROFILE if model.manifest.get('business_association') else SEMANTIC_PROFILE if model.manifest.get('semantic_annotation') else PROFILE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def export_bundle(record, model):
    """Caller supplies a validated fixed publication. Never modify its snapshot."""
    from packages.service.fixed_semantic_consumption import read_fixed
    read_fixed(record,model)
    files = {name: (model.root/name).read_bytes()
             for name in ('publication.json', 'model.json', 'agent.npz')}
    semantic=bool(model.manifest.get('semantic_annotation'))
    if semantic:
        files.update({name:(model.root/name).read_bytes() for name in SEMANTIC_MEMBERS})
    if model.manifest.get('business_association'):files['business.json']=(model.root/'business.json').read_bytes()
    if model.manifest.get('object_relations'):files['relations.json']=(model.root/'relations.json').read_bytes()
    if record.get('semantic_artifact'):
        files.update({name:(model.root/name).read_bytes() for name in INSTANCE_FILES})
    manifest = {'profile': bundle_profile(model,record), 'publication_id': record['id'],
                'quality': 'unverified', 'robot_ready': False, **owned(record),
                'files': {name: {'sha256': sha(data), 'bytes': len(data)}
                          for name, data in files.items()}}
    files['package.json'] = json.dumps(manifest, sort_keys=True).encode('utf-8')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in sorted(files.items()):
            # Stable bytes for a fixed publication, including ZIP timestamps.
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    data = output.getvalue()
    OfflinePreview(data, record['id'], sha(data))
    return data


def bounded_zip(data, names, limit):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if (len(infos) != len(names) or {i.filename for i in infos} != names
                or sum(i.file_size for i in infos) > limit):
            raise ValueError('invalid_archive_members_or_size')
        return {i.filename: archive.read(i) for i in infos}


class OfflinePreview(PreviewModel):
    """Reuses query semantics, with no source model files or online service."""
    def __init__(self, data, expected_publication, expected_sha256):
        if len(data) > MAX_BYTES or sha(data) != expected_sha256:
            raise ValueError('package_integrity_or_size')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:names=set(archive.namelist())
        has_instance=bool(names & INSTANCE_FILES)
        base_names=names-INSTANCE_FILES
        if (has_instance and not INSTANCE_FILES <= names or base_names not in (MEMBERS,MEMBERS|SEMANTIC_MEMBERS,MEMBERS|SEMANTIC_MEMBERS|{'business.json'},MEMBERS|SEMANTIC_MEMBERS|{'relations.json'},MEMBERS|SEMANTIC_MEMBERS|{'business.json','relations.json'})):raise ValueError('invalid_archive_members_or_size')
        files = bounded_zip(data, names, MAX_BYTES)
        package = json.loads(files['package.json'])
        expected_profile=INSTANCE_PROFILE if has_instance else RELATION_PROFILE if 'relations.json' in names else BUSINESS_PROFILE if 'business.json' in names else SEMANTIC_PROFILE if base_names==MEMBERS|SEMANTIC_MEMBERS else PROFILE
        if (package['profile'] != expected_profile or package['publication_id'] != expected_publication
                or package['quality'] != 'unverified' or package['robot_ready'] is not False
                or set(package['files']) != names - {'package.json'}):
            raise ValueError('package_binding')
        for name, member in package['files'].items():
            if sha(files[name]) != member['sha256'] or len(files[name]) != member['bytes']:
                raise ValueError('member_integrity')
        record = json.loads(files['publication.json'])
        if bool(record.get('semantic_artifact'))!=has_instance:raise ValueError('semantic_publication_binding')
        self.manifest = json.loads(files['model.json'])
        semantic=bool(self.manifest.get('semantic_annotation'))
        if semantic!=('objects.json' in names):raise ValueError('semantic_package_binding')
        if bool(self.manifest.get('business_association'))!=('business.json' in names):raise ValueError('business_package_binding')
        if not self.manifest.get('business_association') and 'business.json' in self.manifest['members']:raise ValueError('business_declaration_missing')
        if bool(self.manifest.get('object_relations'))!=('relations.json' in names):raise ValueError('relation_package_binding')
        if not self.manifest.get('object_relations') and 'relations.json' in self.manifest['members']:raise ValueError('relation_declaration_missing')
        match(self.manifest,owned(record))
        from packages.construction.preview_derivations import validate_composition
        validate_composition(self.manifest)
        if record.get('derivation')!=self.manifest.get('derivation'):raise ValueError('publication_view_composition_mismatch')
        match(package,owned(record))
        self.ownership=owned(record)
        model_hash = sha(files['model.json'])
        agent_hash = sha(files['agent.npz'])
        if (record['profile'] != 'cospace.local-preview-publication/0.1'
                or record['id'] != expected_publication
                or record['model_manifest_sha256'] != model_hash
                or record['files']['model.json']['sha256'] != model_hash
                or record['files']['model.json']['bytes'] != len(files['model.json'])
                or record['files']['agent.npz']['sha256'] != agent_hash
                or record['files']['agent.npz']['bytes'] != len(files['agent.npz'])
                or self.manifest['profile'] != 'cospace.real-model-preview/0.1'
                or self.manifest['members']['agent.npz']['sha256'] != agent_hash
                or record['source_model_sha256'] != self.manifest['members']['spatial.npz']['sha256']):
            raise ValueError('publication_binding')
        self.semantic_snapshot=None
        if semantic:
            for name in SEMANTIC_MEMBERS:
                member=record['files'].get(name,{})
                if member.get('sha256')!=sha(files[name]) or member.get('bytes')!=len(files[name]):
                    raise ValueError('semantic_publication_binding')
            self.semantic_snapshot=snapshot(self.manifest,files['objects.json'],files['ontology.json'])
        self.business_snapshot=None
        if 'business.json' in names:
            member=record['files'].get('business.json',{})
            if member.get('sha256')!=sha(files['business.json']) or member.get('bytes')!=len(files['business.json']):raise ValueError('business_publication_binding')
            self.business_snapshot=business_snapshot(self.manifest,self.semantic_snapshot,files['business.json'])
        self.relation_snapshot=None
        if 'relations.json' in names:
            member=record['files'].get('relations.json',{})
            if member.get('sha256')!=sha(files['relations.json']) or member.get('bytes')!=len(files['relations.json']):raise ValueError('relation_publication_binding')
            self.relation_snapshot=relation_snapshot(self.manifest,self.semantic_snapshot,json.loads(files['ontology.json']),files['relations.json'])
        self.fixed_semantics=None
        if has_instance:
            from packages.service.fixed_semantic_consumption import FixedSemantics
            self.fixed_semantics=FixedSemantics(record,{name:files[name] for name in INSTANCE_FILES},self.manifest,
                self.semantic_snapshot['objects'] if self.semantic_snapshot else [],
                self.relation_snapshot['relations'] if self.relation_snapshot else [])
        elif 'semantic_selection' in record or INSTANCE_MANIFEST in record['files']:
            raise ValueError('semantic_publication_binding')
        self.resolution = self.manifest['agent_view']['resolution_m']
        if not np.isfinite(self.resolution) or self.resolution <= 0:
            raise ValueError('invalid_resolution')
        arrays = bounded_zip(files['agent.npz'], {'cells.npy'}, MAX_CELLS * 24 + 4096)
        stream = io.BytesIO(arrays['cells.npy'])
        version = np.lib.format.read_magic(stream)
        if version != (1, 0): raise ValueError('unsupported_array_format')
        shape, _, dtype = np.lib.format.read_array_header_1_0(stream)
        if (len(shape) != 2 or shape[1] != 3 or shape[0] > MAX_CELLS
                or dtype.kind not in 'iu' or dtype.itemsize > 8):
            raise ValueError('invalid_cells')
        cells = np.load(io.BytesIO(arrays['cells.npy']), allow_pickle=False)
        self.cells = {tuple(map(int, row)) for row in cells}
        self.publication_id = expected_publication
        self.model_hash = model_hash
        self.record=record

    def semantics(self,object_id=None,at=None):
        from packages.service.fixed_semantic_consumption import not_included
        if self.fixed_semantics is None:
            if object_id is not None:raise ValueError('semantic_not_included')
            return not_included(self.record)
        return self.fixed_semantics.summary() if object_id is None else self.fixed_semantics.query(object_id,at)

    @classmethod
    def load(cls, path, expected_publication, expected_sha256):
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        return cls(data, expected_publication, expected_sha256)

    def query(self, point):
        return {**super().query(point), 'publication_id': self.publication_id,
                'publication_model_manifest_sha256': self.model_hash,**self.ownership}

    def objects(self,object_id=None):
        return {**super().objects(object_id),'publication_id':self.publication_id,
                'publication_model_manifest_sha256':self.model_hash}

    def query_range(self,bounds_m,frame_id,limit=DEFAULT_RANGE_CELLS):
        return {**super().query_range(bounds_m,frame_id,limit),
                'publication_id':self.publication_id,
                'publication_model_manifest_sha256':self.model_hash,**self.ownership}
