"""Inventory of registered bytes; does not re-read mutable source files."""
from copy import deepcopy


def inventory(manifest, roles):
    return {'representation': 'data_inventory_v0.1',
            'source_description': manifest['data']['source_description'],
            'verification': {'status': 'verified_at_registration', 'verified_at': None,
                             'time_status': 'not_recorded', 'source_files_rechecked': False},
            'usage_conditions': 'not_assessed', 'field_quality': 'not_field_validated',
            'acquisition': 'none_synthetic',
            'items': [{**deepcopy(record), 'role': roles.get(record['path'], 'unclassified'),
                       'integrity': 'verified_at_registration'} for record in manifest['data']['files']]}
