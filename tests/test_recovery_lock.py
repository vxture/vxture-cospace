"""Independent J1 process/ownership contract, not a real validity or recovery path."""
import os

import pytest

from experiments.scripts.check_recovery_lock import CASES
from experiments.scripts.recovery_lock_probe import ControlProbe, LockError, StableLock

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows LockFileEx required')


@pytest.mark.parametrize('case', CASES)
def test_j1_real_process_and_control(case, tmp_path):
    CASES[case](tmp_path / case)


def test_failed_open_never_bootstraps_and_wrong_context_rejected(tmp_path):
    missing = tmp_path / 'absent'
    with pytest.raises(OSError):
        ControlProbe(missing, 'a' * 64)
    assert not missing.exists()
    root = tmp_path / 'existing'
    ControlProbe.bootstrap(root, 'a' * 64)
    with pytest.raises(LockError, match='context_changed'):
        ControlProbe(root, 'b' * 64)
    with pytest.raises(FileExistsError):
        ControlProbe.bootstrap(root, 'a' * 64)


def test_same_process_handles_conflict_and_invalid_timeout(tmp_path):
    path = tmp_path / 'lock'
    with StableLock(path).hold(create=True):
        with pytest.raises(LockError, match='busy'):
            with StableLock(path).hold(0):
                pass
    for value in (-1, True, float('nan'), 6):
        with pytest.raises(LockError, match='invalid_timeout'):
            with StableLock(path).hold(value):
                pass


def test_generation_does_not_wrap(tmp_path):
    import sqlite3
    root = tmp_path / 'exhausted'
    probe = ControlProbe.bootstrap(root, 'a' * 64)
    with sqlite3.connect(probe.path) as db:
        db.execute('UPDATE control SET generation=?', (9007199254740991,))
    latest = ControlProbe(root, 'a' * 64)
    with pytest.raises(LockError, match='generation_exhausted'):
        latest.operation('begin_recovery')
    with sqlite3.connect(latest.path) as db:
        assert db.execute('SELECT generation,mode FROM control').fetchone() == (9007199254740991, 'normal')
