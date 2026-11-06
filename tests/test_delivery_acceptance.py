"""Acceptance evidence cannot turn failures, skipped browser work or old runs into a pass."""
import json
from pathlib import Path

import pytest

import experiments.scripts.delivery_acceptance as acceptance


@pytest.fixture
def exercise_harness(monkeypatch):
    # These tests inject the exercise to test evidence bookkeeping, not OS APIs.
    monkeypatch.setattr(acceptance, '_require_windows', lambda: None)


def test_real_exercise_still_rejects_unsupported_platform(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(acceptance, 'os', SimpleNamespace(name='posix'))
    with pytest.raises(acceptance.AcceptanceFailure, match='windows_required'):
        acceptance._require_windows()


def test_existing_run_never_overwritten(tmp_path):
    marker = tmp_path / 'acceptance.json'
    marker.write_text('previous evidence', encoding='utf-8')
    with pytest.raises(FileExistsError): acceptance.run(tmp_path)
    assert marker.read_text(encoding='utf-8') == 'previous evidence'


def test_failed_check_retained_and_no_acceptance_promotion(tmp_path, monkeypatch, exercise_harness):
    def exercise(output, checks):
        acceptance.record(checks, 'injected.first', True)
        acceptance.record(checks, 'injected.failure', False, actual=503)
    monkeypatch.setattr(acceptance, '_exercise', exercise)
    result = acceptance.run(tmp_path / 'failed-run')
    assert not result['passed'] and len(result['checks']) == 2
    assert result['failure']['check_id'] == 'injected.failure'
    saved = json.loads((tmp_path / 'failed-run/acceptance.json').read_text(encoding='utf-8'))
    assert saved == result and not saved['authorized'] and not saved['browser_executed']


def test_exception_text_not_persisted(tmp_path, monkeypatch, exercise_harness):
    def exercise(output, checks): raise RuntimeError('secret-test-seed-must-not-be-saved')
    monkeypatch.setattr(acceptance, '_exercise', exercise)
    result = acceptance.run(tmp_path / 'exception-run')
    assert not result['passed'] and result['failure']['type'] == 'RuntimeError'
    assert 'secret-test-seed' not in (tmp_path / 'exception-run/acceptance.json').read_text(encoding='utf-8')


def test_empty_exercise_is_not_success(tmp_path, monkeypatch, exercise_harness):
    monkeypatch.setattr(acceptance, '_exercise', lambda output, checks: None)
    assert not acceptance.run(tmp_path / 'empty-run')['passed']


def test_passing_subset_cannot_claim_workflow_acceptance(tmp_path, monkeypatch, exercise_harness):
    def exercise(output, checks): acceptance.record(checks, acceptance.REQUIRED_CHECKS[0], True)
    monkeypatch.setattr(acceptance, '_exercise', exercise)
    result = acceptance.run(tmp_path / 'partial-run')
    assert not result['passed'] and result['failure']['check_id'] == 'required_check_coverage_incomplete'
