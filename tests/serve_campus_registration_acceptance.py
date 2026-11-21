"""LOCAL ACCEPTANCE ONLY: synthetic campus, isolated data, loopback mock identities.

Build the workbench first. Supply a new runtime directory outside the repository.
The lifecycle document exercises approval branches only in this mock runtime;
it must never be imported into a production environment.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New isolated runtime directory outside the repository')
    parser.add_argument('--port', type=int, default=18878)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to(REPO) or not 1024 <= args.port <= 65535:
        parser.error('new_external_runtime_and_loopback_port_required')
    if not (REPO / 'apps/workbench/dist/index.html').is_file():
        parser.error('build_workbench_first')
    os.chdir(REPO)
    os.environ['COSPACE_REGISTRATION_ADAPTERS'] = 'wgs84_local_enu/1'
    os.environ['COSPACE_GLOBE_IMAGERY_URL'] = ''
    os.environ['COSPACE_GLOBE_TERRAIN_URL'] = ''
    sys.path[:0] = [str(REPO), str(REPO / 'tests')]

    import numpy as np
    import uvicorn
    from cryptography.fernet import Fernet
    from pydantic import SecretStr
    from experiments.scripts.platform_auth_fixture import MockAccounts
    from experiments.scripts.pack_input_upload import pack
    from experiments.scripts.serve_nyu_flow_preview import create_app
    from packages.construction.preview_changes import CompareRequest, ReviewRequest, compare, confirm
    from packages.construction.preview_model import digest
    from packages.construction.preview_semantics import annotate
    from packages.infrastructure.platform_rp import RpConfig
    from packages.infrastructure.platform_session_store import LocalRpStore
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    from packages.lifecycle.space_settings import SpaceSettingsChange
    from packages.service.platform_auth_http import create_auth_app
    from packages.service.platform_business_http import BusinessAccess
    from packages.service.platform_login import PlatformLogin
    from packages.service.scene_registrations import source_from_model
    from packages.service.space_access import SpaceAccessPolicy
    from packages.spatial.georeference import evaluate_registration
    from packages.spatial.preview_objects import SemanticRequest
    from test_preview_workflow import prepared

    root.mkdir(parents=True, exist_ok=False)
    (root / 'business').mkdir()
    initial, jobs, directory, spaces, ontologies, pubs, old, new = prepared(root / 'business')
    space = spaces[0]['id']
    directory.settings.change(SpaceSettingsChange.model_validate(dict(
        space_id=space, expected_revision=0, name='智造园区 · 本地合成联调',
        description='110×70m 合成园区，三栋建筑及室外地坪。仅用于功能验证，不代表实测地图或精度验收。',
        address='本地合成园区，不对应现场地址', reason='建立独立功能测试数据',
        location=dict(longitude=116.4, latitude=39.9, altitude=42., crs='WGS84',
                      altitude_reference='ellipsoid', source='合成测试原点，不是测量成果'))),
        'local-fixture', spaces[0])

    cloud_root = root / 'campus-ply'
    cloud_root.mkdir()
    points = [(float(x), float(y), -1.) for x in range(-5, 106, 2) for y in range(-5, 66, 2)]
    for x0, x1, y0, y1, height in [(10, 34, 10, 30, 12), (54, 90, 10, 28, 15), (14, 44, 42, 60, 9)]:
        for x in range(x0, x1 + 1, 2):
            for y in range(y0, y1 + 1, 2):
                points.append((float(x), float(y), float(height)))
        for z in range(0, height + 1, 3):
            points += [(float(x), float(y), float(z)) for x in range(x0, x1 + 1, 2) for y in (y0, y1)]
            points += [(float(x), float(y), float(z)) for x in (x0, x1) for y in range(y0, y1 + 1, 2)]
    points = sorted(set(points))
    values = np.array(points, dtype=[('x','<f4'), ('y','<f4'), ('z','<f4')])
    cloud = cloud_root / 'cloud.ply'
    cloud.write_bytes((f'ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n'
        'property float x\nproperty float y\nproperty float z\nend_header\n').encode() + values.tobytes())
    manifest = dict(profile='cospace.pointcloud-input/0.1',
        cloud=dict(path='cloud.ply', bytes=cloud.stat().st_size, sha256=digest(cloud), points=len(points)),
        coordinates=dict(unit='m', frame_id='campus-local-test', axes=['right','forward','up'],
                         scope='scene_local', scene_alignment='unverified'),
        provenance=dict(kind='derived_single_frame', source_manifest_sha256='a'*64,
            source_member_sha256='b'*64, description='SYNTHETIC: local campus lifecycle acceptance only'))
    (cloud_root / 'pointcloud.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    pack(cloud_root, None, root / 'campus-source.zip', 'ply_pointcloud')
    record = jobs.inputs.register('三栋厂房与地坪 · 合成园区', cloud_root, None, space, 'ply_pointcloud')
    job = jobs.start(record['id'], space)
    print('Building synthetic campus:', job['id'], flush=True)
    deadline = time.monotonic() + 130
    while time.monotonic() < deadline:
        current = next(row for row in jobs.list() if row['id'] == job['id'])
        if current['state'] in ('succeeded', 'failed'):
            break
        time.sleep(.2)
    assert current['state'] == 'succeeded', current
    base = jobs.model(job['id'])
    with np.load(base.root / 'spatial.npz', allow_pickle=False) as arrays:
        geometry = arrays['points']
    ontology = ontologies.register('configs/ontology/indoor-equipment-v0.2.json')
    anchors = [('power-room', 'room', '配电房 · 合成', [10.,10.,0.]),
               ('power-cabinet', 'cabinet', '配电柜 A · 合成', [12.,10.,0.]),
               ('yard-inspection', 'inspection_point', '室外巡检点 · 合成', [54.,10.,0.])]
    annotated = annotate(jobs, ontologies, SemanticRequest.model_validate(dict(space_id=space,
        base_candidate_id=job['id'], base_manifest_sha256=digest(base.root / 'model.json'),
        ontology_ref={key:ontology[key] for key in ('ontology_id','version','sha256')},
        objects=[dict(object_id=identity, type_id=kind, properties=dict(name=name),
            point_index=int(np.argmin(np.linalg.norm(geometry - point, axis=1))))
            for identity,kind,name,point in anchors])))
    candidate = annotated['id']
    # The imported regression fixture has an unrelated room selected. Keep that
    # record as evidence, then start the campus workflow with no active candidate.
    selection_path = jobs.selection_path(space).resolve()
    assert selection_path.is_relative_to(root)
    selection_path.replace(root / 'initial-room-selection.json')
    selection = jobs.selection(space)
    request = dict(space_id=space, candidate_id=candidate, expected_revision=selection['revision'])
    compared = compare(jobs, CompareRequest(**request))
    confirm(jobs, ReviewRequest(**request, comparison_sha256=compared['comparison_sha256'],
        acknowledge_unverified=True, note='合成园区：本地功能联调，非现场验收'))

    document = json.loads(Path('contracts/examples/spatial-registration-campus.json').read_text(encoding='utf-8'))
    document['source'] = source_from_model(jobs.model(candidate), space, candidate)['model_source']
    document['target'].update(title='智造园区 ENU 控制网 · 合成测试',
        horizontal_reference='WGS84 local ENU', vertical_reference='WGS84 local ENU up',
        evidence_ref='LOCAL-SYNTHETIC-CONTROL-SHEET')
    binding = dict(adapter='wgs84_local_enu/1', target_frame_id=document['target']['frame_id'],
        longitude_deg=116.4, latitude_deg=39.9, ellipsoidal_height_m=42.,
        realization='WGS84(G2139)', coordinate_epoch=2026., evidence_ref='LOCAL-SYNTHETIC-ORIGIN')
    report = evaluate_registration(document, expected_source=document['source'])
    assert report['calculation_status'] == 'checks_passed'
    def write(name, value):
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    write('01-synthetic-preview.json', dict(document=document, geographic_binding=binding))
    failed = copy.deepcopy(document)
    failed['controls'][5]['target_m'][0] += .5
    assert evaluate_registration(failed, expected_source=failed['source'])['calculation_status'] == 'check_limits_exceeded'
    write('02-synthetic-k3-failed.json', dict(document=failed, geographic_binding=binding))
    # This file exists only in a loopback mock-identity test runtime. It exercises
    # genuine-data workflow branches; it must never be imported into production.
    lifecycle = copy.deepcopy(document)
    lifecycle['synthetic'] = False
    lifecycle['target']['title'] = '仅本机模拟审批测试 · 非实测成果'
    write('03-LOCAL-ONLY-lifecycle.json', dict(document=lifecycle, geographic_binding=binding))
    wrong = copy.deepcopy(document)
    wrong['source']['candidate_id'] = 'foreign-model-for-rejection'
    write('04-wrong-model-rejected.json', dict(document=wrong, geographic_binding=binding))
    write('control-calculation.json', report)

    accounts = MockAccounts().start()
    accounts.rp_origin = f'http://127.0.0.1:{args.port}'
    accounts.roles = ['workspace:member']
    accounts.profile_claims = dict(active_org_name='本地模拟组织', active_workspace_name='园区合成测试工作区')
    accounts.identity_options = dict(usr_engineer='园区资料工程师（模拟）',
        usr_manager='独立审核管理员（模拟）', usr_local_test='只读查看者（模拟）')
    cfg = RpConfig(issuer=accounts.issuer, backchannel=accounts.issuer, client_id=accounts.client_id,
        client_secret=SecretStr(accounts.secret), origin=accounts.rp_origin, allow_loopback_http=True,
        encryption_key=SecretStr(Fernet.generate_key().decode()))
    rp = PlatformLogin(cfg, LocalRpStore(root / 'sessions', cfg.encryption_key.get_secret_value()))
    policies = SpacePolicyStore(root / 'policy')
    policies.replace(SpaceAccessPolicy.model_validate(dict(
        bindings=[dict(issuer=accounts.issuer, space_id=s['id'], org_id='org_mock', workspace_id='ws_mock') for s in spaces],
        grants=[dict(issuer=accounts.issuer, subject=user, space_id=space, role=role)
            for user,role in [('usr_engineer','engineer'),('usr_manager','manager'),('usr_local_test','viewer')]])),
        expected_revision=0, actor='local-fixture', reason='isolated campus acceptance only')
    app = create_auth_app(rp, Path('apps/workbench/dist'),
        business=create_app(initial, jobs, space_directory=directory, ontologies=ontologies, platform_origin=cfg.origin),
        access=BusinessAccess(rp, policies, directory, jobs))
    context = dict(origin=cfg.origin, root=str(root), space=space, candidate=candidate, input=record['id'],
        points=len(points), old_publication=old['id'], build_candidate=job['id'])
    write('context.json', context)
    (root / 'README.md').write_text('''# 园区配准测试数据（仅本机）

    三栋厂房、地坪、3 个对象锚点；110×70m；右手 X右/Y前/Z上、单位米。
    旋转 18°，平移 E28/N18/U3m；3 个控制点、3 个独立检查点，门限 10cm。
    点位与坐标原点均为合成，不能代表测绘成果或现场精度。

    - campus-source.zip：可复用 PLY 资料包。
    - 01-synthetic-preview.json：合成数据；可核对和保存，禁止提交真实审核。
    - 02-synthetic-k3-failed.json：K3 增加 50cm 偏移；超限应阻止审核。
    - 03-LOCAL-ONLY-lifecycle.json：仅本机模拟身份与隔离库中测试提交/独立审核/采用/发布分支；禁止用于生产。
    - 04-wrong-model-rejected.json：故意绑定错误模型，导入应被拒绝。

    JSON 绑定本次构建摘要，不得套用其他模型。导入其它构建需重新获取来源绑定。
    ''', encoding='utf-8')
    print('Campus fixture ready:', json.dumps(context, ensure_ascii=False), flush=True)
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
    finally:
        accounts.stop()


if __name__ == '__main__':
    main()
