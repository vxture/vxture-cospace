"""Bind stable semantic object IDs to immutable ledger versions in a new candidate."""
from packages.construction.preview_model import digest
from packages.construction.preview_semantics import annotate
from packages.lifecycle.preview_scope import match,scope
from packages.spatial.preview_objects import SemanticRequest


def associate(jobs,ontologies,ledger,request):
    base=jobs.model(request.base_candidate_id);match(base.manifest,scope(jobs.directory,request.space_id))
    if digest(base.root/'model.json')!=request.base_manifest_sha256:raise ValueError('base_candidate_integrity_changed')
    if not base.semantic_snapshot:raise ValueError('semantic_objects_not_available')
    ids={obj['object_id'] for obj in base.semantic_snapshot['objects']};seen=set();records={}
    frozen={r['ref']['record_id']:r for r in base.business_snapshot['records']} if base.business_snapshot else {}
    for binding in request.bindings:
        if binding.object_id not in ids or binding.object_id in seen:raise ValueError('business_object_binding')
        seen.add(binding.object_id);value=frozen.get(binding.ledger_ref.record_id)
        if value is None or value['ref']!=binding.ledger_ref.model_dump():
            value=ledger.resolve(binding.ledger_ref,request.space_id)
        if binding.ledger_ref.record_id in records and records[binding.ledger_ref.record_id]!=value:
            raise ValueError('business_record_binding')
        records[binding.ledger_ref.record_id]=value
    semantic=SemanticRequest(space_id=request.space_id,base_candidate_id=request.base_candidate_id,
        base_manifest_sha256=request.base_manifest_sha256,ontology_ref=base.semantic_snapshot['ontology_ref'],
        objects=[{k:obj[k] for k in ('object_id','type_id','properties')}|{'point_index':obj['evidence']['point_index']}
                 for obj in base.semantic_snapshot['objects']])
    return annotate(jobs,ontologies,semantic,business={'bindings':[b.model_dump() for b in request.bindings],
                    'records':[records[k] for k in sorted(records)]})
