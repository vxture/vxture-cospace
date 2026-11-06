"""Scan exactly the Git index, including nested archives. Requires gitleaks 8.30+."""
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('output/github-candidate-gitleaks.json'))
    args = parser.parse_args()
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip())
    report = args.report.resolve()
    # Reports are local evidence, even though matched values are redacted.
    if not report.is_relative_to(root / 'output'):
        parser.error('report must stay under the ignored output directory')
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cospace-index-scan-') as temporary:
        prefix = Path(temporary).as_posix() + '/'
        subprocess.run(['git', 'checkout-index', '--all', '--prefix=' + prefix], check=True, cwd=root)
        subprocess.run([sys.executable, str(root / 'scripts/security/expand_archives.py'),
                        temporary, str(Path(temporary) / '.archive-inspection')], check=True)
        result = subprocess.run([
            'gitleaks', 'dir', temporary, '--config', str(root / '.gitleaks.toml'),
            '--max-archive-depth', '3', '--max-decode-depth', '5', '--ignore-gitleaks-allow',
            '--redact', '--no-banner', '--report-format', 'json', '--report-path', str(report),
        ], cwd=root)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
