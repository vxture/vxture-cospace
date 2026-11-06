"""Saved check evidence, separate from immutable inputs and build admission."""
from contextlib import closing
import hashlib
import json
import sqlite3


class PreflightUnavailable(RuntimeError):
    pass


class PreflightRecords:
    def __init__(self,catalog):
        self.catalog=catalog
        self.path=catalog.root/'preflight-records.sqlite3'

    def fingerprint(self,identity):
        record=self.catalog.read(identity)
        return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def save(self,identity,report,actor,expected_fingerprint):
        fingerprint=self.fingerprint(identity)
        if fingerprint!=expected_fingerprint:raise ValueError('preflight_registration_changed')
        try:
            with closing(sqlite3.connect(self.path,timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS checks(sequence INTEGER PRIMARY KEY AUTOINCREMENT,input_id TEXT NOT NULL, fingerprint TEXT NOT NULL,record TEXT NOT NULL)')
                    saved=report|{'actor':actor,'registration_sha256':fingerprint}
                    cursor=db.execute('INSERT INTO checks(input_id,fingerprint,record) VALUES(?,?,?)',(identity,fingerprint,json.dumps(saved,ensure_ascii=False)))
                    return saved|{'sequence':cursor.lastrowid}
        except (sqlite3.Error,OSError) as exc:raise PreflightUnavailable('preflight_records_unavailable') from exc

    def latest(self,identity):
        fingerprint=self.fingerprint(identity)
        if not self.path.exists():return None
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                row=db.execute('SELECT sequence,fingerprint,record FROM checks WHERE input_id=? ORDER BY sequence DESC LIMIT 1',(identity,)).fetchone()
                if not row:return None
                report=json.loads(row[2])
                if (not isinstance(report,dict) or report.get('input_id')!=identity or report.get('registration_sha256')!=row[1]
                    or report.get('status') not in ('passed','failed') or not isinstance(report.get('checked_at'),str)):
                    raise ValueError('invalid_check_record')
                return report|{'sequence':row[0],'registration_matches':row[1]==fingerprint,'current_files_checked':False}
        except (sqlite3.Error,OSError,ValueError,TypeError) as exc:raise PreflightUnavailable('preflight_records_unavailable') from exc
