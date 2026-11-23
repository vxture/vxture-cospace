"""Authorized host-owned registration revisions; calculations never grant approval."""
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import os
from typing import Annotated, Literal

import numpy as np
from pydantic import Field, ValidationError, model_validator

from packages.lifecycle.preview_control_lock import mutation_guard
from packages.spatial.georeference import Fixed, Text, Digest, Point, ModelFrame, RegistrationInput, evaluate_registration
from packages.spatial.scene_identity import canonical, content_digest
from packages.spatial.registration_geography import GeographicBinding, validate_binding, project_objects, ADAPTER
from packages.spatial.coordinate_axes import registration_readiness

MAX_REVISIONS = 1000
MAX_BYTES = 1_048_576
Revision = Annotated[int, Field(ge=0, le=MAX_REVISIONS)]
Reason = Annotated[str, Field(min_length=1, max_length=2000)]


class RegistrationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RegistrationError(code)


def instant(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value)
            is not None, 'registration_invalid_time')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise RegistrationError('registration_invalid_time') from exc


class Approval(Fixed):
    evidence_note: Reason
    valid_from: Text
    valid_until: Text
    bounds_m: Annotated[list[Point], Field(min_length=2, max_length=2)]
    control_evidence_verified: bool
    independent_checks_verified: bool
    datum_verified: bool
    extent_verified: bool

    @model_validator(mode='after')
    def evidence(self):
        require(self.evidence_note.strip() and instant(self.valid_from) < instant(self.valid_until),
                'registration_invalid_approval')
        require(all((self.control_evidence_verified, self.independent_checks_verified,
                     self.datum_verified, self.extent_verified)), 'registration_evidence_required')
        require(all(a < b for a, b in zip(*self.bounds_m)), 'registration_invalid_extent')
        return self


class Command(Fixed):
    space_id: Text
    candidate_id: Text
    source_sha256: Digest
    expected_revision: Revision
    request_id: Annotated[str, Field(pattern='^[a-f0-9]{32}$')]
    action: Literal['save', 'submit', 'approve', 'reject', 'adopt', 'clear_adoption']
    reason: Reason
    document: RegistrationInput | None = None
    approval: Approval | None = None
    geographic_binding: GeographicBinding | None = None

    @model_validator(mode='after')
    def shape(self):
        require(bool(self.reason.strip()), 'registration_reason_required')
        require((self.action == 'save') == (self.document is not None), 'registration_invalid_request')
        require((self.action == 'approve') == (self.approval is not None), 'registration_invalid_request')
        require(self.geographic_binding is None or self.action == 'save', 'registration_invalid_request')
        return self


class CheckRequest(Fixed):
    space_id: Text
    candidate_id: Text
    source_sha256: Digest
    document: RegistrationInput
    geographic_binding: GeographicBinding | None = None


class Snapshot(Fixed):
    revision: Revision = 0
    document: RegistrationInput | None = None
    report: dict | None = None
    review_status: Literal['empty', 'draft', 'submitted', 'approved', 'rejected'] = 'empty'
    authored_by: Text | None = None
    reviewed_by: Text | None = None
    reviewed_at: Text | None = None
    approval: Approval | None = None
    approved_revision: Revision | None = None
    adopted_revision: Revision | None = None
    action: Text | None = None
    actor: Text | None = None
    changed_at: Text | None = None
    reason: Reason | None = None
    geographic_binding: GeographicBinding | None = None

    @model_validator(mode='after')
    def consistency(self):
        if self.revision == 0:
            require(self.model_dump(exclude={'revision', 'review_status'}) ==
                    {key: None for key in type(self).model_fields if key not in ('revision', 'review_status')}
                    and self.review_status == 'empty', 'registration_store_integrity')
            return self
        require(all(value is not None for value in (self.document, self.report, self.authored_by,
                self.action, self.actor, self.changed_at, self.reason)), 'registration_store_integrity')
        instant(self.changed_at)
        require(self.review_status != 'empty' and self.action in
                ('save', 'submit', 'approve', 'reject', 'adopt', 'clear_adoption'), 'registration_store_integrity')
        reviewed = self.review_status in ('approved', 'rejected')
        require(reviewed == (self.reviewed_by is not None) and reviewed == (self.reviewed_at is not None),
                'registration_store_integrity')
        if reviewed:
            require(self.reviewed_by != self.authored_by and instant(self.reviewed_at) <= instant(self.changed_at),
                    'registration_store_integrity')
        require((self.review_status == 'approved') == (self.approval is not None) and
                (self.review_status == 'approved') == (self.approved_revision is not None), 'registration_store_integrity')
        for reference in (self.approved_revision, self.adopted_revision):
            require(reference is None or 1 <= reference <= self.revision, 'registration_store_integrity')
        return self


