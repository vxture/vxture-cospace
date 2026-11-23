from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from test_model_display import display
from packages.construction.model_display import encoded
from packages.service.scene_registrations import SceneRegistrations, RegistrationError, Command
from test_scene_registrations import command


def cloud(display, points):
    service, _, _, root, _, client = display
    np.savez_compressed(root / 'spatial.npz', points=points)
    model = json.loads((root / 'model.json').read_bytes())
    model['construction']['model_points'] = len(points)
    if points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all():
        model['bounds_m'] = [points.min(axis=0).tolist(),points.max(axis=0).tolist()]
    ownership = {'space_id':'space-test','project_id':'project-test'}
    model.update(ownership)
    model['source'] = {'input_binding':ownership}
    service.jobs.directory = SimpleNamespace(read=lambda kind, name: {'id':name,'project_id':'project-test'})
    job = json.loads((root.parent/'job.json').read_bytes())
    job.update(ownership, input_binding=ownership)
    (root.parent/'job.json').write_bytes(encoded(job))
    source = sha256((root / 'spatial.npz').read_bytes()).hexdigest()
    model['members']['spatial.npz']['sha256'] = source
    for view in ('human_view', 'agent_view'):
        model[view]['source_model_sha256'] = source
    raw = encoded(model)
    (root / 'model.json').write_bytes(raw)
    return service.exact, (sha256(raw).hexdigest(), source), client, root


def ready(exact, key):
    assert exact.read('candidate', 'build-one', *key, point_index=0)['state'] == 'preparing'
    exact.scan()
    assert exact.describe('candidate', 'build-one', *key)['state'] == 'ready'


def test_original_double_rows_survive_display_reordering_and_large_coordinates(display, monkeypatch):
    points = np.array([[500000.012345678, 4000000.03456789, 18.012345],
                       [500000.015, 4000000.035, 18.015], [500010., 4000010., 20.]])
    exact, key, _, _ = cloud(display, points)
    ready(exact, key)
    # Hot reads must never load NPZ or PreviewModel, including after process restart.
    monkeypatch.setattr(np, 'load', lambda *a, **k: pytest.fail('whole NPZ read'))
    for service in (exact, type(exact)(exact.displays)):
        result = service.read('candidate', 'build-one', *key, point=points[0].tolist(), radius_m=.01)
        assert result['state'] == 'ready'
        assert [p['point_index'] for p in result['points']] == [0, 1]
        assert result['points'][0]['anchor_m'] == points[0].tolist()
        assert result['points'][0]['point_id'] == key[1] + ':0'
        assert service.read('candidate', 'build-one', *key, point_index=2)['points'][0]['anchor_m'] == points[2].tolist()


def test_dense_coincident_and_rounded_rtree_candidates_are_not_silent_nearest(display):
    points = np.vstack([np.repeat([[500000., 4000000., 18.]], 34, axis=0), [[500000.2, 4000000.2, 18.]]])
    exact, key, _, _ = cloud(display, points)
    ready(exact, key)
    assert exact.read('candidate', 'build-one', *key, point=points[0].tolist(), radius_m=.001)['state'] == 'narrow_query'
    result = exact.read('candidate', 'build-one', *key, point=[500000.1, 4000000.1, 18.], radius_m=.001)
    assert result['state'] == 'ready' and result['points'] == []
    assert exact.read('candidate', 'build-one', *key, point_index=33)['points'][0]['point_index'] == 33


