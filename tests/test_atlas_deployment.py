import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('configure_atlas', Path(__file__).resolve().parents[1] / 'deploy/linux/configure_atlas.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
GOOD = {'COSPACE_ATLAS_BASE_URL': 'http://100.76.219.48:3100',
        'COSPACE_ATLAS_COORDINATE_ENDPOINT': 'chat/extract', 'COSPACE_ATLAS_TAILNET_HTTP': '1'}


def test_install_preserve_disable_and_no_partial_write(tmp_path):
    target = tmp_path / 'atlas.env'
    assert module.install(tmp_path, GOOD) == 'enabled'
    before = target.read_bytes()
    assert before == b'COSPACE_ATLAS_BASE_URL=http://100.76.219.48:3100\nCOSPACE_ATLAS_COORDINATE_ENDPOINT=chat/extract\nCOSPACE_ATLAS_TAILNET_HTTP=1\n'
    assert module.install(tmp_path, {}) == 'preserved'
    assert target.read_bytes() == before
    with pytest.raises(ValueError):
        module.install(tmp_path, GOOD | {'COSPACE_ATLAS_COORDINATE_ENDPOINT': 'route\nINJECT=1'})
    assert target.read_bytes() == before
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600
    assert module.install(tmp_path, {'COSPACE_ATLAS_BASE_URL': 'disabled'}) == 'disabled'
    assert b'COSPACE_ATLAS_BASE_URL=\n' in target.read_bytes()


@pytest.mark.parametrize('change', [
    {'COSPACE_ATLAS_BASE_URL': 'http://public.example'},
    {'COSPACE_ATLAS_BASE_URL': 'http://127.0.0.1:3100'},
    {'COSPACE_ATLAS_BASE_URL': 'https://atlas.example/path'},
    {'COSPACE_ATLAS_BASE_URL': 'https://user:secret@atlas.example'},
    {'COSPACE_ATLAS_BASE_URL': 'https://atlas.example\nINJECT=1'},
    {'COSPACE_ATLAS_BASE_URL': 'https://atlas.example:99999'},
    {'COSPACE_ATLAS_BASE_URL': ''}, {'COSPACE_ATLAS_COORDINATE_ENDPOINT': ''},
    {'COSPACE_ATLAS_TAILNET_HTTP': '0'},
])
def test_reject_invalid_origin_and_incomplete_or_injected_settings(change):
    with pytest.raises(ValueError):
        module.settings(GOOD | change)


@pytest.mark.skipif(os.name == 'nt', reason='production symlink permissions are Linux-specific')
def test_refuse_symlink_without_touching_destination(tmp_path):
    destination = tmp_path / 'other'
    destination.write_text('keep')
    (tmp_path / 'atlas.env').symlink_to(destination)
    with pytest.raises(ValueError):
        module.install(tmp_path, GOOD)
    assert destination.read_text() == 'keep'
