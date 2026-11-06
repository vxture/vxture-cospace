"""Strict project-relative source configuration, loaded once at service startup."""
import json
import hashlib
from pathlib import Path
import re
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from packages.data.preview_inputs import inspect


class Source(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    label: str = Field(min_length=1, max_length=100)
    enabled: StrictBool
    format: str
    snapshot: str
    tracking: str|None=None


class Config(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: str
    sources: list[Source] = Field(max_length=100)


def project_path(root, value):
    # Backslashes accepted for Windows-authored project configs, never absolute paths.
    if not value.strip() or re.match(r'^(?:[A-Za-z]:|[/\\])', value):
        raise ValueError('source_path_must_be_project_relative')
    path = (root / value.replace('\\', '/')).resolve()
    if not path.is_relative_to(root): raise ValueError('source_path_outside_project')
    return path


def load_sources(path, project_root, full_check=False):
    root = Path(project_root).resolve()
    path = Path(path)
    if path.stat().st_size > 256_000: raise ValueError('source_config_too_large')
    raw = path.read_bytes()
    config = Config.model_validate(json.loads(raw))
    if config.profile != 'cospace.preview-sources/0.1': raise ValueError('unsupported_source_config')
    allowed = {}; states = []; seen = set()
    for item in config.sources:
        if item.id in seen: raise ValueError('duplicate_source_id')
        seen.add(item.id)
        if not item.label.strip(): raise ValueError('invalid_source_label')
        if item.format not in ('nyu_rgbd_with_existing_poses','ros1_lidar_single_frame','ros1_lidar_multiframe_icp','ply_pointcloud'): raise ValueError('unsupported_source_adapter')
        if item.format!='nyu_rgbd_with_existing_poses' and item.tracking is not None:raise ValueError('lidar_tracking_not_supported')
        if item.format=='nyu_rgbd_with_existing_poses' and item.tracking is None:raise ValueError('tracking_required')
        snapshot = project_path(root, item.snapshot); tracking = project_path(root, item.tracking) if item.tracking is not None else None
        status = 'disabled'
        if item.enabled:
            required=([snapshot/'pointcloud.json',snapshot/'cloud.ply'] if item.format=='ply_pointcloud' else
                [snapshot/'sample.json',snapshot/'sample.bag'] if item.format in ('ros1_lidar_single_frame','ros1_lidar_multiframe_icp') else [snapshot/'report.json',tracking])
            if not all(p.is_file() for p in required):
                raise ValueError(f'enabled_source_missing_files:{item.id}')
            if full_check: inspect(snapshot, tracking,item.format)
            allowed[item.id] = {'label': item.label, 'snapshot': snapshot, 'tracking': tracking,'format':item.format}
            status = 'validated' if full_check else 'configured'
        states.append({'id': item.id, 'label': item.label, 'enabled': item.enabled, 'status': status})
    report = {'profile': config.profile, 'sha256': hashlib.sha256(raw).hexdigest(), 'loaded_at_startup': True,
              'reload_policy': 'restart_required', 'full_file_check': full_check,
              'enabled_count': len(allowed), 'disabled_count': len(states)-len(allowed), 'sources': states}
    return allowed, report
