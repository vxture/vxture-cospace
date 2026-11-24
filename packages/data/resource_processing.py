"""Bounded metadata-only processing graph. No payload reads, polling or exports."""
from datetime import datetime, timezone
import re

from packages.data.input_coordinates import InputCoordinates
from packages.data.resource_governance import GovernanceQuery
from packages.data.resource_lineage import ResourceLineage
from packages.data.workspace_catalog import metadata, MAX_RECORDS
from packages.lifecycle.preview_scope import owned
from packages.lifecycle.workspace_projects import ProjectUnavailable
from packages.construction.build_admission import match_source


CANDIDATE_PREFIX = 'candidate:'


class ProcessingGraph:
    def __init__(self, jobs, ownership):
        self.jobs, self.ownership = jobs, ownership
        self.nodes, self.edges, self.issues = {}, [], set()
        self.inputs, self.models, self.job_records = {}, {}, {}

    def scan(self, root, pattern, kind):
        count = 0
        for path in root.glob(pattern):
            count += 1
            if count > MAX_RECORDS:
                raise ProjectUnavailable('resource_processing_budget')
            try:
                record = metadata(root, path)
                if owned(record) != self.ownership:
                    continue
                identity = path.stem if kind == 'input' else path.parent.name
                prefix = {'input': r'input-[a-f0-9]{16}', 'job': r'build-[A-Za-z0-9-]+',
                          'publication': r'preview-[a-f0-9]{16}'}[kind]
                if record.get('id') != identity or not re.fullmatch(prefix, identity):
                    raise ValueError('identity_invalid')
                yield identity, record
            except (OSError, ValueError, KeyError, TypeError):
                # No identifiers, paths or metadata from inaccessible sources.
                self.issues.add(kind + '_metadata_unavailable')

    def node(self, kind, identity, state, digest=None):
        key = kind + ':' + identity
        self.nodes[key] = {'key': key, 'kind': kind, 'record_id': identity,
                           'state': state, 'metadata_sha256': digest}
        if len(self.nodes) > MAX_RECORDS:
            raise ProjectUnavailable('resource_processing_budget')
        return key

    def edge(self, origin, target, relation, matched):
        local = target if target in self.nodes else None
        self.edges.append({'from': origin, 'to': local, 'relation': relation,
                           'status': 'matched' if local and matched else 'unresolved'})

    def input_match(self, binding):
        return isinstance(binding, dict) and binding in self.inputs.get(binding.get('id'), [])

    def read_inputs(self):
        if self.jobs.inputs is None:
            self.issues.add('input_binding_unavailable')
            return
        for identity, record in self.scan(self.jobs.inputs.root, 'input-*.json', 'input'):
            self.node('input', identity, 'registered')
            try:
                if record.get('profile') != 'cospace.preview-input/0.1':
                    raise ValueError('input_invalid')
                self.inputs[identity] = [{k: v for k, v in r.items() if k not in ('snapshot', 'tracking')}
                                         for r in InputCoordinates(self.jobs.inputs).fixed_records(record)]
            except (ValueError, OSError, KeyError, TypeError):
                self.issues.add('input_binding_unavailable')

    @staticmethod
    def source_keys(binding):
        if binding and binding.get('format') == 'ply_pointcloud':
            return ('snapshot_sha256', 'cloud_sha256')
        if binding and binding.get('format') in ('ros1_lidar_single_frame', 'ros1_lidar_multiframe_icp'):
            return ('snapshot_sha256', 'bag_sha256', 'selected_frame')
        return ('snapshot_sha256', 'tracking_sha256')

    def candidate_model(self, identity, record, binding, matches):
        model, digest = metadata(self.jobs.root, self.jobs.root / identity / 'output/model.json', with_digest=True)
        if not isinstance(model.get('source'), dict) or not isinstance(model.get('members'), dict):
            raise ValueError('model_metadata_invalid')
        source = model['source']
        if (model.get('profile') != 'cospace.real-model-preview/0.1' or model.get('id') != identity or owned(model) != self.ownership or
                source.get('input_binding') != binding or source.get('batch_ref') != record.get('batch_ref')):
            raise ValueError('model_binding_mismatch')
        match_source(record, source)
        if not matches or not all(k in binding and binding[k] == source.get(k) for k in self.source_keys(binding)):
            raise ValueError('source_binding_mismatch')
        return model, digest

    def read_views(self, identity, model, candidate):
        for kind in ('human_view', 'agent_view'):
            view = model.get(kind)
            if not isinstance(view, dict):
                continue
            member = model['members'].get(view.get('path'))
            if not isinstance(member, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(member.get('sha256', ''))):
                self.issues.add('view_member_unavailable')
                continue
            view_key = self.node(kind, identity, 'declared', member['sha256'])
            self.edge(view_key, candidate, 'expresses', True)

    def read_candidate(self, identity, record, binding, matches, job_key):
        try:
            model, digest = self.candidate_model(identity, record, binding, matches)
            self.models[identity] = (model, digest)
            candidate = self.node('candidate', identity, 'metadata_matched', digest)
            self.edge(candidate, job_key, 'produced_by', True)
            self.read_views(identity, model, candidate)
        except (OSError, ValueError, KeyError, TypeError):
            self.issues.add('candidate_metadata_or_binding_unavailable')
            self.edge(job_key, None, 'output_unresolved', False)

    def read_jobs(self):
        for identity, record in self.scan(self.jobs.root, '*/job.json', 'job'):
            state = record.get('state')
            if state not in ('queued', 'running', 'succeeded', 'failed', 'interrupted', 'views_failed'):
                state = 'unknown'
            key = self.node('job', identity, state)
            self.job_records[identity] = record
            binding = record.get('input_binding')
            input_id = record.get('input_id')
            matches = self.input_match(binding) and binding['id'] == input_id
            self.edge(key, 'input:' + input_id if isinstance(input_id, str) else None, 'consumes', matches)
            if state == 'succeeded':
                self.read_candidate(identity, record, binding, matches, key)

    def read_derivations(self):
        for identity, (model, _) in self.models.items():
            annotation = model.get('semantic_annotation')
            if not annotation:
                continue
            base = annotation.get('base_candidate_ref', {}) if isinstance(annotation, dict) else {}
            candidate = base.get('candidate_id')
            job = self.job_records[identity]
            target = self.models.get(candidate) if isinstance(candidate, str) else None
            matches = (target is not None and target[1] == base.get('model_manifest_sha256') and
                       job.get('base_candidate_id') == candidate and job.get('base_manifest_sha256') == target[1])
            self.edge(CANDIDATE_PREFIX + identity, CANDIDATE_PREFIX + candidate if isinstance(candidate, str) else None,
                      'derived_from', matches)

    def read_publications(self):
        for identity, record in self.scan(self.jobs.root / 'publications', '*/publication.json', 'publication'):
            key = self.node('publication', identity, 'fixed_record')
            candidate = record.get('candidate_id')
            target = self.models.get(candidate) if isinstance(candidate, str) else None
            matches = (record.get('profile') == 'cospace.local-preview-publication/0.1' and target is not None and
                       target[1] == record.get('model_manifest_sha256'))
            try:
                fixed, digest = metadata(self.jobs.root, self.jobs.root / 'publications' / identity / 'model.json', with_digest=True)
                matches = (matches and digest == record.get('model_manifest_sha256') and
                           fixed.get('id') == candidate and owned(fixed) == self.ownership)
            except (OSError, ValueError, KeyError, TypeError):
                matches = False
            self.edge(key, CANDIDATE_PREFIX + candidate if isinstance(candidate, str) else None, 'published_from', matches)

    def connected(self, focus):
        adjacency = {}
        for edge in self.edges:
            if edge['to']:
                adjacency.setdefault(edge['from'], set()).add(edge['to'])
                adjacency.setdefault(edge['to'], set()).add(edge['from'])
        keys = {focus}
        pending = [focus]
        while pending:
            for key in adjacency.get(pending.pop(), ()):
                if key not in keys:
                    keys.add(key)
                    pending.append(key)
        order = {kind: i for i, kind in enumerate(('input', 'job', 'candidate', 'human_view', 'agent_view', 'publication'))}
        nodes = sorted((v for k, v in self.nodes.items() if k in keys), key=lambda n: (order[n['kind']], n['record_id']))
        edges = [e for e in self.edges if e['from'] in keys]
        return nodes, sorted(edges, key=lambda e: (e['from'], e['relation']))


