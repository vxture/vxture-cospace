"""Compatibility import for the shared SQLite authoring adapter."""
from .kernel.local_host.authoring_sqlite import MAX_STATE_BYTES, SQLiteAuthoringPort

__all__ = ['MAX_STATE_BYTES', 'SQLiteAuthoringPort']
