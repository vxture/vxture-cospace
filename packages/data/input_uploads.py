"""Bounded scene-owned ZIP intake, immutable sources and repeat-safe registration."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
import stat
import tempfile
import zipfile
from packages.data.preview_inputs import inspect
from packages.data.preview_registration import PreviewRegistration
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_scope import scope,owned

MAX_UPLOAD=128*1024*1024
MAX_EXPANDED=192*1024*1024
MAX_FILES=1104
MAX_SCENE_BYTES=512*1024*1024
FORMATS=('nyu_rgbd_with_existing_poses','ros1_lidar_single_frame','ros1_lidar_multiframe_icp','ply_pointcloud')


class UploadRejected(ValueError):pass


def capabilities():
    from packages.data.input_routes import routes
    return {'profile':'cospace.input-upload/0.1','container':'zip','formats':list(FORMATS),
            'routes':routes(FORMATS),
            'max_upload_bytes':MAX_UPLOAD,'max_expanded_bytes':MAX_EXPANDED,'max_files':MAX_FILES,
            'max_scene_stored_bytes':MAX_SCENE_BYTES,'auto_build':False,
            'input_preview':{'profile':'cospace.input-preview/0.1','formats':['ply_pointcloud'],'max_points':10_000},
            'rgbd_input_preview':{'profile':'cospace.rgbd-input-preview/0.1','formats':['nyu_rgbd_with_existing_poses'],
                'max_frames':500,'max_index_bytes':1024*1024,'max_response_bytes':2*1024*1024,'display_size':[320,240]},
            'build_process':{'profile':'cospace.build-process/0.1','formats':['nyu_rgbd_with_existing_poses'],
                'max_frames':500,'max_points':10000,'max_response_bytes':2*1024*1024},
            'lidar_build_process':{'profile':'cospace.lidar-build-process/0.1','formats':['ros1_lidar_multiframe_icp'],
                'max_frames':20,'max_points':10000,'max_response_bytes':2*1024*1024},
            'pointcloud_preparation':{'profile':'cospace.pointcloud-preparation/0.1','format':'ply_pointcloud',
                'source_profile':'cospace.pointcloud-source/0.1','max_cloud_bytes':32*1024*1024,'max_points':1_000_000}}


def metadata(space_id,label):
    if not isinstance(space_id,str) or not re.fullmatch(r'space-[a-f0-9]{16}',space_id):
        raise UploadRejected('upload_explicit_scene_required')
    if not isinstance(label,str) or not 1<=len(label.strip())<=100:
        raise UploadRejected('invalid_input_label')


def json_file(path):
    if path.stat().st_size>2*1024*1024:raise UploadRejected('upload_manifest_budget')
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise UploadRejected('upload_duplicate_json_key')
            result[k]=v
        return result
    return json.loads(path.read_bytes(),object_pairs_hook=unique)


def unpack(bundle,destination):
    """Never interpret host paths or extract ZIP links; validate before copying bytes."""
    try:
        with zipfile.ZipFile(bundle) as archive:
            infos=archive.infolist()
            if not 1<=len(infos)<=MAX_FILES:raise UploadRejected('upload_member_budget')
            seen=set();total=0
            for member in infos:
                name=member.filename;path=PurePosixPath(name)
                if (not name or '\\' in name or ':' in name or name.startswith('/') or name.endswith('/')
                        or any(p in ('','.', '..') for p in name.split('/')) or path.as_posix()!=name
                        or len(name)>200 or name.casefold() in seen or member.flag_bits&1
                        or stat.S_ISLNK(member.external_attr>>16)
                        or stat.S_IFMT(member.external_attr>>16) not in (0,stat.S_IFREG)):
                    raise UploadRejected('upload_unsafe_member')
                if name not in ('input.json','tracking.json','snapshot/report.json','snapshot/sample.json','snapshot/sample.bag','snapshot/pointcloud.json','snapshot/cloud.ply','snapshot/source.json','snapshot/composition.json') and not re.fullmatch(r'snapshot/raw/[A-Za-z0-9_.-]+\.(pgm|ppm)',name):
                    raise UploadRejected('upload_unexpected_member')
                if member.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise UploadRejected('upload_compression_unsupported')
                seen.add(name.casefold());total+=member.file_size
                if member.file_size<0 or total>MAX_EXPANDED:raise UploadRejected('upload_expanded_budget')
            for member in infos:
                target=destination/member.filename;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(member) as src,target.open('xb') as dst:
                    count=0
                    while chunk:=src.read(256*1024):
                        count+=len(chunk)
                        if count>member.file_size:raise UploadRejected('upload_expanded_budget')
                        dst.write(chunk)
                    if count!=member.file_size:raise UploadRejected('upload_member_integrity')
        doc=json_file(destination/'input.json')
        if not isinstance(doc,dict) or doc.get('profile')!='cospace.input-upload/0.1' or set(doc)!={'profile','format'} or doc.get('format') not in FORMATS:
            raise UploadRejected('upload_format_unsupported')
        format=doc['format']
        if format==FORMATS[0]:
            report=json_file(destination/'snapshot/report.json');json_file(destination/'tracking.json')
            expected={'input.json','tracking.json','snapshot/report.json'}|{'snapshot/raw/'+n for n in report['members']}
        elif format=='ply_pointcloud':
            expected={'input.json','snapshot/pointcloud.json','snapshot/cloud.ply'}
            pointcloud=json_file(destination/'snapshot/pointcloud.json')
            if pointcloud.get('source_receipt_path')=='source.json':expected.add('snapshot/source.json')
            if pointcloud.get('composition_path')=='composition.json':expected.add('snapshot/composition.json')
        else:expected={'input.json','snapshot/sample.json','snapshot/sample.bag'}
        if {m.filename for m in infos}!=expected:raise UploadRejected('upload_members_mismatch')
        return format,total
    except UploadRejected:raise
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,RuntimeError,NotImplementedError) as exc:
        raise UploadRejected('upload_package_invalid') from exc


class InputUploads:
    def __init__(self,catalog):self.catalog=catalog

    def register(self,bundle,space_id,label,actor):
        metadata(space_id,label);ownership=scope(self.catalog.directory,space_id)
        bundle=Path(bundle)
        if not 0<bundle.stat().st_size<=MAX_UPLOAD:raise UploadRejected('upload_size_budget')
        with bundle.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        staging=self.catalog.root/'.upload-staging';staging.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=staging,prefix='unpack-') as temp:
            expanded=Path(temp)/'content';expanded.mkdir();format,total=unpack(bundle,expanded)
            tracking=expanded/'tracking.json' if format==FORMATS[0] else None
            try:checked=inspect(expanded/'snapshot',tracking,format)
            except (OSError,ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:raise UploadRejected('upload_content_validation_failed') from exc
            with mutation_guard(self.catalog.root.parent):
                # A copied catalog can retain sealed source paths outside this
                # upload root. Package identity belongs to the scene, not a path.
                matches=[item for item in self.catalog.list() if owned(item)==ownership
                         and item.get('registration_ref',{}).get('method')=='uploaded_package'
                         and item.get('registration_ref',{}).get('package_sha256')==sha]
                if len(matches)>1:raise UploadRejected('upload_existing_records_ambiguous')
                if matches:
                    try:
                        self.catalog.resolve(matches[0]['id'])
                        original=self.catalog.read_original(matches[0]['id'])
                        if original['format']!=format or any(original.get(k)!=v for k,v in checked.items()):
                            raise ValueError('upload_existing_evidence_mismatch')
                    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
                        raise UploadRejected('upload_existing_evidence_invalid') from exc
                    return {'created':False,'input':matches[0],
                            'upload':{'format':format,'sha256':sha,'bytes':bundle.stat().st_size,'expanded_bytes':total}}
                target=self.catalog.root/'uploads'/space_id/sha
                if not target.exists():
                    scene=target.parent
                    stored=sum(p.stat().st_size for p in scene.rglob('*') if p.is_file()) if scene.exists() else 0
                    if stored+total>MAX_SCENE_BYTES:raise UploadRejected('upload_scene_storage_budget')
                    scene.mkdir(parents=True,exist_ok=True);expanded.rename(target)
                source={'uploaded':{'label':label,'format':format,'snapshot':target/'snapshot',
                                    'tracking':target/'tracking.json' if tracking else None}}
                registration=PreviewRegistration(self.catalog,source,{'method':'uploaded_package',
                    'package_sha256':sha,'actor':actor,'profile':'cospace.input-upload/0.1'})
                result=registration.register('uploaded',label,space_id)
        return result|{'upload':{'format':format,'sha256':sha,'bytes':bundle.stat().st_size,'expanded_bytes':total}}
