"""Serve only the built workbench HTML and its hashed assets from a trusted directory."""
from pathlib import Path
import re


CONTENT_TYPES = {'js': 'text/javascript; charset=utf-8', 'css': 'text/css; charset=utf-8',
                 'woff2': 'font/woff2', 'woff': 'font/woff', 'svg': 'image/svg+xml'}
ASSET_PATH = re.compile(r'/assets/[a-zA-Z0-9_.-]+-[a-zA-Z0-9_-]{6,}\.(js|css|woff2?|svg)\Z')
POLICY = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
          "font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
          "base-uri 'none'; form-action 'none'")


class WorkbenchAssets:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not (self.root / 'index.html').is_file() or not (self.root / 'assets').is_dir():
            raise ValueError('invalid_workbench_assets')

    def read(self, path):
        asset = ASSET_PATH.fullmatch(path)
        if path == '/':
            name, content_type = 'index.html', 'text/html; charset=utf-8'
        elif asset:
            name, content_type = path[1:], CONTENT_TYPES[asset.group(1)]
        else:
            return None
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root) or not target.is_file():
            return None
        with target.open('rb') as stream:
            payload = stream.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError('invalid_workbench_asset_size')
        return payload, content_type, 'public, max-age=31536000, immutable' if asset else 'no-store'
