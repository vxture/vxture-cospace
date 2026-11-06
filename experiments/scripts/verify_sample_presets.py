"""Verify real local preset files and per-scene registration in a temporary catalog."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from packages.data.preview_inputs import PreviewInputs, inspect
from packages.data.preview_registration import PreviewRegistration
from packages.data.preview_source_config import load_sources
from packages.lifecycle.preview_spaces import PreviewSpaces


def verify():
    sources, _ = load_sources('deploy/config/preview-sources.json', Path.cwd())
    report = {'scope': 'local_workflow_samples_not_quality_acceptance', 'samples': [], 'checks': {}}
    with TemporaryDirectory(prefix='cospace-preset-check-') as scratch:
        root = Path(scratch)
        directory = PreviewSpaces(root/'directory')
        project = directory.create('project', 'Isolated sample validation')
        spaces = [directory.create('space', name, project['id'])['id'] for name in ('A', 'B')]
        inputs = PreviewInputs(root/'inputs', directory)
        registration = PreviewRegistration(inputs, sources)
        for key in ('nyu-office-short', 'os1-single-frame'):
            source = sources[key]
            checked = inspect(source['snapshot'], source.get('tracking'), source['format'])
            first = registration.register(key, source['label'], spaces[0])
            repeated = registration.register(key, 'A different display label', spaces[0])
            other = registration.register(key, source['label'], spaces[1])
            assert first['created'] and other['created'] and not repeated['created']
            assert first['input']['id'] == repeated['input']['id'] != other['input']['id']
            assert repeated['input']['label'] == source['label']
            assert PreviewInputs(root/'inputs', directory).resolve(first['input']['id'])['space_id'] == spaces[0]
            report['samples'].append({'source_id': key, 'format': source['format'], 'verified': checked,
                                     'repeat_reused_record': True, 'scene_isolation': True, 'restart_read': True})
        assert len(inputs.list()) == 4
        report['checks']['two_samples_two_spaces_four_records'] = True
        report['checks']['no_build_or_publication_created'] = not (root/'preview-builds').exists()
    # The original engineering lifecycle records remain untouched.
    baseline = json.loads(Path('experiments/evidence/2026-11-03/preview-lifecycle-h3c-001/original-before.json').read_bytes())
    current = {str(p).replace('\\', '/') for name in ('preview-builds', 'preview-directory', 'preview-inputs', 'preview-ontologies')
               for p in (Path('var/nyu')/name).rglob('*') if p.is_file()}
    assert current == set(baseline)
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in baseline.items())
    report['checks']['original_records_unchanged'] = len(baseline)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result['checks'], ensure_ascii=False))
