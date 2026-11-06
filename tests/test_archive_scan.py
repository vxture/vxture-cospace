import io
import tarfile
import zipfile
import pytest
from scripts.security import expand_archives as scanner


def document(path, name='word/document.xml', data=b'synthetic scan marker'):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(name, data)


def test_docx_contents_exposed_and_paths_never_restored(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    document(source / 'design.docx', '../../outside', b'synthetic scan marker')
    output = tmp_path / 'expanded'
    index = scanner.expand_archives(source, output)
    assert len(index) == 1
    identity, name = next(iter(index.items()))
    assert name == 'design.docx!../../outside'
    assert (output / identity).read_bytes() == b'synthetic scan marker'
    assert not (tmp_path / 'outside').exists()


def test_nested_document_in_tgz_is_exposed(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('word/document.xml', b'synthetic nested marker')
    raw = buffer.getvalue()
    with tarfile.open(source / 'bundle.tgz', 'w:gz') as archive:
        info = tarfile.TarInfo('nested.docx'); info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
    output = tmp_path / 'expanded'
    index = scanner.expand_archives(source, output)
    assert any(name.endswith('nested.docx!word/document.xml') for name in index.values())
    assert any(path.read_bytes() == b'synthetic nested marker' for path in output.glob('*.txt'))


def test_duplicate_members_cannot_hide_earlier_contents(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with zipfile.ZipFile(source / 'duplicate.docx', 'w') as archive:
        archive.writestr('word/document.xml', b'first')
        with pytest.warns(UserWarning):
            archive.writestr('word/document.xml', b'second')
    with pytest.raises(ValueError, match='duplicate_member'):
        scanner.expand_archives(source, tmp_path / 'expanded')


def test_archive_resource_limit_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    document(source / 'design.docx')
    monkeypatch.setattr(scanner, 'MAX_BYTES', 4)
    with pytest.raises(ValueError, match='size_limit'):
        scanner.expand_archives(source, tmp_path / 'expanded')


def test_tar_hard_link_exposes_metadata_and_regular_target(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with tarfile.open(source / 'vendor.tgz', 'w:gz') as archive:
        info = tarfile.TarInfo('package/source'); info.size = 6
        archive.addfile(info, io.BytesIO(b'marker'))
        link = tarfile.TarInfo('package/alias')
        link.type = tarfile.LNKTYPE; link.linkname = 'package/source'
        archive.addfile(link)
    output = tmp_path / 'expanded'
    index = scanner.expand_archives(source, output)
    assert len(index) == 2
    assert {p.read_bytes() for p in output.glob('*.txt')} == {b'marker', b'package/source'}
    assert not (output / 'package').exists()


def test_tar_symlink_is_rejected(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with tarfile.open(source / 'vendor.tgz', 'w:gz') as archive:
        link = tarfile.TarInfo('package/alias')
        link.type = tarfile.SYMTYPE; link.linkname = '../../outside'
        archive.addfile(link)
    with pytest.raises(ValueError, match='special_member'):
        scanner.expand_archives(source, tmp_path / 'expanded')
