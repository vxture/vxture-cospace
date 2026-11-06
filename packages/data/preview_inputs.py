"""Local engineering catalog for sealed NYU RGB-D plus existing pose inputs."""
import json
from pathlib import Path
import re
import uuid
import numpy as np
from packages.lifecycle.preview_scope import scope
from packages.construction.preview_model import digest
from packages.data.nyu_rgbd import read_pnm
from packages.lifecycle.preview_control_lock import serialized


def inspect(snapshot, tracking=None, format='nyu_rgbd_with_existing_poses'):
    if format=='ply_pointcloud':
        if tracking is not None:raise ValueError('pointcloud_tracking_not_supported')
        from packages.data.preview_pointcloud import read_cloud
        return read_cloud(snapshot)[0]
    if format in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp'):
        if tracking is not None:raise ValueError('lidar_tracking_not_supported')
        from packages.data.preview_lidar import read_specimen
        return read_specimen(snapshot,sequence=format=='ros1_lidar_multiframe_icp')[0]
    if format!='nyu_rgbd_with_existing_poses':raise ValueError('unsupported_input_format')
    if tracking is None:raise ValueError('tracking_required')
    snapshot=Path(snapshot).resolve(); tracking=Path(tracking).resolve()
    report=snapshot/'report.json'
    source=json.loads(report.read_bytes()); poses=json.loads(tracking.read_bytes())
    if source.get('schema_version')!='cospace.nyu-short-scene/0.1':
        raise ValueError('unsupported_input_format')
    if poses.get('source_report_sha256')!=digest(report): raise ValueError('source_mismatch')
    pairs=[p for p in source['pairs'] if p['accepted']]
    matrices=np.asarray(poses['prefix_T_anchor_camera'],dtype=float)
    if (not 1<=len(pairs)<=500 or matrices.ndim!=3 or matrices.shape[1:]!=(4,4)
            or not 1<=len(matrices)<=len(pairs) or not np.isfinite(matrices).all()
            or not np.allclose(matrices[:,3,:],[0,0,0,1])):
        raise ValueError('invalid_input_poses')
    members=set()
    for pair in pairs:
        for role,suffix in [('depth','.pgm'),('rgb','.ppm')]:
            name=pair[role]
            if not isinstance(name,str) or '/' in name or '\\' in name or Path(name).suffix!=suffix:
                raise ValueError('invalid_input_member')
            path=snapshot/'raw'/name
            if not path.resolve().is_relative_to((snapshot/'raw').resolve()): raise ValueError('invalid_input_member')
            expected=source['members'][name]
            if path.stat().st_size>2_000_000: raise ValueError('input_member_too_large')
            if path.stat().st_size!=expected['bytes'] or digest(path)!=expected['sha256']:
                raise ValueError('input_integrity')
            read_pnm(path.read_bytes(),role=='depth')
            members.add(name)
    return {'snapshot_sha256':digest(report),'tracking_sha256':digest(tracking),
            'input_frames':len(pairs),'used_frames':len(matrices),'verified_image_members':len(members)}


class PreviewInputs:
    def __init__(self,root,directory=None):
        self.directory=directory
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)

    @serialized(lambda self:self.root.parent)
    def register(self,label,snapshot,tracking=None,space_id=None,format='nyu_rgbd_with_existing_poses',registration_ref=None):
        ownership=scope(self.directory,space_id)
        if not isinstance(label,str) or not 1<=len(label.strip())<=100: raise ValueError('invalid_input_label')
        checked=inspect(snapshot,tracking,format)
        record={'profile':'cospace.preview-input/0.1','id':'input-'+uuid.uuid4().hex[:16],
                'label':label.strip(),'format':format,
                'snapshot':str(Path(snapshot).resolve()),**checked,**ownership}
        if tracking is not None:record['tracking']=str(Path(tracking).resolve())
        if registration_ref is not None:record['registration_ref']=dict(registration_ref)
        # Exclusive creation; records are immutable, changed data requires a new registration.
        pending=self.root/(record['id']+'.pending')
        with pending.open('x',encoding='utf-8') as stream:
            json.dump(record,stream,indent=2,ensure_ascii=False)
        pending.rename(self.root/(record['id']+'.json'))
        return record

    def read_original(self,identity):
        if not re.fullmatch(r'input-[a-f0-9]{16}',identity): raise ValueError('input_not_found')
        path=self.root/(identity+'.json')
        if not path.is_file(): raise ValueError('input_not_found')
        record=json.loads(path.read_bytes())
        if record['id']!=identity or record['profile']!='cospace.preview-input/0.1': raise ValueError('invalid_input_record')
        return record

    def read(self,identity):
        from packages.data.input_coordinates import InputCoordinates
        original=self.read_original(identity)
        return InputCoordinates(self).effective(original)

    def resolve(self,identity):
        record=self.read(identity)
        checked=inspect(record['snapshot'],record.get('tracking'),record['format'])
        if record.get('coordinate_revision'):
            from packages.data.input_coordinates import interpret
            checked=interpret(checked,record)
        if any(record[k]!=v for k,v in checked.items()): raise ValueError('registered_input_changed')
        return record

    def list(self):
        return [{k:v for k,v in self.read(p.stem).items() if k not in ('snapshot','tracking')}
                for p in sorted(self.root.glob('input-*.json'))]
