import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile
import pytest
from packages.infrastructure.preview_backup import backup,verify,restore,tree
from packages.infrastructure.preview_service_lock import service_guard


@pytest.fixture
def runtime(tmp_path):
    root=tmp_path/'business'
    for name in ('runtime','policy','setup'):(root/name).mkdir(parents=True)
    (root/'setup/sources.json').write_text(json.dumps({'profile':'cospace.preview-sources/0.1','sources':[]}))
    (root/'setup/workspace-scenes.json').write_text(json.dumps({'profile':'cospace.workspace-scenes/0.1','revision':1,'workspaces':[]}))
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    from packages.service.space_access import SpaceAccessPolicy
    SpacePolicyStore(root/'policy').replace(SpaceAccessPolicy(bindings=[],grants=[]),expected_revision=0,actor='fixture',reason='policy audit')
    data=root/'runtime/preview-inputs/uploads/snapshot';data.mkdir(parents=True);(data/'cloud.ply').write_bytes(b'actual fixture bytes')
    (root/'runtime/preview-inputs/input-aaaaaaaaaaaaaaaa.json').write_text(json.dumps({'snapshot':str(data.resolve())}))
    with service_guard(root/'runtime'):pass
    return root,tmp_path/'backup.zip'


def save(env):
    root,output=env
    return backup(root,output,actor='test_operator',reason='P23 controlled acceptance')


def test_backup_verify_and_original_path_restore_preserve_every_byte(runtime):
    root,output=runtime;before=tree(root);result=save(runtime)
    assert tree(root)==before and result['files']==len(before)
    checked=verify(output,result['sha256']);assert checked['manifest']['sessions_included'] is False
    assert checked['manifest']['actor']=='test_operator'
    root.rename(root.with_name('source-evidence'))
    restored=restore(output,root,result['sha256'])
    assert restored['login_required'] and tree(root)==before
    assert Path(json.loads((root/'runtime/preview-inputs/input-aaaaaaaaaaaaaaaa.json').read_bytes())['snapshot']).exists()


@pytest.mark.parametrize('external',[False,True])
def test_scene_cloud_binding_backup_is_self_contained(runtime,external):
    from test_scene_pointcloud_workspace import assets_at
    root,output=runtime
    location=root.parent/'external-cloud' if external else root/'runtime/preview-inputs/full-cloud'
    config,_,_,_=assets_at(location,'space-'+'1'*16)
    (root/'setup/scene-pointclouds.json').write_bytes(config.read_bytes())
    if external:
        with pytest.raises(ValueError,match='external_scene_cloud_assets'):save(runtime)
        assert not output.exists()
    else:
        before=tree(root);result=save(runtime)
        root.rename(root.with_name('before-restore'))
        assert restore(output,root,result['sha256'])['status']=='passed'
        assert tree(root)==before


def test_unfinished_scene_composition_blocks_backup(runtime):
    root,_=runtime;job=root/'runtime/preview-inputs/scene-compositions/compose-test/job.json'
    job.parent.mkdir(parents=True);job.write_text('{"state":"running"}')
    with pytest.raises(ValueError,match='unfinished_composition'):save(runtime)


def test_running_service_and_second_start_block_backup(runtime):
    root,output=runtime
    with service_guard(root/'runtime'):
        with pytest.raises(ValueError,match='stop_managed_service'):save(runtime)
        command=[sys.executable,'-c',"from packages.infrastructure.preview_service_lock import service_guard; import sys;\nwith service_guard(sys.argv[1]): pass",str(root/'runtime')]
        result=subprocess.run(command,capture_output=True,text=True)
        assert result.returncode!=0 and 'stop_managed_service' in result.stderr
    assert not output.exists()
    assert save(runtime)['status']=='passed'


