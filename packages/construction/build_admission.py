"""Fixed admission receipt, distinct from saved preflight and worker completion."""
from datetime import datetime, timezone
import hashlib
import json


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True).encode()).hexdigest()


def receipt(job_id, binding, preflight_sequence=None):
    value = {'profile': 'cospace.build-admission/0.1', 'job_id': job_id,
             'checked_at': datetime.now(timezone.utc).isoformat(),
             'method': 'preview-inputs.resolve/ply-pointcloud/0.1',
             'input_id': binding['id'], 'registration_sha256': checksum(binding),
             'saved_preflight_sequence': preflight_sequence,
             'source_files_checked': True, 'status': 'passed'}
    return value | {'sha256': checksum(value)}


def validate(value, binding):
    if (not isinstance(value, dict) or not isinstance(binding, dict)
            or value.get('profile') != 'cospace.build-admission/0.1'
            or value.get('sha256') != checksum({k: v for k, v in value.items() if k != 'sha256'})
            or value.get('registration_sha256') != checksum(binding)
            or value.get('input_id') != binding.get('id')
            or binding.get('format') != 'ply_pointcloud'
            or value.get('method') != 'preview-inputs.resolve/ply-pointcloud/0.1'
            or value.get('source_files_checked') is not True or value.get('status') != 'passed'):
        raise ValueError('build_admission_invalid')


def match_source(job, source):
    value = job.get('build_admission')
    if value != source.get('build_admission'):
        raise ValueError('build_admission_binding_mismatch')
    if value is not None:
        validate(value, job.get('input_binding'))
