"""Check design-only recovery record shapes; never verifies commit/recovery semantics."""
import copy
import hashlib
import json
from pathlib import Path
import platform

from jsonschema import Draft202012Validator
from packages.data.structure import LiteralIntegerValidator


ROOT = Path(__file__).resolve().parents[2]


def main():
    schema_path = ROOT / 'contracts/schemas/recovery-journal-v0.1.schema.json'
    sample_path = ROOT / 'examples/recovery-journal/records.json'
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator = LiteralIntegerValidator(schema)
    records = json.loads(sample_path.read_text(encoding='utf-8'))
    results = []
    for name, record in records.items():
        errors = list(validator.iter_errors(record))
        assert not errors, (name, [e.message for e in errors])
        results.append({'case': name, 'expected': 'accepted_shape', 'passed': True})
    changes = [
        ('unknown_field', 'intent', {'extra': 1}),
        ('zero_generation', 'intent', {'generation': 0}),
        ('boolean_generation', 'intent', {'generation': True}),
        ('float_generation', 'intent', {'generation': 1.0}),
        ('counter_overflow', 'intent', {'prepared_revision': 9007199254740992}),
        ('authorization_escalation', 'intent', {'authorized': True}),
        ('robot_ready_escalation', 'intent', {'robot_ready': True}),
        ('production_flag', 'intent', {'test_only': False}),
        ('malformed_digest', 'intent', {'token_sha256': 'bad'}),
        ('oversized_token', 'intent', {'token': 'a' * 49153}),
        ('unknown_record_kind', 'receipt', {'record_kind': 'grant'}),
        ('unknown_outcome', 'receipt', {'outcome': 'authorized'}),
        ('too_many_plan_items', 'plan', {'items': records['plan']['items'] * 201}),
        ('empty_plan', 'plan', {'items': []}),
        ('unknown_phase', 'result', {'phase': 'running_robot'})]
    for name, base, changed in changes:
        record = copy.deepcopy(records[base])
        record.update(changed)
        assert not validator.is_valid(record), name
        results.append({'case': name, 'expected': 'rejected_shape', 'passed': True})
    missing = copy.deepcopy(records['intent'])
    missing.pop('store_id')
    assert not validator.is_valid(missing)
    results.append({'case': 'missing_store_identity', 'expected': 'rejected_shape', 'passed': True})
    output = ROOT / 'experiments/runs/p2-recovery-contract-001'
    output.mkdir(parents=True, exist_ok=True)
    source_paths = [schema_path, sample_path, Path(__file__).resolve()]
    evidence = {'test_only': True, 'schema_valid': True, 'positive_shapes': len(records),
                'negative_shapes': len(results) - len(records), 'cases': results,
                'protocol_verified': False, 'signatures_verified': False,
                'authorized': False, 'robot_ready': False,
                'python': platform.python_version(),
                'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in source_paths}}
    (output / 'report.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(records)} positive and {len(results)-len(records)} negative shapes passed; protocol unverified')


if __name__ == '__main__':
    main()
