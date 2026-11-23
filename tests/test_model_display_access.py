from test_platform_business import secured, sign_in
from test_platform_login import runtime


def test_model_display_and_every_range_use_scene_preview_authorization(secured, monkeypatch):
    _, client, _, _, jobs, _, _, _, _, publication = secured
    calls = []
    monkeypatch.setattr(jobs.displays, 'describe', lambda kind, name: calls.append((kind, name)) or
                        {'model': {'id': name}, 'display': {'state': 'ready'}})
    monkeypatch.setattr(jobs.displays, 'resource', lambda *args: calls.append(args) or (b'abc', 0, 2, 10, 'a' * 64))
    candidate = '/candidates/build-one'
    paths = [candidate + '/api/display', candidate + '/display/' + 'a' * 64 + '/octree.bin',
             '/publications/' + publication['id'] + '/api/display',
             candidate + '/display/' + 'b' * 64 + '/hierarchy.bin']
    for path in paths:
        assert client.get(path, headers={'Range': 'bytes=0-2'}).status_code == 401
    assert calls == []
    sign_in(secured)
    assert client.get(paths[0]).status_code == 200
    assert client.get(paths[1], headers={'Range': 'bytes=0-2'}).status_code == 206
    assert client.get(paths[2]).status_code == 200
    assert client.get(paths[3], headers={'Range': 'bytes=0-2'}).status_code == 206
    calls.clear()
    for path in ['/candidates/build-two/api/display', '/candidates/build-two/display/' + 'a' * 64 + '/octree.bin',
                 candidate + '/display/' + 'a' * 64 + '/spatial.npz', candidate + '/display/' + 'a' * 64 + '/octreeXbin']:
        assert client.get(path, headers={'Range': 'bytes=0-2'}).status_code == 403
    assert calls == []


def test_range_does_not_outlive_revoked_session(secured, monkeypatch):
    from test_platform_login import notify_logout
    _, client, accounts, _, jobs, *_ = secured
    calls = []
    monkeypatch.setattr(jobs.displays, 'resource', lambda *args: calls.append(args) or (b'ab', 0, 1, 10, 'a' * 64))
    sign_in(secured)
    path = '/candidates/build-one/display/' + 'a' * 64 + '/octree.bin'
    assert client.get(path, headers={'Range': 'bytes=0-1'}).status_code == 206
    assert notify_logout(client, accounts).status_code == 200
    assert client.get(path, headers={'Range': 'bytes=0-1'}).status_code == 401
    assert len(calls) == 1


def test_exact_queries_require_scene_access_and_recheck_revocation(secured, monkeypatch):
    from test_platform_login import notify_logout
    _, client, accounts, _, jobs, *_ = secured
    calls = []
    monkeypatch.setattr(jobs.displays.exact, 'read', lambda *a, **k: calls.append((a, k)) or
                        {'state': 'ready', 'points': []})
    params = {'manifest_sha256': 'a'*64, 'source_sha256': 'b'*64, 'point_index': '0'}
    path = '/candidates/build-one/api/exact'
    assert client.get(path, params=params).status_code == 401
    assert not calls
    sign_in(secured)
    assert client.get('/candidates/build-two/api/exact', params=params).status_code == 403
    assert not calls
    assert client.get(path, params=params).status_code == 200
    assert notify_logout(client, accounts).status_code == 200
    assert client.get(path, params=params).status_code == 401
    assert len(calls) == 1


def test_exact_objects_use_the_same_scene_gate(secured, monkeypatch):
    _, client, _, _, jobs, *_ = secured
    calls = []
    monkeypatch.setattr(jobs.displays.exact, 'objects', lambda *a: calls.append(a) or {'state':'preparing'})
    params = {'manifest_sha256':'a'*64, 'source_sha256':'b'*64}
    path = '/candidates/build-one/api/exact-objects'
    assert client.get(path, params=params).status_code == 401
    sign_in(secured)
    assert client.get('/candidates/build-two/api/exact-objects', params=params).status_code == 403
    assert not calls
    response = client.get(path, params=params)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert len(calls) == 1
