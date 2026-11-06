"""Generate a relation candidate over unchanged geometry and stable semantic objects."""
from packages.construction.preview_model import digest
from packages.construction.preview_semantics import annotate
from packages.lifecycle.preview_scope import scope,match
from packages.spatial.preview_objects import SemanticRequest

def relate(jobs,ontologies,request):
    base=jobs.model(request.base_candidate_id);match(base.manifest,scope(jobs.directory,request.space_id))
    if digest(base.root/'model.json')!=request.base_manifest_sha256:raise ValueError('base_candidate_integrity_changed')
    if not base.semantic_snapshot:raise ValueError('semantic_objects_not_available')
    semantic=SemanticRequest(space_id=request.space_id,base_candidate_id=request.base_candidate_id,
        base_manifest_sha256=request.base_manifest_sha256,ontology_ref=request.ontology_ref,
        objects=[{k:o[k] for k in ('object_id','type_id','properties')}|{'point_index':o['evidence']['point_index']}
                 for o in base.semantic_snapshot['objects']])
    return annotate(jobs,ontologies,semantic,relations=[r.model_dump()|{'confirmation':'unverified'} for r in request.relations])
