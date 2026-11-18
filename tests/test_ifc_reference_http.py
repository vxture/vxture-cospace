from fastapi.testclient import TestClient

from experiments.scripts.run_scene_ifc_worker import drain_one
from experiments.scripts.serve_nyu_flow_preview import create_app
from packages.service.platform_auth_http import create_auth_app
from packages.service.platform_business_http import BusinessAccess
from test_ifc_inspection import assets_at
from test_platform_business import secured, sign_in
from test_platform_login import runtime
from test_scene_ifc_versions import parse_fixture

BASE = '/api/scene-ifc/references'


def exercise(env, parse, original, filename, expected_roles):
    rp,_,accounts,clock,jobs,directory,spaces,policies,old,new = env
    space, other = (s['id'] for s in spaces[:2])
    access = BusinessAccess(rp, policies, directory, jobs, scene_ifc_self_service=True)
    app = create_auth_app(rp, business=create_app(None, jobs, space_directory=directory,
                          platform_origin=rp.config.origin), access=access)
    with TestClient(app, base_url=rp.config.origin, follow_redirects=False) as client:
        auth = (rp,client,accounts,clock,jobs,directory,spaces,policies,old,new)
        params = {'space_id':space}
        assert client.get(BASE, params=params).status_code == 401
        headers,_ = sign_in(auth,'usr_engineer')
        response = client.post('/api/scene-attachments', params=params|{'name':filename}, content=original, headers=headers)
        assert response.status_code == 201, response.text
        body=params|{'attachment_id':response.json()['attachment']['id']}
        assert client.post(BASE,json=body).status_code == 403
        task=client.post(BASE,json=body,headers=headers)
        assert task.status_code == 202, task.text
        key=task.json()['task_id']
        assert client.post(BASE,json=body,headers=headers).status_code == 200
        assert client.get(BASE,params={'space_id':other}).status_code == 403
        preview = params|{'task_id':key}
        activation = preview|{'expected_revision':0}
        assert client.get(BASE+'/preview',params=preview).status_code == 409
        assert client.post(BASE+'/activate',json=activation,headers=headers).status_code == 409
        assert drain_one(access.ifc_versions,parse)
        assert client.get('/api/scene-ifc',params=params).json()['configured'] is False
        result=client.get(BASE+'/preview',params=preview)
        assert result.status_code == 200, result.text
        summary=result.json()
        assert summary['role_counts'] == expected_roles
        assert summary['assessment'] == 'unverified' and str(jobs.inputs.root) not in result.text
        assert not client.get('/api/scene-ifc/structure',params=params|{'catalog_sha256':summary['catalog_sha256']}).json()['configured']
        for user in ('usr_local_test','usr_other'):
            denied,_=sign_in(auth,user)
            assert client.get(BASE,params=params).status_code == 403
            assert client.get(BASE+'/preview',params=preview).status_code == 403
            assert client.post(BASE+'/activate',json=activation,headers=denied).status_code == 403
        headers,_ = sign_in(auth,'usr_engineer')
        selected=client.post(BASE+'/activate',json=activation,headers=headers)
        assert selected.status_code == 200, selected.text
        assert selected.json()['catalog_sha256'] == summary['catalog_sha256']
        assert client.post(BASE+'/activate',json=activation,headers=headers).status_code == 409
        listing=client.get(BASE,params=params).json()
        assert listing['current'] == key and listing['revision'] == 1
        assert 'lease_until' not in listing['tasks'][0] and 'attempt' not in listing['tasks'][0]
        structure=client.get('/api/scene-ifc/structure',params=params|{'catalog_sha256':summary['catalog_sha256']}).json()
        assert structure['declared_role_counts'] == expected_roles
        assert not structure['alignment_verified'] and not structure['real_release_ready']
        package=client.get('/api/scene-ifc/design-package',params=params|{'catalog_sha256':summary['catalog_sha256']})
        assert package.status_code == 200, package.text[:500]
        return summary


def test_upload_queue_preview_explicit_activation_and_permissions(secured):
    exercise(secured,parse_fixture,b'design fixture','sample.ifc',{'wall':1})


def test_legacy_reference_stays_readable_until_it_can_be_retained_for_rollback(secured,tmp_path):
    rp,_,accounts,clock,jobs,directory,spaces,policies,old,new = secured
    space=spaces[0]['id']
    config,_,_=assets_at(tmp_path/'legacy-ifc',space)
    access=BusinessAccess(rp,policies,directory,jobs,scene_ifc_config=config,scene_ifc_self_service=True)
    app=create_auth_app(rp,business=create_app(None,jobs,space_directory=directory,platform_origin=rp.config.origin),access=access)
    with TestClient(app,base_url=rp.config.origin,follow_redirects=False) as client:
        headers,_=sign_in((rp,client,accounts,clock,jobs,directory,spaces,policies,old,new),'usr_engineer')
        prior=client.get('/api/scene-ifc',params={'space_id':space}).json()
        assert prior['configured']
        denied=client.post(BASE+'/activate',json={'space_id':space,'task_id':'a'*64,'expected_revision':0},headers=headers)
        assert denied.status_code==409 and denied.json()['detail']=='ifc_legacy_migration_required'
        assert client.get('/api/scene-ifc',params={'space_id':space}).json()==prior
