"""Standard Draft 2020-12 validation with located input diagnostics."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, validators


class StructureError(ValueError):
    def __init__(self, file, path, message):
        self.file, self.path, self.message = file, path, message
        super().__init__(f'{file}#{path}: {message}')


SCHEMA_PATH = (Path(__file__).resolve().parents[2] / 'contracts' / 'schemas'
               / 'synthetic-bundle-v0.1.schema.json')
# Preserve the existing literal-integer input policy, including rejecting bool.
LiteralIntegerValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        'integer', lambda checker, value: type(value) is int))


def check_structure(document, definition, file, profile='cospace.synthetic-bundle/0.1'):
    versions = {'cospace.synthetic-bundle/0.1': 'v0.1',
                'cospace.synthetic-bundle/0.2': 'v0.2'}
    if profile not in versions:
        raise ValueError('unsupported sample profile version')
    path = SCHEMA_PATH.with_name(f'synthetic-bundle-{versions[profile]}.schema.json')
    schema = json.loads(path.read_text(encoding='utf-8'))
    validator = LiteralIntegerValidator({**schema, '$ref': '#/$defs/' + definition})
    errors = list(validator.iter_errors(document))
    if not errors:
        return
    error = errors[0]
    parts = list(error.absolute_path)
    message = error.message
    if error.validator == 'required':
        missing = next(key for key in error.validator_value if key not in error.instance)
        parts.append(missing)
        message = 'required field missing'
    elif error.validator == 'additionalProperties':
        unknown = next(key for key in error.instance
                       if key not in error.schema.get('properties', {}))
        parts.append(unknown)
        message = 'unknown field'
    elif error.validator == 'type':
        kinds = error.validator_value
        message = 'expected ' + (' or '.join(kinds) if isinstance(kinds, list) else kinds)
    elif error.validator == 'minLength':
        message = 'string must not be empty'
    elif error.validator in ('minItems', 'maxItems'):
        message = 'invalid array length'
    elif error.validator == 'pattern':
        message = 'string does not match required pattern'
    elif error.validator == 'minimum':
        message = 'number is below minimum'
    pointer = ''.join('/' + str(part).replace('~', '~0').replace('/', '~1') for part in parts)
    raise StructureError(file, pointer, message)
