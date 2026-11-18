"""Scene IFC task/version state. Authorization is the caller's responsibility."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from uuid import uuid4
from typing import Literal
from zipfile import BadZipFile

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.data.ifc_structure_read import validate_structure
from packages.data.ifc_workspace import IfcBinding, load_mesh, read_json, validate_catalog, validate_source
from packages.data.scene_attachments import checked_path, read_record
from packages.infrastructure.ifc_parser_channel import PARSE_TIMEOUT
from packages.lifecycle.preview_control_lock import mutation_guard
from packages.lifecycle.preview_scope import scope

PARSER = 'ifcopenshell-0.9.0.post1-structure-1'
TIMEOUT_SECONDS = PARSE_TIMEOUT
LEASE_SECONDS = TIMEOUT_SECONDS + 120
MAX_TASKS = 1000
MAX_SWITCHES = 2000
MAX_PENDING = 8


class StoredModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class StoredTask(StoredModel):
    id: str = Field(pattern='^[a-f0-9]{64}$')
    attachment_id: str = Field(pattern='^attachment-[a-f0-9]{16}$')
    source_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    name: str = Field(min_length=1, max_length=160)
    actor: str = Field(min_length=1, max_length=200)
    parser: str = Field(min_length=1, max_length=100)
    state: Literal['queued', 'running', 'ready', 'failed']
    requested_at: str = Field(max_length=40)
    attempt: str = Field(pattern='^[a-f0-9]{32}$')
    started_at: str | None = Field(default=None, max_length=40)
    lease_until: float | None = None
    catalog_sha256: str | None = Field(default=None, pattern='^[a-f0-9]{64}$')
    finished_at: str | None = Field(default=None, max_length=40)
    error: Literal['parse_rejected', 'parse_timeout', 'parser_unavailable', 'worker_interrupted'] | None = None

    @model_validator(mode='after')
    def binding(self):
        if (self.id != hashlib.sha256(f'{self.source_sha256}:{self.parser}'.encode()).hexdigest()
                or self.attachment_id != 'attachment-' + self.source_sha256[:16]
                or (self.lease_until is not None) != (self.state == 'running')
                or (self.catalog_sha256 is not None) != (self.state == 'ready')
                or (self.error is not None) != (self.state == 'failed')):
            raise ValueError('ifc_task_binding_invalid')
        return self


class StoredSwitch(StoredModel):
    from_task: str | None = Field(alias='from', pattern='^[a-f0-9]{64}$')
    to: str = Field(pattern='^[a-f0-9]{64}$')
    actor: str = Field(min_length=1, max_length=200)
    at: str = Field(max_length=40)


class StoredVersions(StoredModel):
    revision: int = Field(ge=0, le=MAX_SWITCHES)
    current: str | None
    tasks: dict[str, StoredTask] = Field(max_length=MAX_TASKS)
    switches: list[StoredSwitch] = Field(max_length=MAX_SWITCHES)

    @model_validator(mode='after')
    def history(self):
        prior = None
        attempts = {t.attempt for t in self.tasks.values()}
        if len(attempts) != len(self.tasks) or any(key != t.id for key,t in self.tasks.items()):
            raise ValueError('ifc_task_identity_invalid')
        for switch in self.switches:
            if (switch.from_task != prior or switch.to == prior or switch.to not in self.tasks
                    or self.tasks[switch.to].state != 'ready'):
                raise ValueError('ifc_switch_history_invalid')
            prior = switch.to
        if self.revision != len(self.switches) or self.current != prior:
            raise ValueError('ifc_current_pointer_invalid')
        return self


def now():
    return datetime.now(timezone.utc).isoformat()


def write_atomic(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     suffix='.pending', delete=False) as stream:
        pending = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(pending, path)
        finally:
            stream.close()
            pending.unlink(missing_ok=True)


def read_versions(path):
    try:
        _, value = read_json(path, 4 * 1024 * 1024)
    except FileNotFoundError:
        return {'revision': 0, 'current': None, 'tasks': {}, 'switches': []}
    return StoredVersions.model_validate(value).model_dump(by_alias=True, exclude_unset=True)


def write_versions(path, value):
    StoredVersions.model_validate(value)
    write_atomic(path, value)


def validate_version_storage(inputs):
    """Check persisted candidates and their original attachments during backup and restore."""
    inputs = Path(inputs)
    root = checked_path(inputs, inputs / 'scene-ifc-versions')
    if not root.exists():
        return
    attachments = inputs / 'scene-attachments'
    for folder in root.iterdir():
        checked_path(root, folder)
        if not re.fullmatch('space-[a-f0-9]{16}', folder.name) or not (folder / 'versions.json').is_file():
            raise ValueError('ifc_version_storage_invalid')
        value = read_versions(checked_path(folder, folder / 'versions.json'))
        for task in value['tasks'].values():
            record = read_record(attachments, attachments / folder.name / task['attachment_id'], verify=True)
            if record['sha256'] != task['source_sha256'] or record['name'] != task['name']:
                raise ValueError('ifc_version_attachment_invalid')
            if task['state'] == 'ready':
                version = checked_path(folder, folder / task['attempt'])
                raw, doc = read_json(checked_path(version, version / 'ifc.json'), 8 * 1024 * 1024)
                if hashlib.sha256(raw).hexdigest() != task['catalog_sha256'] or doc['source']['sha256'] != record['sha256']:
                    raise ValueError('ifc_version_changed')
                validate_catalog(doc)
                validate_structure(doc)
                validate_source(version, doc)
                for product in doc['products']:
                    if product['geometry_status'] == 'extracted':
                        load_mesh(version, product)


class ParseFailed(ValueError):
    pass


def isolated_parser(python):
    """The caller selects a trusted worker interpreter; no request controls it."""
    def parse(source, output, digest):
        try:
            result = subprocess.run([str(python), '-m', 'experiments.scripts.parse_scene_ifc',
                                     str(source), str(output), digest], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ParseFailed('parse_timeout') from exc
        except OSError as exc:
            raise ParseFailed('parser_unavailable') from exc
        if result.returncode:
            raise ParseFailed('parse_rejected')
    return parse


class SceneIfcVersions:
    def __init__(self, attachments):
        self.attachments = attachments
        self.inputs = attachments.inputs
        self.root = self.inputs.root / 'scene-ifc-versions'

    def _paths(self, space):
        scope(self.inputs.directory, space)
        folder = checked_path(self.inputs.root, self.root / space)
        return folder, checked_path(folder, folder / 'versions.json')

    def _read(self, path):
        return read_versions(path)

    @staticmethod
    def _expire(value):
        for task in value['tasks'].values():
            if task['state'] == 'running' and task['lease_until'] <= time.time():
                task.update(state='failed', error='worker_interrupted', finished_at=now())
                task.pop('lease_until')

    def listing(self, space):
        _, path = self._paths(space)
        value = self._read(path)
        self._expire(value)
        return value

    def recover_interrupted(self, space):
        """Only the worker holding the singleton guard may call this on startup."""
        _, path = self._paths(space)
        with mutation_guard(self.inputs.root.parent):
            value = self._read(path)
            running = [task for task in value['tasks'].values() if task['state'] == 'running']
            for task in running:
                task.update(state='failed', error='worker_interrupted', finished_at=now())
                task.pop('lease_until')
            if running:
                write_versions(path, value)

    def enqueue(self, space, attachment, actor, *, retry=False):
        folder, path = self._paths(space)
        record, _ = self.attachments.download(space, attachment)
        if Path(record['name']).suffix.lower() != '.ifc':
            raise ValueError('ifc_attachment_required')
        key = hashlib.sha256(f'{record["sha256"]}:{PARSER}'.encode()).hexdigest()
        with mutation_guard(self.inputs.root.parent):
            value = self._read(path)
            self._expire(value)
            task = value['tasks'].get(key)
            if task is not None and not (retry and task['state'] == 'failed'):
                return task, False
            if retry and task is None:
                raise ValueError('ifc_retry_requires_failed_task')
            if task is None and len(value['tasks']) >= MAX_TASKS:
                raise ValueError('ifc_task_budget')
            if sum(t['state'] in ('queued','running') for t in value['tasks'].values()) >= MAX_PENDING:
                raise ValueError('ifc_queue_full')
            result = {'id': key, 'attachment_id': attachment, 'source_sha256': record['sha256'],
                      'name': record['name'], 'actor': actor, 'parser': PARSER, 'state': 'queued',
                      'requested_at': now(), 'attempt': uuid4().hex}
            value['tasks'][key] = result
            folder.mkdir(parents=True, exist_ok=True)
            write_versions(path, value)
            return result, True

    def run(self, space, task_id, parse):
        """Claim one queued task, parse outside the runtime lock, then publish its candidate."""
        folder, path = self._paths(space)
        with mutation_guard(self.inputs.root.parent):
            value = self._read(path)
            task = value['tasks'].get(task_id)
            if task is None or task['state'] != 'queued':
                return False
            attempt = task['attempt']
            task.update(state='running', started_at=now(), lease_until=time.time()+LEASE_SECONDS)
            write_versions(path, value)
        error = 'parse_rejected'
        with tempfile.TemporaryDirectory(prefix='cospace-ifc-') as temp:
            try:
                record, raw = self.attachments.download(space, task['attachment_id'])
                if record['sha256'] != task['source_sha256']:
                    raise ValueError('source_changed')
                original = Path(temp) / 'source.ifc'
                original.write_bytes(raw)
                candidate = Path(temp) / 'parsed'
                parse(original, candidate, task['source_sha256'])
                catalog_raw, doc = read_json(candidate / 'ifc.json', 8 * 1024 * 1024)
                validate_catalog(doc)
                validate_structure(doc)
                validate_source(candidate, doc)
                if doc['source']['sha256'] != task['source_sha256']:
                    raise ValueError('source_changed')
                members = ['ifc.json', 'source.ifc']
                for product in doc['products']:
                    if product['geometry_status'] == 'extracted':
                        load_mesh(candidate, product)
                        members.append(product['mesh']['path'])
                pin = hashlib.sha256(catalog_raw).hexdigest()
                with mutation_guard(self.inputs.root.parent):
                    value = self._read(path)
                    self._expire(value)
                    current = value['tasks'][task_id]
                    if current['attempt'] != attempt or current['state'] != 'running':
                        return False
                    destination = checked_path(folder, folder / attempt)
                    with tempfile.TemporaryDirectory(dir=folder, prefix='stage-') as stage:
                        staged = Path(stage) / 'candidate'
                        staged.mkdir()
                        for name in members:
                            shutil.copyfile(candidate / name, staged / name)
                        staged.rename(destination)
                    current.update(state='ready', catalog_sha256=pin, finished_at=now())
                    current.pop('lease_until')
                    write_versions(path, value)
                    return True
            except ParseFailed as exc:
                error = str(exc) if str(exc) in ('parse_timeout', 'parser_unavailable', 'parse_rejected') else error
            except (OSError, ValueError, TypeError, KeyError, BadZipFile):
                pass
        with mutation_guard(self.inputs.root.parent):
            value = self._read(path)
            current = value['tasks'][task_id]
            if current['attempt'] == attempt and current['state'] == 'running':
                current.update(state='failed', error=error, finished_at=now())
                current.pop('lease_until')
                write_versions(path, value)
        return False

    def activate(self, space, task_id, *, expected_revision, actor):
        folder, path = self._paths(space)
        with mutation_guard(self.inputs.root.parent):
            value = self._read(path)
            if value['revision'] != expected_revision:
                raise ValueError('ifc_current_changed')
            task = value['tasks'].get(task_id)
            if task is None or task['state'] != 'ready':
                raise ValueError('ifc_version_not_ready')
            binding = self._binding(space, folder, task)
            if value['current'] == task_id:
                return binding
            if len(value['switches']) >= MAX_SWITCHES:
                raise ValueError('ifc_switch_budget')
            value['switches'].append({'from': value['current'], 'to': task_id, 'actor': actor, 'at': now()})
            value.update(current=task_id, revision=expected_revision+1)
            write_versions(path, value)
            return binding

    @staticmethod
    def _binding(space, folder, task):
        if not re.fullmatch('[a-f0-9]{32}', task['attempt']):
            raise ValueError('ifc_version_invalid')
        root = checked_path(folder, folder / task['attempt'])
        raw, doc = read_json(root / 'ifc.json', 8 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != task['catalog_sha256']:
            raise ValueError('ifc_version_changed')
        validate_source(root, doc)
        return IfcBinding(space_id=space, root=str(root), catalog_sha256=task['catalog_sha256'])

    def resolve(self, space, *, catalog_sha256=None, include_pending=False):
        folder, path = self._paths(space)
        value = self._read(path)
        if catalog_sha256 is None:
            task = value['tasks'].get(value['current'])
        else:
            allowed = set(value['tasks']) if include_pending else {switch['to'] for switch in value['switches']}
            task = next((item for item in value['tasks'].values() if item['id'] in allowed and item['state'] == 'ready'
                         and item['catalog_sha256'] == catalog_sha256), None)
        return self._binding(space, folder, task) if task is not None else None
