"""Controlled synthetic input import; never adopts or activates a release."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from jsonschema import Draft202012Validator
from pathlib import Path

from packages.service.sample import inspect_package, read_json


class ImportError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_request(request):
    schema = read_json((Path(__file__).resolve().parents[2] / 'contracts/schemas/import-request-v0.1.schema.json').read_bytes())
    errors = sorted(Draft202012Validator(schema).iter_errors(request), key=lambda e: str(e.path))
    if errors:
        raise ImportError('invalid_request', 'invalid import request at /' + '/'.join(map(str, errors[0].path)))
    if any(not request[field].strip() for field in ('source_description', 'idempotency_key')):
        raise ImportError('invalid_request', 'description and idempotency key must not be blank')


class ImportManager:
    def __init__(self, store, files):
        self.store, self.files = store, files

    def ingest(self, source, request, actor):
        validate_request(request)
        if not actor.strip():
            raise ImportError('invalid_request', 'actor declaration required')
        request_hash = sha(canonical(request))
        import_id = 'import-' + uuid.uuid4().hex
        record, claimed = self.store.claim(import_id, request, request_hash, actor, now())
        if not claimed:
            return record
        stage = 'copy'
        try:
            staged = self.files.stage(import_id, source, request['expected_manifest_sha256'])
            self.store.state(import_id, 'validating')
            stage = 'validation'
            report, snapshot = inspect_package(staged)
            if report['profile'] != 'cospace.synthetic-bundle/0.2' or report['scene_id'] != request['scene_id']:
                raise ImportError('input_mismatch', 'scene/profile does not match requested synthetic input')
            verified_at = now()
            manifest = read_json((staged / 'package.json').read_bytes())
            dataset_id = 'dataset-' + uuid.uuid4().hex
            members = [{'path': 'package.json', 'bytes': (staged / 'package.json').stat().st_size,
                        'sha256': request['expected_manifest_sha256'], 'media_type': 'application/json', 'role': 'source_manifest'}]
            members += [{**item, 'role': snapshot['inspection']['roles'].get(item['path'], 'unclassified')}
                        for item in manifest['data']['files']]
            dataset = {'schema_version': 'cospace.dataset/0.1', 'dataset_id': dataset_id, 'import_id': import_id,
                       'scene_id': request['scene_id'], 'data_kind': 'synthetic', 'purpose': request['purpose'],
                       'source_description': request['source_description'], 'usage_conditions': request['usage_conditions'],
                       'source_manifest_sha256': request['expected_manifest_sha256'], 'members': members,
                       'verified_at': verified_at, 'quality': 'not_field_validated', 'algorithm_ready': False}
            stage = 'seal'
            schema = read_json((Path(__file__).resolve().parents[2] / 'contracts/schemas/dataset-v0.1.schema.json').read_bytes())
            Draft202012Validator(schema).validate(dataset)
            self.files.seal(import_id, dataset)
            stage = 'commit'
            self.store.commit(import_id, dataset, sha(canonical(dataset)), now())
            return self.store.get_import(import_id)
        except (OSError, ValueError) as error:
            code = error.code if isinstance(error, ImportError) else ('storage_error' if isinstance(error, OSError) else 'validation_error')
            # Paths and original exception text can include host secrets; keep a bounded diagnostic.
            self.store.reject(import_id, {'stage': stage, 'code': code, 'message': 'input import failed; no dataset committed'})
            raise ImportError(code, f'import {import_id} failed at {stage}; inspect import record') from error
        # Database failures intentionally leave a nonterminal import and sealed orphan,
        # never a committed dataset. Recovery is explicit, not implicit success.

    def dataset(self, dataset_id):
        record = self.store.get_dataset(dataset_id)
        self.files.verify(record['manifest'])
        return record
