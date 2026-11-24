"""Logical stored original bytes by trusted workspace, without reading blobs."""
from contextlib import closing
import sqlite3

from packages.lifecycle.scene_initialization import checksum


def record_scope(db, principal):
    value = {key: getattr(principal, key) for key in ('issuer', 'org_id', 'workspace_id')}
    db.execute('CREATE TABLE IF NOT EXISTS data_resource_scopes(scope TEXT PRIMARY KEY,issuer TEXT NOT NULL,org_id TEXT NOT NULL,workspace_id TEXT NOT NULL)')
    scope = checksum(value)
    before = db.execute('SELECT issuer,org_id,workspace_id FROM data_resource_scopes WHERE scope=?', (scope,)).fetchone()
    if before is not None and before != tuple(value.values()):
        raise ValueError('resource_scope_invalid')
    db.execute('INSERT OR IGNORE INTO data_resource_scopes VALUES(?,?,?,?)', (scope, *value.values()))


def scope_contexts(db, tables, known):
    scopes = {checksum(dict(zip(('issuer','org_id','workspace_id'), owner))): owner for owner in known}
    if 'data_resource_scopes' not in tables:
        return scopes
    for scope, issuer, org, workspace in db.execute('SELECT scope,issuer,org_id,workspace_id FROM data_resource_scopes'):
        value = {'issuer':issuer, 'org_id':org, 'workspace_id':workspace}
        if not all(isinstance(v,str) and 0<len(v)<=2048 for v in value.values()) or checksum(value)!=scope:
            raise ValueError('resource_storage_scope_invalid')
        scopes[scope] = (issuer, org, workspace)
    return scopes


def stored_bytes(directory, known):
    path = directory.root / 'business-projects.sqlite3'
    if not path.exists():
        return {}
    if any(p.is_symlink() or p.is_junction() for p in (path,*path.parents)) or path.resolve().parent != directory.root.resolve():
        raise ValueError('resource_storage_path_invalid')
    totals = {}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        scopes = scope_contexts(db, tables, known)
        for table in ('data_resource_files','data_resource_file_history','data_shared_versions'):
            if table not in tables:
                continue
            for scope, size in db.execute(f'SELECT scope,COALESCE(SUM(LENGTH(payload)),0) FROM {table} GROUP BY scope'):
                if scope not in scopes or type(size) is not int or size<0:
                    raise ValueError('resource_storage_scope_unknown')
                owner = scopes[scope]
                totals[owner] = totals.get(owner, 0) + size
    return totals
