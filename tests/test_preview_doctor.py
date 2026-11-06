import json
from pathlib import Path
from test_preview_source_config import configuration
from test_real_model_preview import make_preview
from apps.cli.preview_doctor import diagnose


def test_missing_files_fail_without_creating_state(tmp_path):
    before=set(tmp_path.rglob('*'))
    report=diagnose(tmp_path,Path('missing-model'),Path('missing-config'))
    assert report['status']=='failed'
    states={c['name']:c['status'] for c in report['checks']}
    assert all(states[k]=='failed' for k in ('sources','initial_model','workbench'))
    assert set(tmp_path.rglob('*'))==before


def test_existing_inputs_checked_without_catalog_creation(tmp_path):
    config,_=configuration(tmp_path)
    model=tmp_path/'model'; model.mkdir(); make_preview(model)
    front=tmp_path/'apps/workbench/dist'; front.mkdir(parents=True); (front/'layout.html').write_text('test')
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report=diagnose(tmp_path,Path('model'),config,True)
    states={c['name']:c for c in report['checks']}
    assert all(states[k]['status']=='passed' for k in ('sources','initial_model','workbench'))
    assert states['sources']['detail']['full_file_check'] is True
    assert {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before
