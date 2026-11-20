"""Portable instance contract resources used by the B03 pure validator."""
from importlib.resources import files
import json


def instance_schema():
    """Return a detached JSON Schema; no host state, I/O beyond packaged resources.

    Callers must enable format checks. Schema validation alone cannot establish
    referential integrity, ontology compatibility, valid intervals or truth.
    """
    return json.loads(files(__package__).joinpath('instance.schema.json').read_bytes())


def park_baseline_rules():
    """Return candidate domain rules; validation executes them only when selected."""
    return json.loads(files(__package__).joinpath('park-baseline.rules.json').read_bytes())
