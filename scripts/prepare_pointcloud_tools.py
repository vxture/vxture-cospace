"""Fetch checksum-pinned upstream tools; generated third-party files stay out of Git."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'var' / 'pointcloud-tools'
ARCHIVES = {
    'potree.zip': ('https://github.com/potree/potree/releases/download/1.8.2/Potree_1.8.2.zip',
                   'c140a8bce0ce129de762fbc0fd3ba7c21120ffd36d423dd2755abb39f32aebe5'),
    'converter.zip': ('https://github.com/potree/PotreeConverter/releases/download/2.1.5/PotreeConverter_2.1.5_x64_windows.zip',
                      'a05bc3a936e41705649dc41b9ae4300ee5273ed23a3f1845e94690ca142e6248'),
    'converter-source.tar.gz': ('https://codeload.github.com/potree/PotreeConverter/tar.gz/refs/tags/2.1.5',
                              '4bf24b860da65683971869b7b1542cb779ec7be4375df8e20742e9e370dce6e3'),
    # The viewer does not load the upstream 3.1.1 jQuery or its optional legacy UI.
    'jquery.min.js': ('https://code.jquery.com/jquery-3.7.1.min.js',
                      'fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a'),
}


def acquire(name):
    url, expected = ARCHIVES[name]
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if not target.exists():
        with urllib.request.urlopen(url, timeout=90) as response:
            raw = response.read(100 * 1024 * 1024 + 1)
        if len(raw) > 100 * 1024 * 1024:
            raise ValueError('upstream_archive_budget')
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('upstream_archive_integrity')
        target.write_bytes(raw)
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError('cached_archive_integrity')
    return target


def web():
    target = ROOT / 'apps/workbench/public/assets/potree-1.8.2'
    with zipfile.ZipFile(acquire('potree.zip')) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if '..' in path.parts or path.is_absolute():
                raise ValueError('upstream_archive_path')
            relative = '/'.join(path.parts[1:])
            if item.is_dir() or not (relative.startswith('build/potree/') or relative.startswith('libs/three.js/')):
                continue
            if '/lazylibs/' in relative or relative.endswith(('.map', '.html')):
                continue
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(item))
        # Only dependencies used by the isolated viewer, no third-party menus.
        for name in ('libs/other/BinaryHeap.js', 'libs/tween/tween.min.js',
                     'libs/tween/LICENSE.txt', 'libs/proj4/proj4.js', 'libs/proj4/LICENSE.md'):
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read('Potree_1.8.2/' + name))
    shutil.copyfile(acquire('jquery.min.js'), target / 'jquery.min.js')
    print('Pinned Potree 1.8.2 web assets ready')


def converter():
    target = CACHE / 'converter'
    with zipfile.ZipFile(acquire('converter.zip')) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('upstream_archive_path')
            if item.is_dir() or '/resources/' in item.filename:
                continue
            output = target / item.filename
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(item))
    print(target / 'PotreeConverter_2.1.5_x64_windows/PotreeConverter.exe')


def source():
    with tarfile.open(acquire('converter-source.tar.gz')) as archive:
        archive.extractall(CACHE / 'source', filter='data')
    # The pinned 2022 source predates GCC 14's deleted nullptr string assignment.
    # Explicit JSON string extraction and a portable debug trap preserve encoding.
    indexer = CACHE / 'source/PotreeConverter-2.1.5/Converter/src/indexer.cpp'
    text = indexer.read_text()
    replacements = {
        '__debugbreak();': '__builtin_trap();',
        'state->name = js["state"]["name"];': 'state->name = js["state"]["name"].get<string>();',
        'attribute.description = jsAttribute["description"];': 'attribute.description = jsAttribute["description"].get<string>();',
        'chunk->id = jsChunk["id"];': 'chunk->id = jsChunk["id"].get<string>();',
        'chunk->file = jsChunk["file"];': 'chunk->file = jsChunk["file"].get<string>();',
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise ValueError('upstream_compatibility_patch_changed')
        text = text.replace(before, after)
    indexer.write_text(text)
    buffer = indexer.with_name('VBuffer.cpp')
    text = buffer.read_text()
    if text.count('__debugbreak();') != 3:
        raise ValueError('upstream_compatibility_patch_changed')
    buffer.write_text(text.replace('__debugbreak();', '__builtin_trap();'))
    print(CACHE / 'source/PotreeConverter-2.1.5')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--web', action='store_true')
    parser.add_argument('--windows-converter', action='store_true')
    parser.add_argument('--source', action='store_true')
    args = parser.parse_args()
    if args.web:
        web()
    if args.windows_converter:
        converter()
    if args.source:
        source()
