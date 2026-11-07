"""Scene-owned reference files. Opaque originals, never construction inputs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_scope import scope

MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 1000
EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.csv', '.txt', '.ifc')
RECORD = 'record.json'
PAYLOAD = 'original.bin'


class AttachmentRejected(ValueError):
    pass


class Attachment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    profile: Literal['cospace.scene-attachment/0.1']
    id: str = Field(pattern=r'^attachment-[a-f0-9]{16}$')
    space_id: str = Field(pattern=r'^space-[a-f0-9]{16}$')
    project_id: str = Field(pattern=r'^project-[a-f0-9]{16}$')
    name: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: int = Field(gt=0, le=MAX_BYTES)
    created_at: str
    actor: str = Field(min_length=1, max_length=200)
    processing: Literal['stored_original']


def metadata(space_id, name):
    if not isinstance(space_id, str) or not re.fullmatch(r'space-[a-f0-9]{16}', space_id):
        raise AttachmentRejected('attachment_scene_required')
    if (not isinstance(name, str) or not 1 <= len(name) <= 160 or name != name.strip()
            or any(c in name for c in '/\\:<>"|?*') or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or name.endswith(('.', ' '))):
        raise AttachmentRejected('attachment_name_invalid')
    if Path(name).suffix.lower() not in EXTENSIONS:
        raise AttachmentRejected('attachment_format_unsupported')


def checked_path(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise AttachmentRejected('attachment_path_invalid')
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise AttachmentRejected('attachment_path_invalid')
        if parent == root:
            break
    return path


def _read_record(root, folder, *, verify=False):
    folder = checked_path(root, folder)
    path = checked_path(root, folder / RECORD)
    try:
        with path.open('rb') as stream:
            raw = stream.read(8193)
    except OSError as exc:
        raise AttachmentRejected('attachment_record_invalid') from exc
    if len(raw) > 8192:
        raise AttachmentRejected('attachment_record_invalid')
    record = Attachment.model_validate_json(raw).model_dump()
    metadata(record['space_id'], record['name'])
    if (folder.name != record['id'] or folder.parent.name != record['space_id']
            or record['id'] != 'attachment-' + record['sha256'][:16]
            or datetime.fromisoformat(record['created_at']).tzinfo is None):
        raise AttachmentRejected('attachment_record_invalid')
    try:
        members = {p.name for p in folder.iterdir()}
    except OSError as exc:
        raise AttachmentRejected('attachment_record_invalid') from exc
    if members != {RECORD, PAYLOAD}:
        raise AttachmentRejected('attachment_record_invalid')
    payload = checked_path(root, folder / PAYLOAD)
    if payload.stat().st_size != record['bytes']:
        raise AttachmentRejected('attachment_content_changed')
    if verify:
        with payload.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                raise AttachmentRejected('attachment_content_changed')
    return record


def read_record(root, folder, *, verify=False):
    try:
        return _read_record(root, folder, verify=verify)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise AttachmentRejected('attachment_evidence_unavailable') from exc


def stored_records(inputs_root, *, verify=False):
    root = Path(inputs_root) / 'scene-attachments'
    if not root.exists():
        return
    checked_path(inputs_root, root)
    for scene in sorted(root.iterdir()):
        if not re.fullmatch(r'space-[a-f0-9]{16}', scene.name) or not checked_path(root, scene).is_dir():
            raise AttachmentRejected('attachment_record_invalid')
        for folder in sorted(scene.iterdir()):
            yield folder, read_record(root, folder, verify=verify)


class SceneAttachments:
    def __init__(self, inputs):
        self.inputs = inputs
        self.root = inputs.root / 'scene-attachments'

    def list(self, space_id):
        ownership = scope(self.inputs.directory, space_id)
        result = []
        scene = checked_path(self.inputs.root, self.root / space_id)
        if scene.exists():
            for folder in sorted(scene.iterdir()):
                record = read_record(self.root, folder)
                if any(record[k] != v for k, v in ownership.items()):
                    raise AttachmentRejected('attachment_scene_mismatch')
                result.append(record)
                if len(result) > MAX_FILES:
                    raise AttachmentRejected('attachment_file_budget')
        return sorted(result, key=lambda r: (r['created_at'], r['id']), reverse=True)

    def register(self, source, space_id, name, actor):
        metadata(space_id, name)
        ownership = scope(self.inputs.directory, space_id)
        source = Path(source)
        try:
            with source.open('rb') as stream:
                raw = stream.read(MAX_BYTES + 1)
        except OSError as exc:
            raise AttachmentRejected('attachment_source_unavailable') from exc
        if not 0 < len(raw) <= MAX_BYTES:
            raise AttachmentRejected('attachment_size_budget')
        digest = hashlib.sha256(raw).hexdigest()
        identity = 'attachment-' + digest[:16]
        with mutation_guard(self.inputs.root.parent):
            existing = next((r for r in self.list(space_id) if r['id'] == identity), None)
            if existing:
                if existing['sha256'] != digest:
                    raise AttachmentRejected('attachment_identity_collision')
                read_record(self.root, self.root / space_id / identity, verify=True)
                return {'created': False, 'attachment': existing}
            if len(self.list(space_id)) >= MAX_FILES:
                raise AttachmentRejected('attachment_file_budget')
            record = Attachment.model_validate(dict(profile='cospace.scene-attachment/0.1', id=identity,
                **ownership, name=name, sha256=digest, bytes=len(raw), actor=actor,
                created_at=datetime.now(timezone.utc).isoformat(), processing='stored_original')).model_dump()
            # Publish the complete folder atomically; interrupted receives remain temporary.
            staging = self.inputs.root / '.upload-staging'
            staging.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=staging, prefix='reference-') as temp:
                folder = Path(temp) / identity
                folder.mkdir()
                (folder / PAYLOAD).write_bytes(raw)
                (folder / RECORD).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                destination = checked_path(self.inputs.root, self.root / space_id / identity)
                destination.parent.mkdir(parents=True, exist_ok=True)
                folder.rename(destination)
            return {'created': True, 'attachment': record}

    def download(self, space_id, identity):
        scope(self.inputs.directory, space_id)
        if not re.fullmatch(r'attachment-[a-f0-9]{16}', identity):
            raise AttachmentRejected('attachment_not_found')
        folder = checked_path(self.inputs.root, self.root / space_id / identity)
        record = read_record(self.root, folder)
        if record['project_id'] != scope(self.inputs.directory, space_id)['project_id']:
            raise AttachmentRejected('attachment_scene_mismatch')
        with (folder / PAYLOAD).open('rb') as stream:
            raw = stream.read(record['bytes'] + 1)
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise AttachmentRejected('attachment_content_changed')
        return record, raw