def source_from_model(model, space_id, candidate_id):
    manifest = model.manifest
    require(manifest.get('space_id') == space_id and manifest['id'] == candidate_id,
            'registration_source_changed')
    axes = manifest.get('axes', [])
    require(registration_readiness(axes)['status'] == 'ready',
            'registration_source_axes_unsupported')
    require(manifest.get('unit') == 'm', 'registration_source_unit_unsupported')
    with np.load(model.root / 'spatial.npz', allow_pickle=False) as arrays:
        points = arrays['points']
        require(points.ndim == 2 and points.shape[1] == 3 and len(points) and np.isfinite(points).all(),
                'registration_source_geometry_invalid')
        bounds = [points.min(axis=0).astype(float).tolist(), points.max(axis=0).astype(float).tolist()]
    digest = sha256((model.root / 'model.json').read_bytes()).hexdigest()
    return source_frame(manifest, digest, bounds, space_id, candidate_id)


def source_frame(manifest, digest, bounds, space_id, candidate_id):
    try:
        frame = ModelFrame.model_validate(dict(space_id=space_id, candidate_id=candidate_id,
            manifest_sha256=digest, model_sha256=manifest['members']['spatial.npz']['sha256'],
            frame_id=manifest['frame_id'], unit=manifest['unit'], axes=manifest['axes'], handedness='right', bounds_m=bounds))
    except ValidationError as exc:
        raise RegistrationError('registration_source_geometry_invalid') from exc
    return {'source_sha256': digest, 'model_source': frame.model_dump()}


