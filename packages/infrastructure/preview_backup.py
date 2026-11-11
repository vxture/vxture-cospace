"""Cold, self-contained local workbench backups; restore original absolute paths.

No session stores or credentials are accepted. Archive trust is the externally
recorded SHA-256, not a digest read from the archive itself.
"""
from datetime import datetime,timezone
from contextlib import closing
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import sqlite3
import stat
import uuid
import zipfile
from packages.infrastructure.preview_service_lock import service_guard
from packages.lifecycle.preview_control_lock import mutation_guard

PROFILE='cospace.workbench-backup/0.1'
ROOTS={'runtime','policy','setup'}
LOCKS={'.preview-mutation.lock','.preview-service.lock'}
RUNTIME_DIRS={'preview-inputs','preview-builds','preview-directory','preview-ontologies','preview-ledger'}
MAX_FILES=100_000
MAX_BYTES=2_000_000_000


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def safe_name(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name:
        raise ValueError('backup_member_path')
    parts=PurePosixPath(name).parts
    if (not parts or parts[0] not in ROOTS or len(parts)<2 or '/'.join(parts)!=name
            or any(p in ('.','..') or p.endswith((' ','.')) or p in LOCKS
                   or re.fullmatch(r'(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?',p)
                   or any(c in p for c in '<>"|?*') or any(ord(c)<32 for c in p) for p in parts)):
        raise ValueError('backup_member_path')
    return name


def business_member(name):
    # Retain retired seat audit files in existing backups; runtime no longer uses them.
    parts=PurePosixPath(name).parts
    if (parts[0]=='setup' and name not in ('setup/sources.json','setup/workspace-scenes.json','setup/consumer-access.json','setup/scene-pointclouds.json','setup/scene-ifc.json')
            or parts[0]=='policy' and name not in ('policy/space-policy.sqlite3','policy/platform-events.sqlite3','policy/product-seats.sqlite3','policy/.workspace-scenes-required')
            or parts[0]=='runtime' and not (name in ('runtime/preview-lifecycle.sqlite3','runtime/business-versions.sqlite3')
                or len(parts)>2 and parts[1] in RUNTIME_DIRS)):
        raise ValueError('backup_business_layout_only_no_sessions_or_credentials')


def tree(root):
    root=Path(root).resolve()
    if not root.is_dir() or {p.name for p in root.iterdir()}!=ROOTS:
        raise ValueError('backup_requires_runtime_policy_setup_only')
    result={};total=0;folded=set()
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(root):
            raise ValueError('backup_links_not_supported')
        if p.is_dir():continue
        if not p.is_file():raise ValueError('backup_regular_files_required')
        if p.name in LOCKS:continue
        name=safe_name(p.relative_to(root).as_posix())
        if name.casefold() in folded:raise ValueError('backup_duplicate_member')
        folded.add(name.casefold())
        if p.name.endswith(('.pending','.tmp','-wal','-shm','-journal')) or p.name=='fail-next-model':
            raise ValueError('backup_unfinished_write_or_failure_marker')
        business_member(name)
        total+=p.stat().st_size
        if len(result)>=MAX_FILES or total>MAX_BYTES:raise ValueError('backup_budget')
        result[name]={'bytes':p.stat().st_size,'sha256':digest(p)}
    return result


def validate_runtime(root,original_root=None):
    root=Path(root).resolve();original_root=Path(original_root or root).resolve()
    for required in ('setup/sources.json','setup/workspace-scenes.json','policy/space-policy.sqlite3'):
        if not (root/required).is_file():raise ValueError('backup_configuration_missing')
    sources=json.loads((root/'setup/sources.json').read_bytes())
    from packages.data.preview_source_config import Config
    from packages.lifecycle.workspace_scenes import WorkspaceSceneConfig
    from packages.infrastructure.space_policy_store import SpacePolicyStore
    Config.model_validate(sources)
    WorkspaceSceneConfig.model_validate_json((root/'setup/workspace-scenes.json').read_bytes())
    cloud_config=root/'setup/scene-pointclouds.json'
    if cloud_config.exists():
        from packages.data.scene_pointcloud_workspace import SceneCloudConfig
        parsed=SceneCloudConfig.model_validate_json(cloud_config.read_bytes())
        if len({b.space_id for b in parsed.bindings})!=len(parsed.bindings):raise ValueError('backup_duplicate_scene_cloud_binding')
        for binding in parsed.bindings:
            for location,member,expected in ((binding.root,'scene.json',binding.scene_sha256),
                                             (binding.tiles_root,'index.json',binding.index_sha256)):
                path=Path(location)
                if not path.is_absolute() or not path.resolve().is_relative_to(original_root/'runtime/preview-inputs'):
                    raise ValueError('backup_external_scene_cloud_assets')
                saved=root/path.resolve().relative_to(original_root)/member
                if not saved.is_file() or digest(saved)!=expected:raise ValueError('backup_scene_cloud_assets_changed')
    ifc_config=root/'setup/scene-ifc.json'
    if ifc_config.exists():
        from packages.data.ifc_workspace import IfcConfig,read_json,sha,validate_catalog,validate_source,load_mesh
        parsed=IfcConfig.model_validate_json(ifc_config.read_bytes())
        if len({b.space_id for b in parsed.bindings})!=len(parsed.bindings):raise ValueError('backup_duplicate_ifc_binding')
        for binding in parsed.bindings:
            path=Path(binding.root)
            if not path.is_absolute() or not path.resolve().is_relative_to(original_root/'runtime/preview-inputs'):
                raise ValueError('backup_external_ifc_assets')
            saved=root/path.resolve().relative_to(original_root)
            raw,doc=read_json(saved/'ifc.json',8*1024*1024)
            if sha(raw)!=binding.catalog_sha256:raise ValueError('backup_ifc_assets_changed')
            validate_catalog(doc)
            validate_source(saved,doc)
            for product in doc['products']:
                if product['geometry_status']=='extracted':load_mesh(saved,product)
    consumer=root/'setup/consumer-access.json'
    if consumer.exists():
        from packages.service.online_consumer import ConsumerConfig
        parsed=ConsumerConfig.model_validate_json(consumer.read_bytes())
        if len({(g.caller,g.space_id) for g in parsed.grants})!=len(parsed.grants):raise ValueError('backup_duplicate_consumer_grant')
    SpacePolicyStore(root/'policy').load()
    if sources.get('profile')!='cospace.preview-sources/0.1':raise ValueError('backup_source_profile')
    for source in sources['sources']:
        if source['enabled']:
            for key in ('snapshot','tracking'):
                if source.get(key):
                    path=(Path.cwd()/source[key]).resolve()
                    if not path.is_relative_to(original_root) or not (root/path.relative_to(original_root)).exists():
                        raise ValueError('backup_external_source_use_uploaded_inputs')
    for p in (root/'runtime/preview-inputs').glob('input-*.json'):
        record=json.loads(p.read_bytes())
        for key in ('snapshot','tracking'):
            if record.get(key):
                source=Path(record[key])
                if (not source.is_absolute() or not source.resolve().is_relative_to(original_root/'runtime')
                        or not (root/source.resolve().relative_to(original_root)).exists()):
                    raise ValueError('backup_external_or_missing_input_use_uploaded_inputs')
    from packages.data.scene_attachments import stored_records
    try:
        list(stored_records(root/'runtime/preview-inputs', verify=True))
    except (OSError,ValueError,TypeError,KeyError):
        raise ValueError('backup_scene_attachments_invalid') from None
    for pattern in ('*/job.json','*/views/*/task.json'):
        for p in (root/'runtime/preview-builds').glob(pattern):
            if json.loads(p.read_bytes()).get('state') in ('queued','running'):
                raise ValueError('backup_unfinished_build_restart_and_resolve_first')
    for p in (root/'runtime/preview-inputs/scene-compositions').glob('*/job.json'):
        if json.loads(p.read_bytes()).get('state') in ('queued','running'):
            raise ValueError('backup_unfinished_composition_restart_and_resolve_first')
    for p in root.rglob('*.sqlite3'):
        with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('backup_database_integrity')


def backup(root,output,*,actor,reason):
    original=Path(root)
    if original.is_symlink() or original.is_junction():raise ValueError('backup_links_not_supported')
    root=original.resolve();output=Path(output).absolute()
    if output.exists() or not output.parent.is_dir() or output.resolve().is_relative_to(root):
        raise ValueError('backup_exclusive_output_outside_root_required')
    if not isinstance(actor,str) or not actor.strip() or len(actor)>200 or not isinstance(reason,str) or not reason.strip() or len(reason)>500:
        raise ValueError('backup_actor_and_reason_required')
    temporary=output.parent/('.'+output.name+'.'+uuid.uuid4().hex+'.tmp')
    with service_guard(root/'runtime',require_existing=True),mutation_guard(root/'runtime'),mutation_guard(root/'policy'):
        before=tree(root);validate_runtime(root)
        manifest={'profile':PROFILE,'root':str(root),'created_at':datetime.now(timezone.utc).isoformat(),
                  'actor':actor.strip(),'reason':reason.strip(),'restore_mode':'same_machine_original_path',
                  'sessions_included':False,'files':before}
        try:
            with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,sort_keys=True))
                for name in before:archive.write(root/name,name)
            if before!=tree(root):raise ValueError('backup_source_changed')
            # The content is checked before the final name becomes visible.
            checked=verify(temporary,digest(temporary))
            if output.exists():raise ValueError('backup_output_exists')
            # Hard-link publication is exclusive, unlike overwrite-capable replace.
            import os
            os.link(temporary,output)
            return {'status':'passed','archive':str(output),'sha256':checked['sha256'],
                    'files':len(before),'bytes':sum(v['bytes'] for v in before.values()),'manifest':manifest}
        finally:
            if temporary.exists():temporary.unlink()


