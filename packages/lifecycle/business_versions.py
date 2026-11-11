"""Persistent display identities beside immutable engineering records.

Never edits manifests, signatures or source event times. The SQLite sidecar is
part of the business runtime and must be included in backups.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
import secrets
import sqlite3

from packages.lifecycle.preview_control_lock import mutation_guard


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


class BusinessVersions:
    def __init__(self, root):
        requested = Path(root)
        if requested.is_symlink() or not requested.is_dir():
            raise ValueError('existing_business_runtime_required')
        self.root = requested.resolve(strict=True)
        self.path = self.root / 'business-versions.sqlite3'
        if self.path.is_symlink():
            raise ValueError('business_version_database_symlink_rejected')
        with closing(self.connect()) as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS identities (
                  kind TEXT NOT NULL, scope TEXT NOT NULL, identity TEXT NOT NULL,
                  sequence INTEGER NOT NULL, code TEXT NOT NULL,
                  PRIMARY KEY(kind,scope,identity), UNIQUE(kind,scope,sequence),
                  UNIQUE(kind,scope,code));
                CREATE TABLE IF NOT EXISTS presentation (
                  space TEXT NOT NULL, identity TEXT NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(space,identity));
            ''')

    def connect(self):
        # Fixed filename, not a caller-supplied SQLite URI or connection string.
        return sqlite3.connect(database=self.path, timeout=30, uri=False)

    def allocate(self, kind, scope, identity, prefix, *, random_scene=False):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT code FROM identities WHERE kind=? AND scope=? AND identity=?',
                             (kind, scope, identity)).fetchone()
            if row:
                return row[0]
            if random_scene:
                for _ in range(128):
                    sequence = secrets.randbelow(1_000_000)
                    try:
                        code = f'S{sequence:06d}'
                        db.execute('INSERT INTO identities VALUES (?,?,?,?,?)',
                                   (kind, scope, identity, sequence, code))
                        return code
                    except sqlite3.IntegrityError:
                        continue
                raise ValueError('scene_number_allocation_exhausted')
            sequence = db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM identities WHERE kind=? AND scope=?',
                                  (kind, scope)).fetchone()[0]
            code = f'{prefix}{sequence:02d}'
            db.execute('INSERT INTO identities VALUES (?,?,?,?,?)', (kind, scope, identity, sequence, code))
            return code

    def lookup(self, kind, scope, identity):
        with closing(self.connect()) as db:
            row = db.execute('SELECT code FROM identities WHERE kind=? AND scope=? AND identity=?',
                             (kind, scope, identity)).fetchone()
            return row[0] if row else None

    @staticmethod
    def records(paths):
        records = [json.loads(p.read_bytes()) for p in paths]
        return sorted(records, key=lambda r: (r.get('created_at') or r.get('registered_at') or '', r['id']))

    def sync(self):
        """Idempotent inventory migration under the existing runtime writer lock."""
        with mutation_guard(self.root):
            spaces = self.records((self.root/'preview-directory'/'space').glob('*.json'))
            valid = {r['id'] for r in spaces}
            for r in spaces:
                self.allocate('scene', '', r['id'], 'S', random_scene=True)
            inputs = self.records((self.root/'preview-inputs').glob('input-*.json'))
            for r in inputs:
                if r.get('space_id') in valid:
                    # No inferred version chains: independent registrations remain independent D.
                    self.allocate('input', r['space_id'], r['id'], 'D')
            jobs = self.records((self.root/'preview-builds').glob('*/job.json'))
            by_id = {r['id']: r for r in jobs}
            resolving = set()

            def build(r):
                space, identity = r.get('space_id'), r['id']
                if space not in valid:
                    return None
                saved = self.lookup('build', space, identity)
                if saved:
                    return saved
                if identity in resolving:
                    raise ValueError('business_build_lineage_cycle')
                resolving.add(identity)
                parent = r.get('view_parent_id') or r.get('base_candidate_id')
                output = self.root/'preview-builds'/identity/'output'/'model.json'
                if output.exists():
                    manifest = json.loads(output.read_bytes())
                    ref = manifest.get('semantic_annotation', {}).get('base_candidate_ref', {})
                    parent = parent or ref.get('candidate_id')
                if parent and parent not in by_id:
                    # An unverifiable derived candidate must not masquerade as a new build.
                    resolving.remove(identity)
                    return None
                if parent and parent in by_id:
                    previous = by_id[parent]
                    if previous.get('space_id') != space:
                        raise ValueError('business_build_lineage_scope_mismatch')
                    code = build(previous)
                    # Alias candidates preserve their immutable identity, sharing the source B.
                    if code:
                        self.alias(space, identity, code)
                else:
                    code = self.allocate('build', space, identity, 'B')
                resolving.remove(identity)
                return code

            for r in jobs:
                build(r)
            pubs = self.records((self.root/'preview-builds'/'publications').glob('preview-*/publication.json'))
            for r in pubs:
                space = r.get('space_id')
                code = self.build_code(space, r.get('candidate_id')) if space in valid else None
                if code:
                    self.allocate('publication', space+'/'+code, r['id'], code+'-P')
            return {'scenes':len(spaces), 'inputs':len(inputs), 'build_records':len(jobs), 'publications':len(pubs)}

    def alias(self, space, identity, code):
        # Separate kind avoids weakening sequence/code uniqueness for actual builds.
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO presentation VALUES (?,?,?)',
                       (space, 'build-alias:'+identity, json.dumps({'build_code':code})))

    def build_code(self, space, identity):
        direct = self.lookup('build', space, identity)
        if direct:
            return direct
        with closing(self.connect()) as db:
            row = db.execute('SELECT payload FROM presentation WHERE space=? AND identity=?',
                             (space, 'build-alias:'+str(identity))).fetchone()
            return json.loads(row[0])['build_code'] if row else None

    def enrich(self, kind, record):
        result = dict(record)
        space = record.get('space_id')
        if kind == 'scene':
            result['scene_code'] = self.lookup('scene', '', record['id'])
        elif kind == 'input' and space:
            code = self.lookup('input', space, record['id'])
            result['material_code'] = code
            result['version_code'] = code+'-V01' if code else None
            if not result.get('registered_at'):
                with closing(self.connect()) as db:
                    rows=db.execute('SELECT payload FROM presentation WHERE space=? AND identity LIKE ?',
                                    (space, 'input-time:'+record['id'])).fetchall()
                if rows:
                    result.update(json.loads(rows[0][0]))
        elif kind == 'build' and space:
            result['build_code'] = self.build_code(space, record['id'])
            result['demo_timeline'] = self.timeline(space, record['id'])
        elif kind == 'publication' and space:
            code = self.build_code(space, record['candidate_id'])
            result['build_code'] = code
            result['version_code'] = self.lookup('publication', space+'/'+code, record['id']) if code else None
        if kind in ('build', 'publication') and space:
            scene_code = self.lookup('scene', '', space)
            result['scene_code'] = scene_code
            local_code = result.get('version_code') if kind == 'publication' else result.get('build_code')
            result['display_code'] = f'{scene_code}-{local_code}' if scene_code and local_code else None
            build_code = result.get('build_code')
            result['build_display_code'] = f'{scene_code}-{build_code}' if scene_code and build_code else None
        return result

    def ontology(self, record):
        owner=record.get('authoring',{}).get('workspace',{})
        key=hashlib.sha256(json.dumps(owner,sort_keys=True).encode()).hexdigest()+':'+record['ontology_id']
        code=self.allocate('ontology','',key,'O')
        version=self.allocate('ontology-version',code,record['version']+':'+record['sha256'],code+'-V')
        return record|{'rule_code':code,'version_code':version}

    def timeline(self, space, identity):
        with closing(self.connect()) as db:
            row = db.execute('SELECT payload FROM presentation WHERE space=? AND identity=?',
                             (space, 'timeline:'+identity)).fetchone()
            return json.loads(row[0]) if row else None

    def estimate_demo_times(self):
        """Explicit operator command only; never invent source audit timestamps."""
        changed = 0
        with mutation_guard(self.root):
            pubs = self.records((self.root/'preview-builds'/'publications').glob('preview-*/publication.json'))
            for r in self.records((self.root/'preview-builds').glob('*/job.json')):
                space, identity = r.get('space_id'), r['id']
                previous=self.timeline(space,identity) if space else None
                if not space or r.get('state') != 'succeeded' or previous and previous.get('estimation_revision')==2:
                    continue
                created, started, finished = [stamp(r.get(k)) for k in ('created_at','started_at','finished_at')]
                if not created:
                    continue
                related = [p for p in pubs if p.get('candidate_id') == identity and p.get('space_id') == space]
                review = next((stamp(p.get('selection_review',{}).get('reviewed_at')) for p in related
                               if stamp(p.get('selection_review',{}).get('reviewed_at'))), None)
                selections = self.root/'preview-builds'/'space-selections'/(space+'.json')
                if selections.exists():
                    selected = json.loads(selections.read_bytes())
                    if selected.get('candidate_id') == identity:
                        review = review or stamp(selected.get('selection_review',{}).get('reviewed_at'))
                # Earliest publication is an upper bound, not an actual confirmation event.
                published = min((stamp(p['created_at']) for p in related if stamp(p.get('created_at'))), default=None)
                end_model = finished or published or created+timedelta(minutes=10)
                begin_model = started or min(created, end_model)
                if begin_model > end_model:
                    continue
                input_path = self.root/'preview-inputs'/(str(r.get('input_id'))+'.json')
                source = json.loads(input_path.read_bytes()) if input_path.exists() else {}
                registered = stamp(source.get('registered_at')) if not source.get('registered_at_estimated') else None
                prepare = registered or created-timedelta(minutes=20)
                check = max(prepare, min(created-timedelta(minutes=5), begin_model))
                confirmation = review or published or end_model+timedelta(minutes=5)
                boundaries = [prepare, check, begin_model, end_model, confirmation]
                if boundaries != sorted(boundaries):
                    continue
                estimates = [not registered or bool(source.get('registered_at_estimated')), True, not started, not finished, not review]
                payload = {'profile':'cospace.demo-stage-times/0.1', 'estimation_revision':2, 'estimated':any(estimates),
                           'basis':'保留真实起止；缺失准备按构建前20分钟、检查按前5分钟估算；缺失核对取首次发布上界，否则按完成后5分钟估算。',
                           'generated_at':datetime.now(timezone.utc).isoformat(),
                           'stages':[{'start':boundaries[i].isoformat(), 'end':boundaries[i+1].isoformat(),
                                      'estimated':estimates[i] or estimates[i+1]} for i in range(4)]}
                with closing(self.connect()) as db, db:
                    db.execute('INSERT OR REPLACE INTO presentation VALUES (?,?,?)',
                               (space, 'timeline:'+identity, json.dumps(payload, ensure_ascii=False)))
                    if r.get('input_id') and not registered:
                        db.execute('INSERT OR IGNORE INTO presentation VALUES (?,?,?)',
                                   (space,'input-time:'+r['input_id'],json.dumps({
                                       'registered_at':prepare.isoformat(),'registered_at_estimated':True})))
                changed += 1
        return changed
