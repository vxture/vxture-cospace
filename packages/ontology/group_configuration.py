"""Compatibility import for existing CoSpace configuration consumers."""
from .kernel.local_host.group_configuration import (
    PRESETS, GroupConfigurationError, GroupConfigurationStore, clean_text,
    initial_groups, normalize, validate_change,
)

__all__ = ['PRESETS', 'GroupConfigurationError', 'GroupConfigurationStore', 'clean_text',
           'initial_groups', 'normalize', 'validate_change']
