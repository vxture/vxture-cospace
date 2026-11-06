import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from pydantic import ValidationError
from experiments.scripts import trial_workbench as trial
from test_workbench_backup import runtime as backup_runtime
from packages.infrastructure.preview_backup import backup,verify,restore,tree


def config(tmp_path,**changes):
    return trial.TrialConfig(profile='cospace.windows-trial/0.1',mode='mock',port=18790,accounts_port=19227,
        business_root=str(tmp_path/'business'),state_root=str(tmp_path/'state'),**changes)


def test_empty_trial_is_explicit_isolated_and_cannot_overwrite(tmp_path):
    cfg=config(tmp_path);trial.initialize(cfg)
    assert json.loads((Path(cfg.business_root)/'setup/consumer-access.json').read_bytes())['grants']==[]
    assert list((Path(cfg.business_root)/'runtime').iterdir())==[]
    with pytest.raises(FileExistsError):trial.initialize(cfg)
    with pytest.raises(ValueError):trial.initialize(cfg.model_copy(update={'mode':'platform','business_root':str(tmp_path/'other')}))
    assert trial.current(cfg)=={'status':'stopped'}


@pytest.mark.parametrize('changes',[
    {'business_root':str(trial.REPO/'var/validation/old')}, {'state_root':str(trial.REPO/'var/samples')},
    {'business_root':str(trial.REPO)}, {'business_root':'relative'}, {'port':19127,'accounts_port':19127},
    {'business_root':str(trial.REPO/'var')},
])
def test_protect_original_samples_and_validation_roots(tmp_path,changes):
    doc=config(tmp_path).model_dump()|changes
    with pytest.raises(ValidationError):trial.TrialConfig.model_validate(doc)


def test_release_changes_with_runtime_code_assets_or_config_not_business(tmp_path,monkeypatch):
    repo=tmp_path/'checkout';repo.mkdir();monkeypatch.setattr(trial,'REPO',repo)
    for name in ('packages/example.py','experiments/scripts/example.py','contracts/schemas/example.json','apps/workbench/dist/layout.html',
                 'pyproject.toml','uv.lock','apps/workbench/pnpm-lock.yaml','apps/workbench/package.json'):
        p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('pinned bytes')
    cfg=config(tmp_path);baseline=trial.release(cfg)
    (repo/'var').mkdir();(repo/'var/data.json').write_text('business mutation')
    assert trial.release(cfg)==baseline
    (repo/'packages/example.py').write_text('new code')
    assert trial.release(cfg)!=baseline


def test_consumer_grants_included_in_cold_restore_without_credentials(backup_runtime):
    root,output=backup_runtime
    path=root/'setup/consumer-access.json'
    path.write_text(json.dumps({'profile':'cospace.online-consumer-access/0.1','audience':'cospace',
        'grants':[{'caller':'robot-product','space_id':'space-'+'a'*16}]}))
    before=tree(root);result=backup(root,output,actor='trial',reason='grants recovery')
    assert 'setup/consumer-access.json' in result['manifest']['files']
    root.rename(root.with_name('preserved'))
    restore(output,root,result['sha256']);assert tree(root)==before


def test_consumer_configuration_rejects_secret_in_backup(backup_runtime):
    root,output=backup_runtime
    (root/'setup/consumer-access.json').write_text(json.dumps({'profile':'cospace.online-consumer-access/0.1','audience':'cospace','grants':[],
                                                             'client_secret':'not-allowed'}))
    with pytest.raises(ValueError):backup(root,output,actor='trial',reason='must reject')
    assert not output.exists()


@pytest.mark.skipif(os.name!='nt',reason='Windows trial ownership')
def test_abrupt_trial_owner_exit_kills_descendant_before_late_write(tmp_path):
    ready=tmp_path/'ready';late=tmp_path/'late'
    child="from pathlib import Path;import sys,time;Path(sys.argv[1]).write_text('ready');time.sleep(2);Path(sys.argv[2]).write_text('late')"
    code="from packages.infrastructure.trial_job import bind_trial_process;import subprocess,sys,time;bind_trial_process();subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]],creationflags=0x08000000);time.sleep(30)"
    proc=subprocess.Popen([sys.executable,'-c',code,child,str(ready),str(late)],creationflags=0x08000000)
    try:
        for _ in range(100):
            if ready.exists():break
            if proc.poll() is not None:pytest.fail('owner failed before child acknowledgement')
            time.sleep(.05)
        assert ready.exists();proc.kill();proc.wait(timeout=5);time.sleep(2.2)
        assert not late.exists()
    finally:
        if proc.poll() is None:proc.kill();proc.wait(timeout=5)
