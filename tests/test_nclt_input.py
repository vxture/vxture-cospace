import hashlib
import pytest
from packages.data.nclt_input import inspect_ms25


def fixture(times=(1357847237276758,1357847237276759)):
    return ''.join(str(t)+',1,2,3,4,5,6,7,8,9\n' for t in times).encode()


def test_exact_integer_time_and_declared_columns():
    raw=fixture(); report=inspect_ms25(raw,hashlib.sha256(raw).hexdigest())
    assert report['structural_precheck_passed'] and report['input']['expected_digest_verified']
    assert report['valid_rows']==2 and report['time']['min_positive_delta_us']==1
    assert report['time']['start_us']==1357847237276758
    assert report['columns'][4]=={'name':'accel_x','declared_unit':'m/s^2'}
    assert report['ranges']['accel_x']==[4,4]
    assert report['algorithm_ready'] is False and report['real_release_ready'] is False


@pytest.mark.parametrize('raw,code',[(b'','insufficient_rows'),(b'1,2\n','column_count'),
    (fixture().replace(b',1,',b',nan,'),'non_finite_value'),
    (fixture().replace(b',1,',b',inf,'),'non_finite_value'),
    (fixture().replace(b',1,',b',unknown,'),'invalid_numeric'),
    (b'0,1,2,3,4,5,6,7,8,9\n','invalid_timestamp'),
    (b'1.5,1,2,3,4,5,6,7,8,9\n','invalid_timestamp'),
    (b'\xff','csv_decode_failed'),(b'"unclosed','csv_decode_failed'),
    (fixture((2,1)),'non_increasing_time'),(fixture((2,2)),'non_increasing_time')])
def test_failures(raw,code):
    report=inspect_ms25(raw)
    assert not report['structural_precheck_passed']
    assert code in {e['code'] for e in report['errors']}


def test_missing_rows_not_silently_repaired():
    report=inspect_ms25(fixture()+b'broken\n'+fixture((1357847237276760,)))
    assert report['valid_rows']==3 and report['invalid_rows']==1
    assert not report['structural_precheck_passed']


def test_digest_mismatch_before_parse():
    report=inspect_ms25(fixture(),'0'*64)
    assert report['errors']==[{'code':'input_digest_mismatch','row':None}]
    assert report['valid_rows']==0


@pytest.mark.parametrize('limit,code',[('MAX_BYTES','file_budget'),('MAX_ROWS','row_budget')])
def test_budgets(monkeypatch,limit,code):
    monkeypatch.setattr('packages.data.nclt_input.'+limit,1)
    report=inspect_ms25(fixture())
    assert code in {e['code'] for e in report['errors']}


def test_diagnostic_bound_and_wrong_python_type():
    report=inspect_ms25(b'invalid\n'*100)
    assert len(report['errors'])==32 and report['invalid_rows']==100
    with pytest.raises(ValueError,match='bytes_required'): inspect_ms25('not bytes')