def test_stale_binding_integrity_and_capacity_fail_closed(display, monkeypatch):
    exact, key, _, root = cloud(display, np.array([[1., 2., 3.]]))
    ready(exact, key)
    with sqlite3.connect(exact.path(key)) as db:
        db.execute('UPDATE points SET x=42 WHERE id=0')
    with pytest.raises(ValueError, match='exact_integrity'):
        exact.read('candidate', 'build-one', *key, point_index=0)
    (root / 'model.json').write_bytes((root / 'model.json').read_bytes() + b' ')
    with pytest.raises(ValueError, match='exact_source_changed'):
        exact.read('candidate', 'build-one', *key, point_index=0)
    exact, key, _, _ = cloud(display, np.array([[1., 2., 3.], [4., 5., 6.]]))
    monkeypatch.setattr('packages.construction.model_exact.MAX_POINTS', 1)
    assert exact.read('candidate', 'build-one', *key, point_index=0)['state'] == 'preparing'
    exact.scan()
    assert exact.read('candidate', 'build-one', *key, point_index=0)['state'] == 'unavailable'


def test_streaming_build_rejects_wrong_header_and_nonfinite_without_ready_file(display):
    for points in (np.array([[1., 2.]]), np.array([[np.nan, 2., 3.]])):
        exact, key, _, _ = cloud(display, points)
        assert exact.read('candidate', 'build-one', *key, point_index=0)['state'] == 'preparing'
        exact.scan()
        assert not exact.path(key).exists()
        assert exact.read('candidate', 'build-one', *key, point_index=0)['state'] == 'unavailable'


def test_http_validation_version_and_no_store(display):
    exact, key, client, _ = cloud(display, np.array([[1., 2., 3.]]))
    path = '/candidates/build-one/api/exact'
    params = dict(manifest_sha256=key[0], source_sha256=key[1], point_index='0')
    response = client.get(path, params=params)
    assert response.status_code == 200 and response.json()['state'] == 'preparing'
    assert response.headers['cache-control'] == 'no-store'
    exact.scan()
    assert client.get(path, params=params).json()['points'][0]['anchor_m'] == [1, 2, 3]
    for change in ({'point_index': '-1'}, {'point_index': 'true'}, {'point_index': '0.5'},
                   {'x': 'NaN'}, {'x': '1'}, {'manifest_sha256': 'wrong'}, {'other': '1'}):
        assert client.get(path, params=params | change).status_code == 422
    for change in ({'manifest_sha256': 'a'*64}, {'source_sha256': 'b'*64}):
        assert client.get(path, params=params | change).status_code == 409
    assert client.get(path, params=list(params.items())+[('point_index','1')]).status_code == 422
    assert client.get(path, params={**params, 'point_index': '3'}).status_code == 422
    query = {k:v for k,v in params.items() if k != 'point_index'} | dict(x='1', y='2', z='3', radius_m='.01')
    assert client.get(path, params=query).json()['state'] == 'ready'
    assert client.get(path, params=query | {'radius_m': '2'}).status_code == 422


def test_registration_source_is_lightweight_and_exact_evidence_checked_on_check_and_save(display, tmp_path, monkeypatch):
    document = json.loads(__import__('pathlib').Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))
    points = np.array([p['source_m'] for p in document['controls']], dtype='f8')
    exact, key, _, _ = cloud(display, points)
    # The registration frame is derived once, offline; no agent/NPZ hot decode.
    jobs = SimpleNamespace(displays=exact.displays)
    service = SceneRegistrations(tmp_path, 'workspace', 'engineer', jobs)
    model = exact.displays.source('candidate','build-one')[2]
    space = model.get('space_id')
    monkeypatch.setattr(np, 'load', lambda *a, **k: pytest.fail('whole NPZ read'))
    source = service.source(space, 'build-one')
    exact.scan()
    assert service.source(space, 'build-one') == source
    document['source'] = source['model_source']
    document['controls'][0]['evidence_ref'] = 'model-point:' + key[1] + ':0'
    request = dict(space_id=space,candidate_id='build-one',source_sha256=key[0],document=document)
    service.check(source, request)
    service._change(source, Command.model_validate(command(document)))
    bad = deepcopy(document)
    bad['controls'][0]['source_m'][0] += .001
    with pytest.raises(RegistrationError, match='registration_exact_point_invalid'):
        service.check(source, request | {'document': bad})
    with pytest.raises(RegistrationError, match='registration_exact_point_invalid'):
        service._change(source, Command.model_validate(command(bad, revision=1, key=2)))
    bad['controls'][0]['evidence_ref'] = 'model-point:' + 'a'*64 + ':0'
    with pytest.raises(RegistrationError, match='registration_exact_point_invalid'):
        service.verify_points(bad)