class ResourceProcessing:
    def __init__(self, resources):
        self.resources, self.projects = resources, resources.projects

    def read(self, principal, policy, query: GovernanceQuery):
        with self.projects.database() as db:
            resource = ResourceLineage(self.resources).registration(db, self.projects.scope(principal), query.resource_id)
            self.resources.sharing.require_source(principal, policy, resource)
        report = {'profile': 'cospace.resource-processing/0.1', 'workspace_id': principal.workspace_id,
                  'resource_id': query.resource_id, 'nodes': [], 'edges': [], 'issues': [], 'focus': None,
                  'status': 'not_applicable', 'source_files_rechecked': False, 'jobs_polled': False,
                  'consistency': 'request_time_metadata_reads_not_transactional',
                  'observed_at': datetime.now(timezone.utc).isoformat()}
        space = resource['space_id']
        if space is None:
            return report
        prefix, _, identity = resource['source_key'].partition('/')
        kind, _, record_id = identity.partition(':')
        if prefix != space or kind not in ('input', 'candidate', 'human_view', 'agent_view', 'attachment'):
            raise ProjectUnavailable('resource_processing_source_invalid')
        if kind == 'attachment':
            return report
        # Task and publication records have stronger read scopes than raw inputs.
        policy.require(principal, space, 'build.run')
        policy.require(principal, space, 'publication.manage')
        scene = self.resources.directory.read('space', space)
        graph = ProcessingGraph(self.resources.jobs, {'space_id': space, 'project_id': scene['project_id']})
        graph.read_inputs()
        graph.read_jobs()
        graph.read_derivations()
        graph.read_publications()
        focus = kind + ':' + record_id
        nodes, edges = graph.connected(focus)
        if focus not in graph.nodes:
            graph.issues.add('source_metadata_unavailable')
        partial = bool(graph.issues) or any(e['status'] != 'matched' for e in edges)
        return report | {'nodes': nodes, 'edges': edges, 'focus': focus if focus in graph.nodes else None,
                         'issues': sorted(graph.issues), 'status': 'partial' if partial else 'ready'}