class SceneRegistrations:
    def __init__(self, root, workspace_scope, actor, jobs, *, clock=None, adapters=None):
        self.path = Path(root) / 'scene-registrations.sqlite3'
        self.workspace_scope, self.actor, self.jobs = workspace_scope, actor, jobs
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
        self.adapters = set(os.environ.get('COSPACE_REGISTRATION_ADAPTERS', '').split(',')) if adapters is None else set(adapters)

    def source(self, space_id, candidate_id):
        if self.jobs is None:
            raise RegistrationError('registration_source_changed')
        if hasattr(self.jobs, 'displays'):
            displays = self.jobs.displays
            _, _, model, raw = displays.source('candidate', candidate_id)
            require(model.get('space_id') == space_id, 'registration_source_changed')
            require(registration_readiness(model.get('axes', []))['status'] == 'ready',
                    'registration_source_axes_unsupported')
            require(model.get('unit') == 'm', 'registration_source_unit_unsupported')
            digest = sha256(raw).hexdigest()
            info = displays.exact.describe('candidate', candidate_id, digest, model['members']['spatial.npz']['sha256'])
            # Frozen build manifests already carry the source's numeric extent.
            # Showing that extent must not wait for an engineering query index.
            # Legacy manifests without it wait for the offline verified extent.
            if model.get('bounds_m') is not None:
                return source_frame(model, digest, model['bounds_m'], space_id, candidate_id)
            require(info['state'] == 'ready', 'registration_source_preparing' if info['state'] in ('preparing', 'busy')
                    else 'registration_exact_unavailable')
            return source_frame(model, digest, info['bounds_m'], space_id, candidate_id)
        return source_from_model(self.jobs.model(candidate_id), space_id, candidate_id)

    def verify_points(self, document):
        """A reserved point reference is never accepted as self-attested coordinates."""
        frame = document['source']
        for control in document['controls']:
            reference = control['evidence_ref']
            if not reference.startswith('model-point:'):
                continue
            parsed = re.fullmatch(r'model-point:([a-f0-9]{64}):(0|[1-9][0-9]{0,9})', reference)
            require(parsed is not None and parsed[1] == frame['model_sha256'] and self.jobs is not None,
                    'registration_exact_point_invalid')
            result = self.jobs.displays.exact.read('candidate', frame['candidate_id'], frame['manifest_sha256'],
                                                  frame['model_sha256'], point_index=int(parsed[2]))
            require(result['state'] == 'ready' and len(result['points']) == 1
                    and result['points'][0]['anchor_m'] == control['source_m'], 'registration_exact_point_invalid')

    def source_diagnostics(self, space_id, candidate_id):
        """Inspect a blocked source without creating revisions or mutating its manifest."""
        with mutation_guard(self.jobs.root.parent):
            model = self.jobs.model(candidate_id)
            manifest = model.manifest
            require(manifest.get('space_id') == space_id and manifest['id'] == candidate_id,
                    'registration_source_changed')
            binding = manifest.get('source', {}).get('input_binding')
            input_id = None
            if binding and self.jobs.inputs is not None:
                from packages.data.input_coordinates import InputCoordinates
                original = self.jobs.inputs.read_original(binding['id'])
                require(original.get('space_id') == space_id and
                        any({key:value for key,value in record.items() if key not in ('snapshot','tracking')} == binding
                            for record in InputCoordinates(self.jobs.inputs).fixed_records(original)),
                        'registration_source_changed')
                input_id = original['id']
            return {'profile': 'cospace.registration-source/0.1', 'space_id': space_id,
                    'candidate_id': candidate_id, 'input_id': input_id, 'frame_id': manifest.get('frame_id'),
                    'registration_readiness': registration_readiness(manifest.get('axes'), manifest.get('unit'))}

    def scope(self, source):
        frame = source['model_source']
        return content_digest([self.workspace_scope, frame['space_id'], frame['candidate_id']])

    def check(self, source, body):
        request = CheckRequest.model_validate(body)
        frame = source['model_source']
        require((request.space_id, request.candidate_id, request.source_sha256) ==
                (frame['space_id'], frame['candidate_id'], source['source_sha256']), 'registration_source_changed')
        document = request.document.model_dump()
        require(document['source'] == frame, 'registration_source_changed')
        self.verify_points(document)
        try:
            report = evaluate_registration(document, expected_source=frame)
        except ValueError as exc:
            raise RegistrationError('registration_invalid_document') from exc
        binding = self.binding(document, request.geographic_binding)
        return {'document': document, 'report': report, 'geographic_binding': binding,
                'source_sha256': source['source_sha256']}

    def binding(self, document, binding):
        if binding is None:
            return None
        require(ADAPTER in self.adapters, 'registration_adapter_not_enabled')
        try:
            return validate_binding(document, binding.model_dump() if isinstance(binding, GeographicBinding) else binding)
        except ValueError as exc:
            raise RegistrationError(str(exc)) from exc

    def geometry(self, space_id, candidate_id):
        from packages.data.input_preview import sample, bounded
        with mutation_guard(self.jobs.root.parent):
            model = self.jobs.model(candidate_id)
            source = source_from_model(model, space_id, candidate_id)
            with np.load(model.root / 'spatial.npz', allow_pickle=False) as arrays:
                result = bounded({'profile': 'cospace.anchor-preview/0.1', 'candidate_id': candidate_id,
                    'space_id': space_id, 'source_sha256': source['model_source']['model_sha256'],
                    'manifest_sha256': source['source_sha256'], 'frame_id': source['model_source']['frame_id'],
                    'axes': source['model_source']['axes'], 'unit': 'm',
                    'appearance': model.manifest.get('appearance', 'source_rgb'), 'quality': 'unverified',
                    'robot_ready': False, **sample(arrays['points'], arrays['colors'])})
            require(self.source(space_id, candidate_id) == source, 'registration_source_changed')
            return result

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS revisions(scope TEXT NOT NULL, revision INTEGER NOT NULL, payload BLOB NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(scope,revision))')
        db.execute('CREATE TABLE IF NOT EXISTS requests(scope TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result BLOB NOT NULL, PRIMARY KEY(scope,request_id))')
        db.commit()
        return db

    def load(self, db, source, revision=None):
        query = 'SELECT revision,payload,digest FROM revisions WHERE scope=?'
        values = [self.scope(source)]
        if revision is not None:
            query += ' AND revision=?'
            values.append(revision)
        row = db.execute(query + ' ORDER BY revision DESC LIMIT 1', values).fetchone()
        if row is None:
            require(revision is None, 'registration_revision_not_found')
            return Snapshot().model_dump()
        try:
            require(len(row[1]) <= MAX_BYTES and sha256(row[1]).hexdigest() == row[2], 'registration_store_integrity')
            snapshot = Snapshot.model_validate_json(row[1]).model_dump()
            require(snapshot['revision'] == row[0] and canonical(snapshot) == row[1], 'registration_store_integrity')
            document = snapshot['document']
            require(document is not None, 'registration_store_integrity')
            require(document['source'] == source['model_source'], 'registration_source_changed')
            report = evaluate_registration(document, expected_source=source['model_source'])
            require(report == snapshot['report'], 'registration_store_integrity')
            if snapshot['review_status'] in ('submitted', 'approved'):
                require(not document['synthetic'] and report['calculation_status'] == 'checks_passed',
                        'registration_store_integrity')
            validate_binding(document, snapshot['geographic_binding'])
            require(snapshot['review_status'] not in ('approved',) or snapshot['approval'] is not None
                    and snapshot['reviewed_by'] != snapshot['authored_by'], 'registration_store_integrity')
            return snapshot
        except (ValueError, TypeError, KeyError) as exc:
            if str(exc) == 'registration_source_changed':
                raise
            raise RegistrationError('registration_store_integrity') from exc

    def fixed(self, source, revision):
        require(type(revision) is int and 1 <= revision <= MAX_REVISIONS, 'registration_invalid_revision')
        require(self.path.is_file(), 'registration_revision_not_found')
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            return self.load(db, source, revision)

    def read(self, source, revision=None):
        require(revision is None or type(revision) is int and 1 <= revision <= MAX_REVISIONS,
                'registration_invalid_revision')
        if not self.path.exists():
            require(revision is None, 'registration_revision_not_found')
            state = Snapshot().model_dump()
        else:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                state = self.load(db, source, revision)
        adopted = self.fixed(source, state['adopted_revision']) if state['adopted_revision'] else None
        if adopted:
            require(adopted['review_status'] == 'approved' and adopted['action'] == 'approve'
                    and adopted['approved_revision'] == adopted['revision'], 'registration_store_integrity')
        frame = source['model_source']
        return {**state, **source, 'profile': 'cospace.scene-registration/0.1',
                'space_id': frame['space_id'], 'candidate_id': frame['candidate_id'],
                'adopted': adopted, 'enabled_adapters': sorted(self.adapters & {ADAPTER}),
                'can_focus_geographic_map': self.geography_status(adopted) == 'available',
                'included_in_publication': False}

    def geography_status(self, adopted, at=None):
        if adopted is None:
            return 'registration_not_adopted'
        if adopted['geographic_binding'] is None:
            return 'geographic_binding_not_recorded'
        if ADAPTER not in self.adapters:
            return 'registration_adapter_not_enabled'
        period = adopted['approval']
        if not instant(period['valid_from']) <= instant(at or self.clock()) < instant(period['valid_until']):
            return 'registration_outside_valid_time'
        return 'available'

    def map(self, source, *, at=None):
        state = self.read(source)
        status = self.geography_status(state['adopted'], at)
        result = {'profile': 'cospace.registration-geographic-points/0.1', 'space_id': state['space_id'],
            'candidate_id': state['candidate_id'], 'source_sha256': source['source_sha256'],
            'registration_revision': state['adopted_revision'], 'status': status, 'crs': 'WGS84',
            'height_reference': 'ellipsoidal', 'objects': [], 'robot_ready': False}
        if status == 'available':
            adopted = state['adopted']
            model = self.jobs.model(state['candidate_id'])
            require(source_from_model(model, state['space_id'], state['candidate_id']) == source,
                    'registration_source_changed')
            result['objects'] = project_objects(adopted['document'], adopted['geographic_binding'],
                adopted['approval']['bounds_m'], model.objects()['objects'])
            result['geographic_binding'] = adopted['geographic_binding']
            result['check_metrics'] = adopted['report']['metrics']['check']
        return result

    def change(self, source, body, *, can_review=False):
        command = Command.model_validate(body)
        frame = source['model_source']
        require((command.space_id, command.candidate_id, command.source_sha256) ==
                (frame['space_id'], frame['candidate_id'], source['source_sha256']), 'registration_source_changed')
        require(command.action not in ('approve', 'reject') or can_review, 'registration_review_denied')
        guard = mutation_guard(self.jobs.root.parent) if self.jobs is not None else nullcontext()
        with guard:
            if self.jobs is not None:
                try:
                    self.jobs.controls.require_active(frame['space_id'], 'candidate:' + frame['candidate_id'])
                except ValueError as exc:
                    raise RegistrationError('registration_source_inactive') from exc
                require(self.source(frame['space_id'], frame['candidate_id']) == source, 'registration_source_changed')
            return self._change(source, command)

    def _change(self, source, command):
        scope = self.scope(source)
        fingerprint = content_digest([self.actor, command.model_dump()])
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replay = db.execute('SELECT fingerprint,result FROM requests WHERE scope=? AND request_id=?',
                                (scope, command.request_id)).fetchone()
            if replay:
                require(replay[0] == fingerprint, 'registration_request_conflict')
                return json.loads(replay[1])
            state = self.load(db, source)
            require(state['revision'] == command.expected_revision, 'registration_revision_changed')
            require(state['revision'] < MAX_REVISIONS, 'registration_revision_budget')
            now = self.clock()
            instant(now)
            if command.action == 'save':
                document = command.document.model_dump()
                require(document['source'] == source['model_source'], 'registration_source_changed')
                self.verify_points(document)
                try:
                    report = evaluate_registration(document, expected_source=source['model_source'])
                except ValueError as exc:
                    raise RegistrationError('registration_invalid_document') from exc
                state.update(document=document, report=report, review_status='draft', authored_by=self.actor,
                             reviewed_by=None, reviewed_at=None, approval=None, approved_revision=None,
                             geographic_binding=self.binding(document, command.geographic_binding))
            elif command.action == 'submit':
                require(state['review_status'] in ('draft', 'rejected'), 'registration_transition_invalid')
                require(state['report']['calculation_status'] == 'checks_passed', 'registration_checks_failed')
                require(not state['document']['synthetic'], 'registration_synthetic_not_approvable')
                state.update(review_status='submitted', reviewed_by=None, reviewed_at=None, approval=None, approved_revision=None)
            elif command.action in ('approve', 'reject'):
                require(state['review_status'] == 'submitted', 'registration_transition_invalid')
                require(state['authored_by'] != self.actor, 'registration_independent_reviewer_required')
                if command.action == 'approve':
                    bounds = command.approval.bounds_m
                    model_bounds = source['model_source']['bounds_m']
                    require(all(model_bounds[0][i] <= bounds[0][i] < bounds[1][i] <= model_bounds[1][i]
                                for i in range(3)), 'registration_extent_outside_model')
                    require(instant(command.approval.valid_until) > instant(now), 'registration_approval_expired')
                state.update(review_status='approved' if command.action == 'approve' else 'rejected',
                             reviewed_by=self.actor, reviewed_at=now,
                             approved_revision=state['revision'] + 1 if command.action == 'approve' else None,
                             approval=command.approval.model_dump() if command.approval else None)
            elif command.action == 'adopt':
                require(state['review_status'] == 'approved', 'registration_approval_required')
                period = state['approval']
                require(instant(period['valid_from']) <= instant(now) < instant(period['valid_until']),
                        'registration_outside_valid_time')
                require(state['adopted_revision'] != state['approved_revision'], 'registration_already_adopted')
                state['adopted_revision'] = state['approved_revision']
            else:
                require(state['adopted_revision'] is not None, 'registration_not_adopted')
                state['adopted_revision'] = None
            state.update(revision=state['revision'] + 1, action=command.action, actor=self.actor,
                         changed_at=now, reason=command.reason)
            state = Snapshot.model_validate(state).model_dump()
            raw = canonical(state)
            require(len(raw) <= MAX_BYTES, 'registration_size_budget')
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)', (scope, state['revision'], raw, sha256(raw).hexdigest()))
            result = {'revision': state['revision'], 'review_status': state['review_status'],
                      'adopted_revision': state['adopted_revision']}
            db.execute('INSERT INTO requests VALUES(?,?,?,?)', (scope, command.request_id, fingerprint, canonical(result)))
            return result
