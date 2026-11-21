"""Install non-secret Atlas settings during the reviewed deployment; blank means preserve."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


def settings(env):
    base = env.get('COSPACE_ATLAS_BASE_URL', '')
    route = env.get('COSPACE_ATLAS_COORDINATE_ENDPOINT', '')
    http = env.get('COSPACE_ATLAS_TAILNET_HTTP', '0')
    if not base and not route:
        return None
    if base == 'disabled' and not route:
        return {'COSPACE_ATLAS_BASE_URL': '', 'COSPACE_ATLAS_COORDINATE_ENDPOINT': '',
                'COSPACE_ATLAS_TAILNET_HTTP': '0'}
    if http not in ('0', '1') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,159}', route):
        raise ValueError('atlas_configuration_invalid')
    value = urlsplit(base)
    try:
        tailnet = ipaddress.ip_address(value.hostname or '') in ipaddress.ip_network('100.64.0.0/10')
    except ValueError:
        tailnet = False
    allowed = value.scheme == 'https' or value.scheme == 'http' and tailnet and http == '1'
    if (not allowed or not value.hostname or value.username or value.password or value.path
            or value.query or value.fragment or any(c.isspace() for c in base)
            or any(ord(c) < 32 or ord(c) == 127 for c in base) or value.port == 0):
        raise ValueError('atlas_trusted_origin_required')
    return {'COSPACE_ATLAS_BASE_URL': base, 'COSPACE_ATLAS_COORDINATE_ENDPOINT': route,
            'COSPACE_ATLAS_TAILNET_HTTP': http}


def install(directory, env):
    values = settings(env)
    if values is None:
        return 'preserved'
    directory = Path(directory).absolute()
    target = directory / 'atlas.env'
    if directory.is_symlink() or directory.resolve() != directory or target.is_symlink():
        raise ValueError('atlas_configuration_symlink')
    if not directory.is_dir():
        raise ValueError('atlas_configuration_directory_missing')
    descriptor, temporary = tempfile.mkstemp(prefix='.atlas.', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return 'enabled' if values['COSPACE_ATLAS_BASE_URL'] else 'disabled'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--directory', type=Path)
    options = parser.parse_args()
    try:
        if options.check:
            settings(os.environ)
        elif options.directory:
            print('Atlas configuration ' + install(options.directory, os.environ))
        else:
            parser.error('--check or --directory required')
    except ValueError:
        raise SystemExit('Invalid Atlas deployment configuration') from None
