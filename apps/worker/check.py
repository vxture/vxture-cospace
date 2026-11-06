"""Fixed child process. Reads only a copied synthetic input, writes one report."""
import argparse
from pathlib import Path
from packages.data.imports import canonical
from packages.infrastructure.files import bounded_read
from packages.service.sample import inspect_package, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    root = Path(args.directory)
    try:
        context = read_json(bounded_read(root / 'context.json'))
        report, _ = inspect_package(root / 'input')
        result = {'schema_version': 'cospace.check-report/0.1', 'job_id': context['job_id'],
                  'attempt_id': context['attempt_id'], 'spec_sha256': context['spec_sha256'],
                  'dataset_sha256': context['dataset_sha256'], 'data_kind': 'synthetic',
                  'validation': report, 'candidate_created': False, 'truth_created': False,
                  'not_executed': ['slam', 'field_quality', 'localization', 'adoption', 'publication']}
        (root / 'validation_report.json').write_bytes(canonical(result))
        print('synthetic_check completed; no candidate created')
        return 0
    except (OSError, ValueError, KeyError):
        print('synthetic_check failed; input or report invalid')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
