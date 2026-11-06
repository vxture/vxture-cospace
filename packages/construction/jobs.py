"""Fixed synthetic checks. No candidate creation, adoption or release activation."""
from packages.construction.errors import JobError
from pathlib import Path
import json
from jsonschema import Draft202012Validator


def validate(spec):
    schema = json.loads((Path(__file__).resolve().parents[2] / 'contracts/schemas/check-job-v0.1.schema.json').read_text(encoding='utf-8'))
    if not Draft202012Validator(schema).is_valid(spec):
        raise JobError('invalid_specification', 'unsupported or invalid fixed check specification')


class JobManager:
    def __init__(self, store, inputs, runner):
        self.store, self.inputs, self.runner = store, inputs, runner

    def submit(self, dataset_id, actor, timeout_seconds=120, log_limit_bytes=8388608):
        if not actor.strip() or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
            raise JobError('invalid_request', 'actor and timeout (1..120 seconds) required')
        if type(log_limit_bytes) is not int or not 1024 <= log_limit_bytes <= 8388608:
            raise JobError('invalid_request', 'log limit must be 1024..8388608 bytes')
        dataset = self.inputs.dataset(dataset_id)
        spec = {'schema_version': 'cospace.job/0.1', 'kind': 'synthetic_check', 'executor': 'synthetic_check/0.1',
                'dataset_id': dataset_id, 'dataset_sha256': dataset['sha256'], 'scene_id': dataset['manifest']['scene_id'],
                'config': {'timeout_seconds': timeout_seconds, 'log_limit_bytes': log_limit_bytes},
                'environment': self.runner.fingerprint()}
        validate(spec)
        return self.store.submit(spec, actor)

    def run(self, identity, revision):
        record = self.store.get(identity)
        attempt = self.store.claim(identity, revision)
        stage = 'preflight'
        try:
            spec = record['spec']
            validate(spec)
            if spec['executor'] != 'synthetic_check/0.1' or spec['kind'] != 'synthetic_check':
                raise JobError('executor_unavailable', 'unsupported fixed executor')
            if self.runner.fingerprint() != spec['environment']:
                raise JobError('environment_mismatch', 'fixed runtime changed; submit a new job')
            dataset = self.inputs.dataset(spec['dataset_id'])
            if dataset['sha256'] != spec['dataset_sha256']:
                raise JobError('input_mismatch', 'fixed dataset digest changed')
            stage = 'execution'
            artifact = self.runner.execute(identity, attempt, spec, dataset['manifest'])
        except (ValueError, OSError) as error:
            self.store.finish(identity, attempt, diagnostic={'stage': stage,
                'code': getattr(error, 'code', 'execution_error'), 'message': 'check failed; no candidate or release produced',
                'attempt_id': attempt})
            return self.store.get(identity)
        # A database failure after sealing leaves running + an orphan artifact.
        # Do not reclassify it as an execution failure or auto-resume.
        self.store.finish(identity, attempt, artifact=artifact)
        return self.store.get(identity)

    def report(self, identity):
        record = self.store.get(identity)
        if record['state'] != 'succeeded':
            raise JobError('artifact_unavailable', 'job has no successful report')
        artifact = record['attempts'][0]['artifact']
        return self.runner.report(artifact)
