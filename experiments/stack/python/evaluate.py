"""Compatibility evidence only; no production API or schema migrations."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[3]


def main():
    checks = []
    def passed(name):
        checks.append({'name': name, 'passed': True})
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'],
                            cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    passed('existing_16_test_methods_on_python314')
    schema = json.loads((ROOT / 'contracts/schemas/synthetic-bundle-v0.1.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    mapping = {'package': 'package', 'truth': 'truth', 'release': 'release',
               'ontology': 'ontology', 'objects': 'objects', 'human': 'view', 'agent': 'view'}
    for name, definition in mapping.items():
        variant = {**schema, '$ref': '#/$defs/' + definition}
        document = json.loads((ROOT / f'examples/indoor/{name}.json').read_text(encoding='utf-8'))
        Draft202012Validator(variant).validate(document)
    passed('standard_schema_engine_all_7_documents')
    file_schema = {**schema, '$ref': '#/$defs/file'}
    base = {'path': 'x.json', 'bytes': 1.0, 'sha256': 'a' * 64, 'media_type': 'application/json'}
    Draft202012Validator(file_schema).validate(base)
    assert list(Draft202012Validator(file_schema).iter_errors({**base, 'bytes': True}))
    passed('schema_integer_float_difference_recorded_boolean_rejected')

    class Request(BaseModel):
        model_config = ConfigDict(extra='forbid', strict=True)
        release_id: str
    app = FastAPI()
    @app.post('/evaluate')
    def evaluate(request: Request):
        return {'release_id': request.release_id, 'data_kind': 'synthetic'}
    with TestClient(app) as client:
        assert client.post('/evaluate', json={'release_id': 'fixed-001'}).json()['release_id'] == 'fixed-001'
        assert client.post('/evaluate', json={'release_id': 42}).status_code == 422
        assert client.post('/evaluate', json={'release_id': 'x', 'extra': True}).status_code == 422
        assert client.get('/openapi.json').json()['openapi'].startswith('3.1')
    passed('fastapi_pydantic_http_openapi_and_rejection')

    db = os.environ.get('COSPACE_EVAL_DATABASE_URL')
    if db:
        engine = create_engine(db)
        with engine.begin() as conn:
            version = conn.execute(text('show server_version')).scalar_one()
            assert version.split('.')[0] == '18', version
            conn.execute(text('create table release_eval (id integer primary key, current_release text not null)'))
            conn.execute(text("insert into release_eval values (1, 'old')"))
        with engine.connect() as conn:
            transaction = conn.begin()
            assert conn.execute(text("update release_eval set current_release='new' where id=1 and current_release='old'")).rowcount == 1
            transaction.rollback()
            assert conn.execute(text('select current_release from release_eval where id=1')).scalar_one() == 'old'
            conn.rollback()
        with engine.begin() as conn:
            assert conn.execute(text("update release_eval set current_release='new' where id=1 and current_release='old'")).rowcount == 1
            assert conn.execute(text("update release_eval set current_release='other' where id=1 and current_release='old'")).rowcount == 0
        engine.dispose()
        passed('postgres18_psycopg_sqlalchemy_commit_rollback_conditional_switch')
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'dependencies': {name: importlib.metadata.version(name) for name in
                 ('fastapi', 'pydantic', 'jsonschema', 'sqlalchemy', 'alembic', 'psycopg', 'pytest', 'uvicorn')},
              'checks': checks, 'passed': True, 'database_executed': bool(db),
              'limits': ['No production API or migration implementation',
                         'No concurrent crash/recovery or real spatial performance validation']}
    output = ROOT / 'experiments/stack/results'
    output.mkdir(exist_ok=True)
    (output / ('python-db.json' if db else 'python.json')).write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