def test_existing_objects_use_bounded_original_rows_without_whole_model_decode(tmp_path, monkeypatch):
    from test_preview_workflow import prepared
    from packages.construction.model_display import ModelDisplays
    _, jobs, _, _, _, _, _, publication = prepared(tmp_path)
    record = {'id':publication['candidate_id']}
    model = jobs.model(record['id'])
    expected = model.objects()
    assert expected['relations'] and any(obj.get('business_links') for obj in expected['objects'])
    # Old fixture predates construction metadata; the runtime requires its count.
    manifest = model.manifest
    manifest['unit'] = 'm'
    with np.load(model.root/'spatial.npz') as arrays:
        manifest['construction'] = {'model_points':len(arrays['points'])}
    raw = encoded(manifest)
    (model.root/'model.json').write_bytes(raw)
    displays = ModelDisplays(jobs)
    exact = displays.exact
    key = (sha256(raw).hexdigest(), manifest['members']['spatial.npz']['sha256'])
    assert exact.objects('candidate',record['id'],*key) == {'state':'preparing'}
    exact.scan()
    monkeypatch.setattr(np,'load',lambda *a,**k:pytest.fail('whole NPZ read'))
    result = exact.objects('candidate',record['id'],*key)
    assert result == expected | {'state':'ready','source_manifest_sha256':key[0]}
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from packages.service.model_display_http import install
    app = FastAPI()
    install(app,displays)
    with TestClient(app) as client:
        path = f"/candidates/{record['id']}/api/exact-objects"
        parameters = dict(manifest_sha256=key[0],source_sha256=key[1])
        response = client.get(path,params=parameters)
        assert response.status_code == 200 and response.json() == result
        assert response.headers['cache-control'] == 'no-store'
        assert client.get(path,params=parameters|{'point_index':'0'}).status_code == 422
        assert client.get(path,params=parameters|{'manifest_sha256':'f'*64}).status_code == 409
        assert client.get(path,params=list(parameters.items())+[('source_sha256',key[1])]).status_code == 422
    objects = json.loads((model.root/'objects.json').read_bytes())
    objects['objects'][0]['anchor_m'][0] += .01
    changed = encoded(objects)
    (model.root/'objects.json').write_bytes(changed)
    manifest['members']['objects.json'] = {'sha256':sha256(changed).hexdigest(),'bytes':len(changed)}
    raw = encoded(manifest)
    (model.root/'model.json').write_bytes(raw)
    key = (sha256(raw).hexdigest(),key[1])
    assert exact.objects('candidate',record['id'],*key)['state'] == 'preparing'
    exact.scan()
    with pytest.raises(ValueError,match='object_anchor_mismatch'):
        exact.objects('candidate',record['id'],*key)


def test_exact_read_slots_and_disk_budget_are_bounded(display, monkeypatch):
    exact, key, _, _ = cloud(display, np.array([[1.,2.,3.]]))
    ready(exact,key)
    for _ in range(4):
        assert exact.read_slots.acquire(blocking=False)
    assert exact.read('candidate','build-one',*key,point_index=0)['state'] == 'busy'
    for _ in range(4):
        exact.read_slots.release()
    exact.path(key).unlink()
    monkeypatch.setattr('packages.construction.model_exact.shutil.disk_usage',lambda _:SimpleNamespace(free=0))
    exact.read('candidate','build-one',*key,point_index=0)
    exact.scan()
    assert exact.read('candidate','build-one',*key,point_index=0)['state'] == 'unavailable'
