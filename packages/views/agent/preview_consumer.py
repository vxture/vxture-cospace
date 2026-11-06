"""Single-process preview consumer: explicit activation and fixed query sessions."""
from dataclasses import dataclass
from threading import Lock
from packages.views.agent.preview_offline import OfflinePreview
from packages.spatial.preview_range import DEFAULT_RANGE_CELLS


@dataclass(frozen=True)
class PreviewSession:
    revision: int
    publication_id: str
    package_sha256: str
    _model: OfflinePreview

    def query(self, point):
        return {**self._model.query(point), 'consumer_revision': self.revision,
                'package_sha256': self.package_sha256}

    def objects(self, object_id=None):
        return {**self._model.objects(object_id), 'consumer_revision': self.revision,
                'package_sha256': self.package_sha256}

    def query_range(self, bounds_m, frame_id, limit=DEFAULT_RANGE_CELLS):
        return {**self._model.query_range(bounds_m, frame_id, limit),
                'consumer_revision': self.revision, 'package_sha256': self.package_sha256}


class PreviewConsumer:
    """Downloading alone never changes the active package; restart starts empty."""
    def __init__(self):
        self._lock = Lock()
        self._active = None
        self._revision = 0

    def status(self):
        with self._lock:
            return {'profile': 'cospace.preview-consumer/0.1',
                    'revision': self._revision,
                    'publication_id': self._active.publication_id if self._active else None,
                    'package_sha256': self._active.package_sha256 if self._active else None,
                    'quality': 'unverified', 'robot_ready': False}

    def activate(self, path, publication_id, package_sha256, expected_revision):
        # Validate the entire proposed package before changing visible state.
        model = OfflinePreview.load(path, publication_id, package_sha256)
        with self._lock:
            if expected_revision != self._revision:
                raise ValueError('consumer_revision_changed')
            self._revision += 1
            self._active = PreviewSession(self._revision, publication_id, package_sha256, model)
            return self._active

    def session(self):
        with self._lock:
            if self._active is None:
                raise ValueError('consumer_has_no_active_publication')
            return self._active
