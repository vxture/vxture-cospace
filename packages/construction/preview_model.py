"""Local candidate model preview; no production release or navigation authority."""
import hashlib
import json
from pathlib import Path
import numpy as np
from packages.lifecycle.preview_scope import owned
from packages.spatial.preview_objects import snapshot,object_result
from packages.spatial.preview_business import business_snapshot,links_for
from packages.spatial.preview_relations import relation_snapshot,relations_for
from packages.spatial.preview_range import surface_range,DEFAULT_RANGE_CELLS


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def surface_cells(points,resolution):
    if (points.ndim!=2 or points.shape[1]!=3 or not len(points) or not np.isfinite(points).all()
        or not np.isfinite(resolution) or resolution<=0): raise ValueError('invalid_grid_input')
    return np.unique(np.floor(points/resolution).astype(np.int64),axis=0)


class PreviewModel:
    def __init__(self,root):
        self.root=Path(root); self.manifest=json.loads((self.root/'model.json').read_bytes())
        if self.manifest['profile']!='cospace.real-model-preview/0.1': raise ValueError('unsupported_preview')
        for name,record in self.manifest['members'].items():
            if Path(name).name!=name or digest(self.root/name)!=record['sha256']:
                raise ValueError('artifact_integrity')
        # Legacy query-only previews have no human view declaration. Once a dual
        # view is declared, both artifacts must identify this exact geometry.
        if 'human_view' in self.manifest:
            canonical=self.manifest['members'].get('spatial.npz',{}).get('sha256')
            for key in ('human_view','agent_view'):
                view=self.manifest.get(key,{})
                if (not canonical or view.get('path') not in self.manifest['members']
                        or view.get('source_model_sha256')!=canonical):
                    raise ValueError('dual_view_source_mismatch')
        from packages.construction.preview_derivations import validate_composition
        validate_composition(self.manifest)
        with np.load(self.root/'agent.npz',allow_pickle=False) as arrays:
            self.cells={tuple(map(int,row)) for row in arrays['cells']}
        self.resolution=self.manifest['agent_view']['resolution_m']
        self.semantic_snapshot=None
        if self.manifest.get('semantic_annotation'):
            with np.load(self.root/'spatial.npz',allow_pickle=False) as arrays:points=arrays['points']
            self.semantic_snapshot=snapshot(self.manifest,(self.root/'objects.json').read_bytes(),
                                            (self.root/'ontology.json').read_bytes(),points)
        self.business_snapshot=None
        if self.manifest.get('business_association'):
            self.business_snapshot=business_snapshot(self.manifest,self.semantic_snapshot,(self.root/'business.json').read_bytes())
        elif 'business.json' in self.manifest['members']:
            raise ValueError('business_declaration_missing')
        self.relation_snapshot=None
        if self.manifest.get('object_relations'):
            self.relation_snapshot=relation_snapshot(self.manifest,self.semantic_snapshot,json.loads((self.root/'ontology.json').read_bytes()),(self.root/'relations.json').read_bytes())
        elif 'relations.json' in self.manifest['members']:raise ValueError('relation_declaration_missing')

    def objects(self,object_id=None):
        result=object_result(self.manifest,self.semantic_snapshot,object_id)
        if self.business_snapshot is not None:
            result['profile']='cospace.preview-object-query/0.2'
            for obj in result['objects']:obj['business_links']=links_for(self.business_snapshot,obj['object_id'])
        if self.relation_snapshot is not None:
            result['profile']='cospace.preview-object-query/0.3'
            result['relations']=relations_for(self.relation_snapshot,object_id)
        return result

    def query_range(self,bounds_m,frame_id,limit=DEFAULT_RANGE_CELLS):
        result=surface_range(self.cells,self.resolution,bounds_m,frame_id,self.manifest['frame_id'],limit)
        return {'profile':'cospace.preview-range/0.1','model_id':self.manifest['id'],
                'source_model_sha256':self.manifest['members']['spatial.npz']['sha256'],
                **result,'quality':'unverified','robot_ready':False,**owned(self.manifest)}

    def query(self,point):
        p=np.asarray(point,dtype=float)
        if p.shape!=(3,) or not np.isfinite(p).all(): raise ValueError('invalid_point')
        index=tuple(int(v) for v in np.floor(p/self.resolution))
        state='surface_candidate' if index in self.cells else 'unknown'
        return {'profile':'cospace.preview-query/0.1','model_id':self.manifest['id'],
            'source_model_sha256':self.manifest['members']['spatial.npz']['sha256'],
            'frame_id':self.manifest['frame_id'],'point_m':p.tolist(),'cell_index':list(index),
            'state':state,'reason':'observed_points_in_cell' if state=='surface_candidate' else 'no_surface_evidence',
            'quality':'unverified','robot_ready':False,**owned(self.manifest)}
