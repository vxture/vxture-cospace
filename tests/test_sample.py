"""Cross-module tests for semantic and reference failures, with valid digests."""
import tempfile
import unittest
from pathlib import Path

from packages.service.sample import validate_package
from scripts.build_sample import build


class SamplePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'bundle'

    def reject(self, mutation, reason):
        build(self.root, mutation)
        with self.assertRaisesRegex(ValueError, reason):
            validate_package(self.root)

    def test_valid_package(self):
        build(self.root)
        result = validate_package(self.root)
        self.assertTrue(result['passed'])
        self.assertFalse(result['real_release_ready'])
        self.assertEqual(result['verified_files'], 6)

    def test_mixed_truth_with_valid_hash(self):
        # JSON references are shared in the generator; replace the reference to isolate the change.
        def isolated(name, doc):
            if name == 'agent.json':
                doc['source_truth'] = {**doc['source_truth'], 'truth_version_id': 'other-truth'}
        self.reject(isolated, 'different truth')

    def test_unknown_type(self):
        def mutate(name, doc):
            if name == 'objects.json':
                doc['objects'][0]['type_id'] = 'undefined'
        self.reject(mutate, 'unknown ontology type')

    def test_missing_required_property(self):
        def mutate(name, doc):
            if name == 'objects.json':
                doc['objects'][0]['properties'] = {}
        self.reject(mutate, 'missing property')

    def test_frame_mismatch(self):
        def mutate(name, doc):
            if name == 'human.json':
                doc['frame'] = {**doc['frame'], 'frame_id': 'different-frame'}
        self.reject(mutate, 'coordinate definition')

    def test_ontology_version_mismatch(self):
        def mutate(name, doc):
            if name == 'truth.json':
                doc['ontology_ref'] = {**doc['ontology_ref'], 'version': 'other'}
        self.reject(mutate, 'ontology identity/version')

    def test_unverified_localization_claim(self):
        def mutate(name, doc):
            if name == 'agent.json':
                doc['capabilities'] = ['localization']
        self.reject(mutate, 'reference reading')

    def test_tampered_content(self):
        build(self.root)
        with (self.root / 'objects.json').open('ab') as output:
            output.write(b' ')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            validate_package(self.root)

    def test_outside_reference(self):
        def mutate(name, doc):
            if name == 'package.json':
                doc['data']['files'][0]['path'] = '../outside.json'
        self.reject(mutate, 'invalid package path')

    def test_real_channel_rejected(self):
        build(self.root)
        with self.assertRaisesRegex(ValueError, 'sample channel only'):
            validate_package(self.root, 'real')

    def test_real_data_label_rejected(self):
        def mutate(name, doc):
            if name == 'package.json':
                doc['data_kind'] = 'captured'
        self.reject(mutate, 'restricted to synthetic')

    def test_duplicate_json_keys(self):
        build(self.root)
        (self.root / 'package.json').write_text('{"profile":1,"profile":2}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            validate_package(self.root)


if __name__ == '__main__':
    unittest.main()
