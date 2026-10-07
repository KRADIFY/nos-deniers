"""Host-only safeguards protecting the already encoded retrieval supplement."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / 'tools/build_retrieval_extension.py'


@unittest.skipUnless(TOOL.is_file(), 'Corpus preparation tool is not shipped in the Web image')
class RetrievalExtensionGuardTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('retrieval_extension_guard_test', TOOL)
        self.extension = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.extension)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.previous = self.root / 'previous'
        self.previous.mkdir()
        self.database = self.previous / 'search.sqlite'
        # The safeguards must reject before SQLite or the tokenizer is touched.
        self.database.write_bytes(b'previous immutable database bytes')
        (self.previous / 'dense.faiss').write_bytes(b'previous immutable vector bytes')
        e = self.extension
        self.manifest = dict(version=e.VERSION, state='ready', model=e.MODEL, revision=e.REVISION,
                             dimension=e.DIMENSION, base_input_sha256='a' * 64,
                             files=[dict(path=name, bytes=(self.previous / name).stat().st_size,
                                         sha256=e.digest(self.previous / name)) for name in ('search.sqlite', 'dense.faiss')])
        (self.previous / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        self.manifest_sha = e.digest(self.previous / 'manifest.json')
        self.input = self.root / 'new-input.json'
        self.input.write_text('{}', encoding='utf-8')
        self.before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.previous.iterdir()}

    def assert_rejected_without_opening_or_copying(self, output, base_identity, message):
        e = self.extension
        with patch.object(e.shutil, 'copyfile') as copy, patch.object(e.sqlite3, 'connect') as connect:
            with self.assertRaisesRegex(ValueError, message):
                e.prepare(self.previous, self.input, output, self.manifest_sha, base_identity)
            copy.assert_not_called()
            connect.assert_not_called()
        self.assertEqual(self.before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.previous.iterdir()})

    def test_same_output_directory_cannot_modify_previous_supplement(self):
        self.assert_rejected_without_opening_or_copying(self.previous / '.', 'a' * 64, 'separate copy')

    def test_hardlink_output_cannot_modify_previous_supplement(self):
        output = self.root / 'extension'
        output.mkdir()
        try:
            os.link(self.database, output / 'search.sqlite')
        except OSError as error:
            self.skipTest('Hardlinks unavailable in this temporary filesystem: ' + str(error))
        self.assert_rejected_without_opening_or_copying(output, 'a' * 64, 'separate copy')
        self.assertTrue((output / 'search.sqlite').samefile(self.database))

    def test_another_main_generation_is_rejected_before_creating_output(self):
        output = self.root / 'extension'
        self.assert_rejected_without_opening_or_copying(output, 'b' * 64, 'another main generation')
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
