"""Bad metadata must produce a stable file and JSON Pointer diagnostic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from packages.data.structure import StructureError, check_structure
from packages.service.sample import validate_package
from scripts.build_sample import build


class StructureTests(unittest.TestCase):
    def test_malformed_package_cases(self):
        cases = [
            ('package.json', lambda d: d.pop('data'), '/data', 'required field'),
            ('package.json', lambda d: d.update(extra=True), '/extra', 'unknown field'),
            ('package.json', lambda d: d['data']['files'][0].update(bytes=True),
             '/data/files/0/bytes', 'expected integer'),
            ('package.json', lambda d: d['data']['files'][0].update(bytes=-1),
             '/data/files/0/bytes', 'below minimum'),
            ('package.json', lambda d: d['release'].update(sha256='bad'),
             '/release/sha256', 'pattern'),
            ('ontology.json', lambda d: d['types']['room']['properties']['name'].update(required='yes'),
             '/types/room/properties/name/required', 'expected boolean'),
            ('objects.json', lambda d: d['objects'][0].update(anchor_xyz=[True, 0, 0]),
             '/objects/0/anchor_xyz/0', 'expected number'),
            ('objects.json', lambda d: d['objects'][0].update(object_id=''),
             '/objects/0/object_id', 'empty'),
            ('truth.json', lambda d: d.update(parent_truth_version_id=42),
             '/parent_truth_version_id', 'string or null'),
            ('truth.json', lambda d: d.update(provenance={}),
             '/provenance/method', 'required field'),
            ('agent.json', lambda d: d.update(frame=[]), '/frame', 'expected object'),
            ('release.json', lambda d: d.update(views=[]), '/views', 'array length'),
        ]
        for filename, mutation, pointer, message in cases:
            with self.subTest(file=filename, pointer=pointer), tempfile.TemporaryDirectory() as tmp:
                def mutate(name, document):
                    if name == filename:
                        mutation(document)
                build(Path(tmp), mutate)
                with self.assertRaises(StructureError) as caught:
                    validate_package(tmp)
                self.assertEqual(caught.exception.file, filename)
                self.assertEqual(caught.exception.path, pointer)
                self.assertIn(message, caught.exception.message)

    def test_root_must_be_object(self):
        with self.assertRaisesRegex(StructureError, 'expected object'):
            check_structure([], 'package', 'package.json')

    def test_json_pointer_escapes_property_names(self):
        document = {'objects': [{'object_id': 'x', 'type_id': 'cabinet',
                     'properties': {'a/b~c': 12}, 'anchor_xyz': [0, 0, 0],
                     'confirmation': 'synthetic'}]}
        with self.assertRaises(StructureError) as caught:
            check_structure(document, 'objects', 'objects.json')
        self.assertEqual(caught.exception.path, '/objects/0/properties/a~1b~0c')

    def test_cli_structured_error_and_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp))
            (Path(tmp) / 'package.json').write_text('[]', encoding='utf-8')
            result = subprocess.run([sys.executable, '-m', 'apps.cli.check_sample', tmp],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            report = json.loads(result.stdout)
            self.assertEqual(report['error'], {'code': 'structure_error',
                'file': 'package.json', 'path': '', 'message': 'expected object'})
            self.assertFalse(report['real_release_ready'])
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
