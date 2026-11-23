"""Summarize saved synthetic results without treating a pilot as enablement evidence."""
import argparse
import json
from pathlib import Path

import numpy as np


def summarize(evidence):
    rows = evidence['rows']
    summaries = []
    quality = True
    for sample in sorted({r['sample'] for r in rows}):
        group = [r for r in rows if r['sample'] == sample]
        reference = next(r for r in group if r['strategy'] == 'baseline')
        for strategy in ('baseline', 'task', 'adaptive', 'governance', 'combined'):
            selected = [r for r in group if r['strategy'] == strategy]
            if not selected:
                continue
            correct = all(r[phase]['pointBudget'] == 500000 and r[phase]['nodePixels'] == 30
                          and r[phase]['points'] == reference[phase]['points']
                          and r[phase]['viewSignature'] == reference[phase]['viewSignature']
                          and r[phase]['cameraSignature'] == reference[phase]['cameraSignature']
                          and r[phase]['exactValid'] and r[phase]['accounting_complete']
                          and not r[phase]['strategyFallback']
                          for r in selected for phase in ('initial', 'final'))
            quality &= correct
            metrics = {k: {name: float(np.percentile([r['metrics'][k] for r in selected], p))
                           for name, p in [('p50', 50), ('p75', 75), ('p95', 95)]}
                       for k in reference['metrics']}
            summaries.append({'sample': sample, 'strategy': strategy, 'n': len(selected),
                              'same_quality_and_exact': correct, 'metrics': metrics})
    # Peak CPU/GPU memory and representative production runs are not captured by
    # this lab. Even 30 repeats here alone cannot auto-enable a production policy.
    return {'quality_passed': quality and len(summaries) == 10,
            'pilot': len(summaries) != 10 or any(s['n'] < 30 for s in summaries),
            'enablement_gate_passed': False,
            'limitations': ['synthetic-only', 'peak CPU/GPU memory not measured',
                            'no automatic production enablement or industry superiority claim'],
            'summaries': summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.evidence.read_text(encoding='utf-8'))), indent=2))


if __name__ == '__main__':
    main()
