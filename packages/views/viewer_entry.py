"""Small bookmark bridge; all interactive rendering belongs to the workbench."""
from html import escape
from urllib.parse import urlencode


def viewer_href(space_id, *, candidate_id=None, publication_id=None):
    if bool(candidate_id) == bool(publication_id):
        raise ValueError('one_viewer_record_required')
    return '/space?' + urlencode({'screen': 'space', 'preview': '1', 'space': space_id,
                                  **({'job': candidate_id} if candidate_id else {'publication': publication_id})})


def write_viewer_entry(root, manifest, *, publication_id=None):
    href = escape(viewer_href(manifest.get('space_id', ''),
                             candidate_id=None if publication_id else manifest['id'],
                             publication_id=publication_id), quote=True)
    (root/'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>CoSpace 成果查看</title>'
        f'<meta http-equiv="refresh" content="0;url={href}">'
        f'<a href="{href}">打开 CoSpace 成果查看器</a>', encoding='utf-8')
