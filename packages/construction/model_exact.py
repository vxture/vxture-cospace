"""Bounded original-row queries using SQLite R*Tree, separate from display LOD.

R*Tree's outward-rounded bounds select candidates; original doubles determine
spherical membership and confirmed coordinates. Builds stream fixed NPY batches.
"""
from collections import OrderedDict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import struct
import shutil
import tempfile
import threading
import time
from zipfile import ZipFile

import numpy as np

MAX_POINTS = 20_000_000
MAX_RESULTS = 32
BATCH_POINTS = 25_000
PROFILE = 'cospace.model-exact/0.1'


def checksum(source, index, point):
    return sha256(bytes.fromhex(source) + struct.pack('!qddd', index, *point)).digest()


class ModelExact:
    def __init__(self, displays):
        self.displays = displays
        self.root = displays.root.parent / 'model-exact'
        self.lock = threading.RLock()
        self.pending = OrderedDict()
        self.failed = OrderedDict()
        self.read_slots = threading.BoundedSemaphore(4)

    def source(self, kind, name, manifest_sha256, source_sha256):
        root, _, model, raw = self.displays.source(kind, name)
        if (sha256(raw).hexdigest() != manifest_sha256
                or model['members']['spatial.npz']['sha256'] != source_sha256):
            raise ValueError('exact_source_changed')
        if model.get('unit') != 'm':
            raise ValueError('exact_unit_unsupported')
        return root, model, raw

    def path(self, key):
        return self.root / (sha256((':'.join(key) + ':sqlite-rtree/1').encode()).hexdigest() + '.sqlite3')

    def state(self, kind, name, key):
        if self.path(key).is_file():
            return 'ready'
        with self.lock:
            if key in self.failed and time.monotonic() - self.failed[key] < 60:
                return 'unavailable'
            if len(self.pending) >= 16 and key not in self.pending:
                return 'busy'
            self.pending[key] = (kind, name)
        return 'preparing'

    def connect(self, key):
        db = sqlite3.connect(self.path(key).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        db.execute('PRAGMA cache_size=-2048')
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            info = json.loads(db.execute('SELECT value FROM metadata').fetchone()[0])
            if (info.get('source_manifest_sha256'), info.get('source_model_sha256')) != key:
                raise ValueError('exact_source_changed')
        except BaseException:
            db.close()
            raise
        return db, info

    def describe(self, kind, name, manifest_sha256, source_sha256):
        self.source(kind, name, manifest_sha256, source_sha256)
        key = (manifest_sha256, source_sha256)
        state = self.state(kind, name, key)
        if state != 'ready':
            return {'state': state}
        db, info = self.connect(key)
        db.close()
        return info | {'state': 'ready'}

    def read(self, kind, name, manifest_sha256, source_sha256, *, point=None, radius_m=None, point_index=None):
        _, model, _ = self.source(kind, name, manifest_sha256, source_sha256)
        if point_index is not None:
            if type(point_index) is not int or not 0 <= point_index < model['construction']['model_points']:
                raise ValueError('exact_query_invalid')
        elif (not isinstance(point, list) or len(point) != 3
              or any(type(v) not in (float, int) or not np.isfinite(v) for v in point)
              or type(radius_m) not in (float, int) or not np.isfinite(radius_m) or not .001 <= radius_m <= 1):
            raise ValueError('exact_query_invalid')
        result = {'profile': PROFILE, 'space_id': model.get('space_id'), 'model_id': model['id'],
                  'source_manifest_sha256': manifest_sha256, 'source_model_sha256': source_sha256,
                  'frame_id': model['frame_id'], 'unit': 'm', 'points': [],
                  'quality': 'source_precision_not_survey_acceptance'}
        key = (manifest_sha256, source_sha256)
        state = self.state(kind, name, key)
        if state != 'ready':
            return result | {'state': state}
        if not self.read_slots.acquire(blocking=False):
            return result | {'state': 'busy'}
        try:
            db, _ = self.connect(key)
            with closing(db):
                if point_index is not None:
                    rows = db.execute('SELECT id,x,y,z,checksum FROM points WHERE id=?', (point_index,)).fetchall()
                else:
                    x, y, z = point
                    rows = db.execute('''SELECT p.id,p.x,p.y,p.z,p.checksum FROM bounds b
                        JOIN points p ON p.id=b.id WHERE b.minx<=? AND b.maxx>=?
                        AND b.miny<=? AND b.maxy>=? AND b.minz<=? AND b.maxz>=?
                        AND (p.x-?)*(p.x-?)+(p.y-?)*(p.y-?)+(p.z-?)*(p.z-?)<=? LIMIT ?''',
                        (x+radius_m, x-radius_m, y+radius_m, y-radius_m, z+radius_m, z-radius_m,
                         x, x, y, y, z, z, radius_m**2, MAX_RESULTS+1)).fetchall()
                if len(rows) > MAX_RESULTS:
                    return result | {'state': 'narrow_query', 'limit': MAX_RESULTS}
                points = []
                for i, x, y, z, digest in sorted(rows):
                    if checksum(source_sha256, i, [x, y, z]) != digest:
                        raise ValueError('exact_integrity')
                    points.append({'point_id': f'{source_sha256}:{i}', 'point_index': i, 'anchor_m': [x, y, z]})
                if point_index is not None and len(points) != 1:
                    raise ValueError('exact_integrity')
            return result | {'state': 'ready', 'points': points}
        except sqlite3.OperationalError:
            return result | {'state': 'busy'}
        finally:
            self.read_slots.release()

    def scan(self):
        with self.lock:
            if not self.pending:
                return
            key, (kind, name) = self.pending.popitem(last=False)
        try:
            self.build(kind, name, key)
        except (ValueError, OSError, LookupError, TypeError, AttributeError, sqlite3.Error):
            with self.lock:
                self.failed[key] = time.monotonic()
                while len(self.failed) > 128:
                    self.failed.popitem(last=False)

    def objects(self, kind, name, manifest_sha256, source_sha256):
        """Bounded engineering snapshots, with every anchor checked against source rows."""
        from packages.construction.model_display import small_json
        from packages.spatial.preview_objects import snapshot, object_result
        from packages.spatial.preview_business import business_snapshot, links_for
        from packages.spatial.preview_relations import relation_snapshot, relations_for
        root, model, _ = self.source(kind, name, manifest_sha256, source_sha256)
        if not model.get('semantic_annotation'):
            raise ValueError('semantic_objects_not_available')
        ontology, ontology_raw = small_json(root / 'ontology.json')
        _, objects_raw = small_json(root / 'objects.json')
        doc = snapshot(model, objects_raw, ontology_raw)
        for obj in doc['objects']:
            result = self.read(kind, name, manifest_sha256, source_sha256,
                               point_index=obj['evidence']['point_index'])
            if result['state'] != 'ready':
                return {'state': result['state']}
            if not np.allclose(obj['anchor_m'], result['points'][0]['anchor_m'], rtol=0, atol=1e-6):
                raise ValueError('object_anchor_mismatch')
        result = object_result(model, doc)
        if model.get('business_association'):
            _, raw = small_json(root / 'business.json')
            business = business_snapshot(model, doc, raw)
            result['profile'] = 'cospace.preview-object-query/0.2'
            for obj in result['objects']:
                obj['business_links'] = links_for(business, obj['object_id'])
        elif 'business.json' in model['members']:
            raise ValueError('business_declaration_missing')
        if model.get('object_relations'):
            _, raw = small_json(root / 'relations.json')
            relations = relation_snapshot(model, doc, ontology, raw)
            result['profile'] = 'cospace.preview-object-query/0.3'
            result['relations'] = relations_for(relations)
        elif 'relations.json' in model['members']:
            raise ValueError('relation_declaration_missing')
        return result | {'state': 'ready', 'source_manifest_sha256': manifest_sha256}

    def build(self, kind, name, key):
        root, model, raw = self.source(kind, name, *key)
        count = model['construction']['model_points']
        if type(count) is not int or not 0 < count <= MAX_POINTS:
            raise ValueError('exact_capacity')
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.path(key)
        if destination.is_file():
            return
        if shutil.disk_usage(self.root).free < count * 192 + 64 * 1024 * 1024:
            raise ValueError('exact_disk_budget')
        path = root / 'spatial.npz'
        digest = sha256()
        with path.open('rb') as stream:
            while block := stream.read(256 * 1024):
                digest.update(block)
        if digest.hexdigest() != key[1]:
            raise ValueError('exact_integrity')
        with tempfile.TemporaryDirectory(prefix='.exact-', dir=self.root) as staging:
            database = Path(staging) / 'index.sqlite3'
            with closing(sqlite3.connect(database)) as db, db:
                db.execute('PRAGMA journal_mode=OFF')
                db.execute('PRAGMA cache_size=-8192')
                db.execute('PRAGMA max_page_count=1048576')
                db.execute('CREATE TABLE points(id INTEGER PRIMARY KEY,x REAL,y REAL,z REAL,checksum BLOB)')
                db.execute('CREATE VIRTUAL TABLE bounds USING rtree(id,minx,maxx,miny,maxy,minz,maxz)')
                db.execute('CREATE TABLE metadata(value TEXT NOT NULL)')
                low, high = np.full(3, np.inf), np.full(3, -np.inf)
                with ZipFile(path) as archive, archive.open('points.npy') as source:
                    version = np.lib.format.read_magic(source)
                    if version != (1, 0):
                        raise ValueError('exact_npy_version')
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(source)
                    if shape != (count, 3) or fortran or dtype.kind != 'f' or dtype.itemsize not in (4, 8):
                        raise ValueError('exact_geometry_invalid')
                    for start in range(0, count, BATCH_POINTS):
                        if self.displays.stopping.is_set():
                            raise ValueError('exact_interrupted')
                        n = min(BATCH_POINTS, count-start)
                        points = np.frombuffer(source.read(n * 3 * dtype.itemsize), dtype=dtype).reshape(n, 3)
                        if not np.isfinite(points).all():
                            raise ValueError('exact_geometry_invalid')
                        low, high = np.minimum(low, points.min(axis=0)), np.maximum(high, points.max(axis=0))
                        db.executemany('INSERT INTO points VALUES(?,?,?,?,?)',
                            ((start+i, float(p[0]), float(p[1]), float(p[2]), checksum(key[1], start+i, p))
                             for i, p in enumerate(points)))
                        db.executemany('INSERT INTO bounds VALUES(?,?,?,?,?,?,?)',
                            ((start+i, float(p[0]), float(p[0]), float(p[1]), float(p[1]), float(p[2]), float(p[2]))
                             for i, p in enumerate(points)))
                    if source.read(1):
                        raise ValueError('exact_geometry_invalid')
                info = {'profile': PROFILE, 'source_manifest_sha256': key[0], 'source_model_sha256': key[1],
                        'point_count': count, 'bounds_m': [low.tolist(), high.tolist()], 'index': 'sqlite-rtree/1'}
                db.execute('INSERT INTO metadata VALUES(?)', (json.dumps(info, allow_nan=False),))
            if (root / 'model.json').read_bytes() != raw:
                raise ValueError('exact_source_changed')
            database.rename(destination)

    def clear(self):
        with self.lock:
            self.pending.clear()
            self.failed.clear()
