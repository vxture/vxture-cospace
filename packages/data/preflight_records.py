"""Saved check evidence, separate from immutable inputs and build admission."""
from contextlib import closing
import hashlib
import json
import sqlite3
from pydantic import BaseModel, ConfigDict, Field


class PreflightHistoryQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    space_id: str | None = Field(default=None, pattern=r'^space-[a-f0-9]{16}$')
    limit: int = Field(default=20, ge=1, le=100)
    before_sequence: int | None = Field(default=None, ge=1, le=9007199254740991)
    sequence: int | None = Field(default=None, ge=1, le=9007199254740991)


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

    def history(self, identity, *, limit=20, before_sequence=None, sequence=None):
        query=PreflightHistoryQuery(limit=limit,before_sequence=before_sequence,sequence=sequence)
        if sequence is not None and before_sequence is not None:
            raise ValueError('preflight_history_cursor_conflict')
        fingerprint=self.fingerprint(identity)
        result={'input_id':identity,'items':[],'next_before_sequence':None,
                'current_files_checked':False,'consistency':'saved_records_not_current_file_validation'}
        if not self.path.exists():return result
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                sql='SELECT sequence,fingerprint,record FROM checks WHERE input_id=?'
                values=[identity]
                if query.before_sequence is not None:
                    sql+=' AND sequence<?';values.append(query.before_sequence)
                if query.sequence is not None:
                    sql+=' AND sequence=?';values.append(query.sequence)
                rows=db.execute(sql+' ORDER BY sequence DESC LIMIT ?',values+[query.limit+1]).fetchall()
                for number,registered,raw in rows[:query.limit]:
                    if len(raw.encode('utf-8'))>262144:raise ValueError('history_record_budget')
                    report=json.loads(raw)
                    if (not isinstance(report,dict) or report.get('input_id')!=identity
                        or report.get('registration_sha256')!=registered
                        or report.get('status') not in ('passed','failed')
                        or not isinstance(report.get('checked_at'),str)):
                        raise ValueError('invalid_check_record')
                    result['items'].append(report|{'sequence':number,
                        'registration_matches':registered==fingerprint,'current_files_checked':False})
                if len(rows)>query.limit:result['next_before_sequence']=rows[query.limit-1][0]
                return result
        except (sqlite3.Error,OSError,ValueError,TypeError) as exc:
            raise PreflightUnavailable('preflight_records_unavailable') from exc