def verify(archive_path,expected_sha256):
    if not isinstance(expected_sha256,str) or not re.fullmatch('[a-f0-9]{64}',expected_sha256):
        raise ValueError('backup_external_sha256_required')
    archive_path=Path(archive_path)
    if digest(archive_path)!=expected_sha256:raise ValueError('backup_archive_digest_mismatch')
    with zipfile.ZipFile(archive_path) as archive:
        entries=archive.infolist();names=[v.filename for v in entries]
        if len(names)!=len(set(n.casefold() for n in names)) or len(names)>MAX_FILES+1:
            raise ValueError('backup_duplicate_or_excess_members')
        if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>32_000_000:
            raise ValueError('backup_manifest_missing_or_large')
        manifest=json.loads(archive.read('manifest.json'))
        if (manifest.get('profile')!=PROFILE or manifest.get('restore_mode')!='same_machine_original_path'
                or manifest.get('sessions_included') is not False or not Path(manifest.get('root','')).is_absolute()):
            raise ValueError('backup_manifest_profile')
        files=manifest.get('files')
        if not isinstance(files,dict):raise ValueError('backup_member_set_mismatch')
        for name in files:safe_name(name);business_member(name)
        if set(names)!={'manifest.json',*files}:raise ValueError('backup_member_set_mismatch')
        if not {'setup/sources.json','setup/workspace-scenes.json','policy/space-policy.sqlite3'}<=files.keys():
            raise ValueError('backup_configuration_missing')
        total=0
        for name,value in files.items():
            safe_name(name);info=archive.getinfo(name)
            if (not isinstance(value,dict) or type(value.get('bytes')) is not int or value['bytes']<0
                    or not re.fullmatch('[a-f0-9]{64}',str(value.get('sha256','')))
                    or info.file_size!=value['bytes'] or info.is_dir()
                    or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1):
                raise ValueError('backup_member_metadata')
            total+=value['bytes']
            if total>MAX_BYTES:raise ValueError('backup_budget')
            with archive.open(name) as stream:
                actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=value['sha256']:raise ValueError('backup_member_digest_mismatch')
    return {'status':'passed','sha256':expected_sha256,'files':len(files),'bytes':total,'manifest':manifest}


