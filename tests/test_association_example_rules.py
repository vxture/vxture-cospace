import json
from pathlib import Path
from packages.construction.preview_semantics import annotate
from packages.spatial.preview_objects import SemanticRequest
from test_preview_objects import fixture


def test_example_device_types_survive_fixed_candidate_without_changing_geometry(tmp_path):
    _, jobs, _, _, store, body = fixture(tmp_path)
    rule = store.register('configs/ontology/indoor-equipment-v0.3.json')
    original = (jobs.root/'build-one/output/spatial.npz').read_bytes()
    body['ontology_ref'] = {key: rule[key] for key in ('ontology_id', 'version', 'sha256')}
    body['objects'] = [dict(object_id=kind, type_id=kind, properties={'name': name}, point_index=0)
                       for kind, name in [('cabinet', '设备柜 A-01'), ('pump', '泵组 P-01'),
                                          ('control_cabinet', '控制柜 P-03'), ('inspection_cabinet', '检测柜 C-01')]]
    saved = annotate(jobs, store, SemanticRequest.model_validate(body))
    model = jobs.model(saved['id'])
    assert (model.root/'spatial.npz').read_bytes() == original
    assert {o['type_id'] for o in model.objects()['objects']} == {'cabinet', 'pump', 'control_cabinet', 'inspection_cabinet'}
    assert all(o['confirmation'] == 'unverified' for o in model.objects()['objects'])
    old = json.loads(Path('configs/ontology/indoor-equipment-v0.2.json').read_bytes())
    new = json.loads(Path('configs/ontology/indoor-equipment-v0.3.json').read_bytes())
    assert all(new['types'][key] == value for key, value in old['types'].items())
