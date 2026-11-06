"""Small local diagnostic archive; atomic visibility, no overwrite, no trust grant."""
import os
from pathlib import Path
import re
import uuid

from packages.data.imports import canonical, sha
from packages.infrastructure.files import safe_path
from packages.service.delivery import SavedReport, SavedDeliveryReader, DeliveryReportError
from packages.data.delivery_report import validate_generation

KEY = re.compile(r'[0-9a-f-]{36}\.[0-9a-f]{64}')


def report_key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise ValueError('invalid report key')
    identity = uuid.UUID(value[:36])
    if str(identity) != value[:36] or identity.version != 4:
        raise ValueError('invalid report batch')
    return value


def separate_output(output, roots):
    output = safe_path(output)
    for root in roots:
        root = safe_path(root)
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError('archive and observed roots must not overlap')
    return output


def publish(root, document):
    """Same-volume hardlink publishes completed bytes without replacing any destination."""
    SavedReport.model_validate(document)
    generation = validate_generation(document)
    if generation is None:
        raise ValueError('only generated 0.2 reports can be archived')
    raw = canonical(document)
    if len(raw) > SavedDeliveryReader.MAX_BYTES:
        raise ValueError('report exceeds archive limit')
    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True)
    key = report_key(generation.report_id + '.' + sha(raw))
    temporary = safe_path(root / ('.writing-' + str(uuid.uuid4())))
    destination = safe_path(root / (key + '.json'))
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic no-replace visibility on supported local filesystems. No copy fallback.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {'report_key': key, 'sha256': sha(raw), 'bytes': len(raw),
            'report_id': generation.report_id, 'authorized': False}


class ReportArchive:
    def __init__(self, root):
        self.root = Path(root)

    def read(self, scene, release, key):
        try:
            key = report_key(key)
            path = safe_path(safe_path(self.root) / (key + '.json'))
            envelope = SavedDeliveryReader(path).read(scene, release)
            if (envelope['source']['sha256'] != key[37:] or
                    envelope['report']['generation'] is None or
                    envelope['report']['generation']['report_id'] != key[:36]):
                raise ValueError('archive content identity mismatch')
            envelope['source']['report_key'] = key
            return envelope
        except (OSError, ValueError) as error:
            raise DeliveryReportError('delivery_report_unavailable') from error

    def list(self, scene, release):
        try:
            root = safe_path(self.root)
            # Bound the whole directory, including ignored temporary/unrecognized entries.
            names = []
            with os.scandir(root) as entries:
                for entry in entries:
                    names.append(entry.name)
                    if len(names) > 200:
                        raise ValueError('archive directory limit')
            items = []
            for name in sorted(names):
                if not name.endswith('.json') or not KEY.fullmatch(name[:-5]):
                    continue
                key = name[:-5]
                try:
                    envelope = self.read(scene, release, key)
                except DeliveryReportError as error:
                    if error.code == 'delivery_report_target_mismatch':
                        continue
                    raise
                report = envelope['report']
                items.append({'report_key': key, 'sha256': envelope['source']['sha256'],
                    'report_id': report['generation']['report_id'],
                    'interval': report['generation']['interval'],
                    'requested_binding': report['requested_binding'],
                    'complete': report['complete'], 'needs_attention': report['needs_attention']})
                if len(items) > 50:
                    raise ValueError('archive target limit')
            return {'schema_version': 'cospace.delivery-report-list/0.1',
                    'scene_id': scene, 'release_id': release, 'items': items,
                    'selection': 'explicit_key_required', 'authorized': False}
        except (OSError, ValueError) as error:
            raise DeliveryReportError('delivery_report_unavailable') from error