def restore(archive_path,root,expected_sha256):
    archive_path=Path(archive_path).resolve();root=Path(root).absolute()
    if root.exists() or root.is_symlink() or not root.parent.is_dir():raise ValueError('backup_restore_requires_absent_target')
    checked=verify(archive_path,expected_sha256)
    if root.resolve()!=Path(checked['manifest']['root']).resolve():raise ValueError('backup_restore_original_path_required')
    stage=root.parent/('.'+root.name+'.restore-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        for name in ROOTS:(stage/name).mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            # Archive path is reopened; recheck its digest before extracting.
            if digest(archive_path)!=expected_sha256:raise ValueError('backup_archive_changed')
            for name in checked['manifest']['files']:
                target=stage/name
                target.parent.mkdir(parents=True,exist_ok=True)
                remaining=checked['manifest']['files'][name]['bytes']
                with archive.open(name) as source,target.open('xb') as output:
                    while remaining:
                        chunk=source.read(min(remaining,1024*1024))
                        if not chunk:raise ValueError('backup_member_size_changed')
                        output.write(chunk);remaining-=len(chunk)
                    if source.read(1):raise ValueError('backup_member_size_changed')
        if tree(stage)!=checked['manifest']['files']:raise ValueError('backup_restored_digest_mismatch')
        validate_runtime(stage,root)
        # Do not rebase absolute input paths. They become valid at the final root.
        if root.exists():raise ValueError('backup_restore_requires_absent_target')
        stage.rename(root)
        return {k:v for k,v in checked.items() if k!='manifest'}|{'root':str(root),'restore_mode':'same_machine_original_path','login_required':True}
    finally:
        # Only this call's freshly created staging directory may be removed.
        if stage.exists():
            if stage.resolve().parent!=root.parent.resolve() or not stage.name.startswith('.'+root.name+'.restore-'):
                raise ValueError('backup_cleanup_target_mismatch')
            shutil.rmtree(stage)
