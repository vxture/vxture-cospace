"""J4 explicit file-package session adapter; synthetic only, no default R1 change."""
from experiments.scripts.recovery_state import RecoveryStore
from experiments.scripts.validity_probe import GuardedSession, GateError


class RecoverySession(GuardedSession):
    def __init__(self, files, scene, ledger, binding, clock):
        if not isinstance(ledger, RecoveryStore):
            raise GateError('recovery_store_required')
        if scene != binding.get('scene_id'):
            raise GateError('scene_binding_mismatch')
        super().__init__(files, scene, ledger, binding, clock)
        self.open_generation = ledger.generation

    def query(self, point):
        result = super().query(point)
        return {**result, 'session_generation': self.open_generation,
                'authorized': False, 'robot_ready': False}
