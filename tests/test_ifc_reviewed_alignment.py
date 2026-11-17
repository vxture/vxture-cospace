import numpy as np
import pytest

from experiments.scripts.ifc_reviewed_alignment import reviewed_candidate
from packages.data.ifc_inspection import digest, inspect_ifc
from packages.spatial.scene_identity import content_digest
from test_ifc_alignment import controls
from test_ifc_inspection import fake_reader, FACES
from test_preview_pointcloud import specimen, update


@pytest.fixture
def reviewed_sources(tmp_path, controls):
    source = tmp_path / 'source.ifc'
    source.write_bytes(b'synthetic test source')
    ifc = tmp_path / 'catalog'
    vertices = np.array([p['ifc_m'] for p in controls['pairs']], dtype=float)

    def reader(path):
        metadata, rows = fake_reader(path)
        rows = list(rows)
        rows[1] = (rows[1][0], vertices, FACES)
        return metadata, iter(rows)

    catalog = inspect_ifc(source, ifc, expected_sha256=digest(source), reader=reader)
    cloud = specimen(tmp_path)
    path = cloud / 'cloud.ply'
    header = path.read_bytes().split(b'end_header\n')[0].replace(b'element vertex 2', b'element vertex 6')
    points = np.array([p['cloud_m'] for p in controls['pairs']], dtype='<f4')
    path.write_bytes(header + b'end_header\n' + points.tobytes())
    update(cloud, lambda d: d['cloud'].update(points=6, bytes=path.stat().st_size, sha256=digest(path)))
    update(cloud, lambda d: d['coordinates'].update(frame_id='sensor_local'))
    pins = dict(expected_ifc_sha256=digest(ifc / 'ifc.json'),
                expected_cloud_sha256=digest(path), max_check_error_m=.02)
    sheet = dict(profile='cospace.ifc-control-review/0.1', status='not_aligned',
                 ifc=dict(frame_id=catalog['frame_id'], unit='m', artifact_sha256=pins['expected_ifc_sha256']),
                 cloud=dict(frame_id='sensor_local', unit='m', artifact_sha256=pins['expected_cloud_sha256']),
                 cloud_unit_verified=False, alignment_verified=False,
                 pairs=[dict(id=p['id'], purpose=p['purpose'], description='synthetic',
                             ifc=dict(xyz=p['ifc_m'], reference=dict(global_id='wall', vertex=i)),
                             cloud=dict(xyz=p['cloud_m'], reference=dict(ply_point_index=i)), verified=False)
                        for i, p in enumerate(controls['pairs'])])
    review = dict(profile='cospace.ifc-control-review-record/0.1', worksheet_sha256=content_digest(sheet),
                  reviewer='test-reviewer', unit_evidence=dict(id='unit-report', sha256='d'*64),
                  controls=[dict(control_id=p['id'], evidence=dict(id=p['evidence_ref'], sha256='e'*64))
                            for p in controls['pairs']])
    return sheet, review, ifc, cloud, pins


def run(env):
    sheet, review, ifc, cloud, pins = env
    return reviewed_candidate(sheet, review, ifc, cloud, **pins)


def test_source_checked_controls_produce_candidate_only(reviewed_sources):
    result = run(reviewed_sources)
    assert result['check']['max_m'] < 1e-10
    for key in ('alignment_verified', 'control_evidence_verified', 'real_release_ready', 'evidence_content_verified'):
        assert result[key] is False
    assert result['review_sha256'] == content_digest(reviewed_sources[1])


def test_edited_worksheet_invalidates_review(reviewed_sources):
    reviewed_sources[0]['pairs'][0]['description'] = 'changed'
    with pytest.raises(ValueError, match='review_worksheet_changed'):
        run(reviewed_sources)


@pytest.mark.parametrize('mutation,error', [
    (lambda s: s['pairs'][0]['ifc']['xyz'].__setitem__(0, .1), 'review_point_coordinates_changed'),
    (lambda s: s['pairs'][0]['cloud']['reference'].update(ply_point_index=100), 'review_point_index'),
    (lambda s: s['pairs'][0]['ifc']['reference'].update(global_id='missing'), 'review_ifc_reference'),
    (lambda s: s['cloud'].update(frame_id='wrong'), 'review_source_binding'),
])
def test_rehashed_review_cannot_replace_native_evidence(reviewed_sources, mutation, error):
    sheet, review, *_ = reviewed_sources
    mutation(sheet)
    review['worksheet_sha256'] = content_digest(sheet)
    with pytest.raises(ValueError, match=error):
        run(reviewed_sources)


def test_missing_control_review_rejected(reviewed_sources):
    reviewed_sources[1]['controls'][0]['control_id'] = 'unknown'
    with pytest.raises(ValueError, match='review_control_coverage'):
        run(reviewed_sources)


def test_unit_evidence_is_required(reviewed_sources):
    reviewed_sources[1].pop('unit_evidence')
    with pytest.raises(ValueError):
        run(reviewed_sources)


def test_review_evidence_bytes_checked_without_approving_controls(reviewed_sources, tmp_path):
    from test_evidence_content import put
    sheet, review, ifc, cloud, pins = reviewed_sources
    root = tmp_path / 'evidence'
    ref = put(root)
    review['unit_evidence']['sha256'] = ref['sha256']
    for row in review['controls']:
        row['evidence']['sha256'] = ref['sha256']
    result = reviewed_candidate(sheet, review, ifc, cloud, **pins, evidence_root=root)
    assert result['evidence_receipt']['document_sha256'] == content_digest(review)
    assert result['evidence_receipt']['content_integrity_checked'] is True
    for key in ('alignment_verified', 'control_evidence_verified', 'evidence_content_verified', 'real_release_ready'):
        assert result[key] is False
    (root / (ref['sha256'] + '.bin')).write_bytes(b'changed')
    with pytest.raises(ValueError, match='content_changed'):
        reviewed_candidate(sheet, review, ifc, cloud, **pins, evidence_root=root)
import json



def test_cli_exports_candidate_and_refuses_overwrite(reviewed_sources, tmp_path, monkeypatch):
    from experiments.scripts.ifc_reviewed_alignment import main
    sheet, review, ifc, cloud, pins = reviewed_sources
    worksheet_path, review_path, output = (tmp_path / name for name in ('sheet.json', 'review.json', 'out.json'))
    worksheet_path.write_text(json.dumps(sheet), encoding='utf-8')
    review_path.write_text(json.dumps(review), encoding='utf-8')
    monkeypatch.setattr('sys.argv', [
        'ifc_reviewed_alignment', '--worksheet', str(worksheet_path), '--review', str(review_path),
        '--ifc-root', str(ifc), '--cloud-root', str(cloud), '--output', str(output),
        '--ifc-sha256', pins['expected_ifc_sha256'], '--cloud-sha256', pins['expected_cloud_sha256'],
        '--max-check-error-m', '.02'])
    main()
    original = output.read_bytes()
    assert json.loads(original)['status'] == 'review_required'
    with pytest.raises(FileExistsError):
        main()
    assert output.read_bytes() == original