@pytest.mark.parametrize('suffix',['.pending','.tmp','-wal','-shm','-journal'])
def test_unfinished_files_rejected(runtime,suffix):
    root,output=runtime;(root/('runtime/file'+suffix)).write_bytes(b'x')
    with pytest.raises(ValueError,match='unfinished_write'):save(runtime)
    assert not output.exists()


@pytest.mark.parametrize('kind',['job','view'])
@pytest.mark.parametrize('state',['queued','running'])
def test_unfinished_workers_rejected(runtime,kind,state):
    root,_=runtime
    p=root/'runtime/preview-builds/build-one'/('job.json' if kind=='job' else 'views/view-one/task.json')
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'state':state}))
    with pytest.raises(ValueError,match='unfinished_build'):save(runtime)


def test_sessions_and_failure_markers_never_silently_included(runtime):
    root,_=runtime;(root/'sessions').mkdir()
    with pytest.raises(ValueError,match='runtime_policy_setup_only'):save(runtime)
    (root/'sessions').rmdir();(root/'setup/fail-next-model').write_text('explicit failure')
    with pytest.raises(ValueError,match='unfinished_write'):save(runtime)


def test_external_registered_input_rejected(runtime,tmp_path):
    root,_=runtime
    p=root/'runtime/preview-inputs/input-aaaaaaaaaaaaaaaa.json';p.write_text(json.dumps({'snapshot':str(tmp_path)}))
    with pytest.raises(ValueError,match='external_or_missing_input'):save(runtime)


def test_external_enabled_source_rejected(runtime):
    root,_=runtime
    (root/'setup/sources.json').write_text(json.dumps({'profile':'cospace.preview-sources/0.1','sources':[{'id':'external','label':'External','enabled':True,'format':'ply_pointcloud','snapshot':'var/external'}]}))
    with pytest.raises(ValueError,match='external_source'):save(runtime)


def test_corrupt_database_rejected(runtime):
    root,_=runtime;(root/'policy/space-policy.sqlite3').write_bytes(b'not a database')
    from packages.infrastructure.platform_identity import IdentityUnavailable
    with pytest.raises(IdentityUnavailable):save(runtime)


def test_backup_needs_managed_launcher_and_exclusive_output(runtime):
    root,output=runtime;(root/'runtime/.preview-service.lock').unlink()
    with pytest.raises(ValueError,match='managed_service_lock_required'):save(runtime)
    with service_guard(root/'runtime'):pass
    with pytest.raises(ValueError,match='exclusive_output'):backup(root,root/'backup.zip',actor='a',reason='b')
    result=save(runtime)
    with pytest.raises(ValueError,match='exclusive_output'):save(runtime)
    assert verify(output,result['sha256'])['status']=='passed'


def test_digest_wrong_path_and_existing_target_are_refused(runtime):
    root,output=runtime;r=save(runtime);before=tree(root)
    with pytest.raises(ValueError,match='absent_target'):restore(output,root,r['sha256'])
    with pytest.raises(ValueError,match='original_path'):restore(output,root.with_name('other'),r['sha256'])
    with pytest.raises(ValueError,match='digest_mismatch'):verify(output,'0'*64)
    with pytest.raises(ValueError,match='external_sha256'):verify(output,'')
    assert tree(root)==before


def rewrite(env,name,payload,*,manifest_edit=None):
    _,output=env
    with zipfile.ZipFile(output) as z:files={n:z.read(n) for n in z.namelist()}
    files[name]=payload
    if manifest_edit:
        m=json.loads(files['manifest.json']);manifest_edit(m);files['manifest.json']=json.dumps(m).encode()
    output.unlink()
    with zipfile.ZipFile(output,'w') as z:
        for n,b in files.items():z.writestr(n,b)
    return hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize('name',['../outside','runtime/../../outside','runtime/CON','runtime/dir\\escape','runtime/FILE.','runtime/a:b'])
