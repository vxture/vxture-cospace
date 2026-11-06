"""Explicit local scan to a separate archive. No Web write operation or source repair."""
import argparse
import json
import sys

from experiments.scripts.delivery_audit import DeliveryAudit
from packages.infrastructure.delivery_reports import publish, separate_output
from packages.infrastructure.files import bounded_read
from packages.service.sample import read_json


def generate(files, journal, binding_path, output, limit=100):
    # Check before scanning or creating output. All source paths are explicit operator inputs.
    output = separate_output(output, [files, journal, binding_path])
    report = DeliveryAudit(files, journal).scan(read_json(bounded_read(binding_path)), limit)
    receipt = publish(output, report)
    receipt.update(complete=report['complete'], needs_attention=report['needs_attention'])
    return receipt


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('files', 'journal', 'binding', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    try:
        receipt = generate(args.files, args.journal, args.binding, args.output, args.limit)
    except (OSError, ValueError) as error:
        print(json.dumps({'error': str(error), 'authorized': False}))
        return 2
    print(json.dumps(receipt))
    return 0 if receipt['complete'] and not receipt['needs_attention'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
