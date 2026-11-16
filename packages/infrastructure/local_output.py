"""Local experiment output confined to an explicit trusted root, never runtime storage."""
from pathlib import Path
import re

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / 'output'


def output_path(path, *, allowed_root=None):
    if allowed_root is None:
        DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
    allowed = (DEFAULT_ROOT if allowed_root is None else Path(allowed_root)).resolve(strict=True)
    candidate = Path(path).resolve()
    if not allowed.is_dir() or candidate == allowed or not candidate.is_relative_to(allowed):
        raise ValueError('output_outside_allowed_root')
    return candidate


def new_output_directory(path, *, allowed_root=None):
    candidate = output_path(path, allowed_root=allowed_root)
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def write_member(root, name, raw):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9.-]{0,100}', name):
        raise ValueError('output_member_name')
    candidate = output_path(Path(root) / name, allowed_root=root)
    with candidate.open('xb') as stream:
        stream.write(raw)