def test_archive_paths_rejected_even_with_matching_outer_digest(runtime,name):
    save(runtime);_,output=runtime
    def edit(m):m['files'][name]={'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
    sha=rewrite(runtime,name,b'x',manifest_edit=edit)
    with pytest.raises(ValueError,match='member_path'):verify(output,sha)


def test_changed_member_not_hidden_by_valid_outer_digest(runtime):
    root,output=runtime;save(runtime);name='runtime/preview-inputs/uploads/snapshot/cloud.ply'
    original=(root/name).read_bytes();sha=rewrite(runtime,name,b'x'*len(original))
    with pytest.raises(ValueError,match='member_digest_mismatch'):verify(output,sha)


def test_duplicate_members_refused(runtime):
    _,output=runtime;save(runtime)
    with zipfile.ZipFile(output,'a') as z:z.writestr('RUNTIME/preview-inputs/uploads/snapshot/cloud.ply',b'x')
    with pytest.raises(ValueError,match='duplicate'):verify(output,hashlib.sha256(output.read_bytes()).hexdigest())


def test_restore_corrupt_package_does_not_create_target(runtime):
    root,output=runtime;r=save(runtime);root.rename(root.with_name('source-evidence'))
    with output.open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='digest_mismatch'):restore(output,root,r['sha256'])
    assert not root.exists() and not list(root.parent.glob('.business.restore-*'))


def test_cli_rejection_and_verify_receipt(runtime):
    _,output=runtime;r=save(runtime)
    command=[sys.executable,'-m','experiments.scripts.workbench_backup','verify','--archive',str(output),'--sha256',r['sha256']]
    p=subprocess.run(command,capture_output=True,text=True,check=True);assert json.loads(p.stdout)['sha256']==r['sha256']
    p=subprocess.run(command[:-1]+['0'*64],capture_output=True,text=True)
    assert p.returncode==2 and 'backup_archive_digest_mismatch' in p.stderr


def test_private_rules_history_ledger_and_retirement_bytes_are_not_skipped(runtime):
    root,output=runtime
    for name in ('runtime/preview-ontologies/.workspaces/hash/rule/1.0.0/rules.json',
                 'runtime/preview-ledger/ledger-one.json','runtime/preview-builds/publications/preview-one/publication.json'):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'{"historical":"fixture"}')
    before=tree(root);r=save(runtime)
    root.rename(root.with_name('source-evidence'));restore(output,root,r['sha256'])
    assert tree(root)==before


def test_source_change_during_copy_never_publishes_backup(runtime,monkeypatch):
    root,output=runtime;original=zipfile.ZipFile.write
    def changed(archive,filename,*args,**kwargs):
        result=original(archive,filename,*args,**kwargs)
        if Path(filename).name=='cloud.ply':Path(filename).write_bytes(b'changed during backup')
        return result
    monkeypatch.setattr(zipfile.ZipFile,'write',changed)
    with pytest.raises(ValueError,match='backup_source_changed'):save(runtime)
    assert not output.exists() and not list(output.parent.glob('.backup.zip.*.tmp'))


def test_restore_database_corruption_even_with_recomputed_manifest_never_commits(runtime):
    root,output=runtime;save(runtime);payload=b'not sqlite';name='policy/space-policy.sqlite3'
    def edit(m):m['files'][name]={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    sha=rewrite(runtime,name,payload,manifest_edit=edit);root.rename(root.with_name('source-evidence'))
    from packages.infrastructure.platform_identity import IdentityUnavailable
    with pytest.raises(IdentityUnavailable):restore(output,root,sha)
    assert not root.exists() and not list(root.parent.glob('.business.restore-*'))


@pytest.mark.parametrize('name',['policy/sessions/token.json','setup/client-secret.json','runtime/sessions/token.json'])
def test_credentials_or_login_stores_inside_backup_layout_are_rejected(runtime,name):
    root,_=runtime;p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('never archive this credential fixture')
    with pytest.raises(ValueError,match='no_sessions_or_credentials'):save(runtime)
