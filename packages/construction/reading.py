"""Read-only job projections, independent of current service release pointers."""
from packages.construction.errors import JobError
from packages.data.imports import ImportError


class JobReader:
    def __init__(self, store, inputs, runner):
        self.store, self.inputs, self.runner = store, inputs, runner

    def list(self, scene, limit, offset):
        return self.store.list(scene, limit, offset)

    def detail(self, scene, identity):
        record = self.store.get(identity)
        if record['spec']['scene_id'] != scene:
            raise JobError('job_not_found', 'job not found in requested scene')
        return {'scene_id': scene, **record}

    def dataset(self, scene, identity):
        record = self.detail(scene, identity)
        try:
            dataset = self.inputs.dataset(record['spec']['dataset_id'])
        except ImportError as error:
            raise JobError('content_corrupt', 'fixed dataset is missing or invalid') from error
        if dataset['sha256'] != record['spec']['dataset_sha256'] or dataset['manifest']['scene_id'] != scene:
            raise JobError('content_corrupt', 'dataset does not match fixed job input')
        return {'scene_id': scene, 'job_id': identity, 'spec_sha256': record['sha256'],
                'dataset_sha256': dataset['sha256'], 'manifest': dataset['manifest']}

    def report(self, scene, identity):
        record = self.detail(scene, identity)
        if record['state'] != 'succeeded' or len(record['attempts']) != 1:
            raise JobError('artifact_unavailable', 'job has no successful report')
        attempt = record['attempts'][0]
        artifact = attempt['artifact']
        if not artifact or artifact.get('spec_sha256') != record['sha256']:
            raise JobError('content_corrupt', 'artifact does not match job specification')
        report = self.runner.report(artifact)
        if (report.get('job_id') != identity or report.get('attempt_id') != attempt['attempt_id']
                or report.get('spec_sha256') != record['sha256']
                or report.get('dataset_sha256') != record['spec']['dataset_sha256']):
            raise JobError('content_corrupt', 'report does not match fixed job context')
        return {'scene_id': scene, 'job_id': identity, 'spec_sha256': record['sha256'],
                'artifact': artifact, 'report': report}
