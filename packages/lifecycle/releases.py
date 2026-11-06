"""Synthetic release policy; storage supplies transactions and scene locking."""
from packages.service.query import QueryError, SampleService


class ReleaseError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class ReleaseManager:
    def __init__(self, store):
        self.store = store

    def register(self, root):
        service = SampleService(root)
        metadata = service.describe()
        # Persist verified in-memory content, not a mutable filesystem location.
        self.store.register(metadata['scene_id'], metadata['release_id'], service.export_snapshot())
        return metadata

    def activate(self, scene_id, release_id, expected_revision, actor):
        if type(expected_revision) is not int or expected_revision < 0 or not actor.strip():
            raise ReleaseError('invalid_request', 'revision and actor are required')
        with self.store.transaction(scene_id) as tx:
            pointer = tx.current()
            if pointer['revision'] != expected_revision:
                raise ReleaseError('revision_conflict', 'current revision changed; resolve before retry')
            tx.load(release_id)
            self._check_valid(tx, release_id)
            return tx.activate(release_id, actor)

    def revoke(self, scene_id, release_id, actor, reason):
        if not actor.strip() or not reason.strip():
            raise ReleaseError('invalid_request', 'actor and reason must be nonempty')
        with self.store.transaction(scene_id) as tx:
            tx.load(release_id)
            return tx.revoke(release_id, actor, reason)

    def current(self, scene_id):
        with self.store.transaction(scene_id) as tx:
            pointer = tx.current()
            if pointer['release_id'] is None:
                raise ReleaseError('no_current_release', 'scene has no active sample release')
            service = self._service(tx.load(pointer['release_id']))
            return {**service.describe(), **pointer,
                    'active': not bool(tx.revocations(pointer['release_id']))}

    def trace(self, scene_id, release_id):
        with self.store.transaction(scene_id) as tx:
            return {**self._service(tx.load(release_id)).describe(),
                    'revocations': tx.revocations(release_id)}

    def query(self, scene_id, release_id, frame_id, point):
        # Revocation and query serialize on the same scene lock. A revocation
        # committed before this operation is never bypassed by a pinned version.
        with self.store.transaction(scene_id) as tx:
            service = self._service(tx.load(release_id))
            self._check_valid(tx, release_id)
            return service.query(scene_id, release_id, frame_id, point)

    def human(self, scene_id, release_id):
        # Conservatively block preview on the same sample revocation gate.
        with self.store.transaction(scene_id) as tx:
            service = self._service(tx.load(release_id))
            self._check_valid(tx, release_id)
            return service.human()

    def inspection(self, scene_id, release_id, kind):
        with self.store.transaction(scene_id) as tx:
            service = self._service(tx.load(release_id))
            self._check_valid(tx, release_id)
            return service.inspection(kind)

    @staticmethod
    def _check_valid(tx, release_id):
        if tx.revocations(release_id):
            raise QueryError('capability_revoked', 'synthetic_point_query has been revoked; see trace')

    @staticmethod
    def _service(payload):
        return SampleService.from_snapshot(payload)
