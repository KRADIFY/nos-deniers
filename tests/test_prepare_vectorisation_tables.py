import sys
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_vectorisation_tables import raw_chunks, lexical, replace_file_safely


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=True):
        return SimpleNamespace(ids=list(text)+[0, 1])


class RawSourceTests(unittest.TestCase):
    def test_checkpoint_retries_transient_windows_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'status.partial'; target=Path(folder)/'status.json'
            source.write_text('new'); target.write_text('old')
            real_replace=Path.replace; calls=[]
            def locked_once(path,destination):
                calls.append(str(path))
                if len(calls)<3:
                    raise PermissionError('simulated Windows reader')
                return real_replace(path,destination)
            with patch('pathlib.Path.replace',locked_once),patch('prepare_vectorisation_tables.time.sleep'):
                replace_file_safely(source,target)
            self.assertEqual(target.read_text(),'new')
            self.assertFalse(source.exists())
            self.assertEqual(len(calls),3)

    def test_persistent_denial_preserves_both_checkpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'status.partial'; target=Path(folder)/'status.json'
            source.write_text('new'); target.write_text('old')
            with patch('pathlib.Path.replace',side_effect=PermissionError('permanent')) as mocked,patch('prepare_vectorisation_tables.time.sleep'):
                with self.assertRaises(PermissionError):
                    replace_file_safely(source,target)
            self.assertEqual(mocked.call_count,30)
            self.assertEqual(target.read_text(),'old')
            self.assertEqual(source.read_text(),'new')

    def test_long_unicode_blocks_preserve_every_character(self):
        original = [('MaPrimeRénov’ AE 123\u202f456 CP −789,10\n'*50), 'Écologie e\u0301🙂 zéro 0']
        record = {'page':3, 'blocks':[{'text':x} for x in original], 'words':[]}
        result = raw_chunks(record, 'a'*64, CharacterTokenizer())
        rebuilt = ['','']
        for chunk in result:
            self.assertLessEqual(chunk['tokens'], 800)
            for segment in chunk['segments']:
                self.assertEqual(len(rebuilt[segment['block']]), segment['char_start'])
                rebuilt[segment['block']] += segment['text']
        self.assertEqual(original, rebuilt)
        self.assertFalse(lexical(''.join(original))-sum((lexical(c['body']) for c in result), lexical('')))

    def test_missing_native_word_is_indexed(self):
        record = {'page':1,'blocks':[{'text':'Total'}],
                  'words':[[0,0,10,10,'Total'], [11,0,20,10,'123456']]}
        result = raw_chunks(record, 'a'*64, CharacterTokenizer())
        self.assertIn('123456', '\n'.join(c['body'] for c in result))

    def test_continuous_long_atom_has_exact_offsets(self):
        original = 'x'*10000
        result = raw_chunks({'page':1,'blocks':[{'text':original}],'words':[]}, 'b'*64, CharacterTokenizer())
        self.assertEqual(''.join(s['text'] for c in result for s in c['segments']), original)
        self.assertGreater(len(result), 1)

    def test_empty_page_does_not_create_fabricated_text(self):
        self.assertEqual(raw_chunks({'page':1,'blocks':[],'words':[]},'c'*64,CharacterTokenizer()), [])


if __name__ == '__main__':
    unittest.main()
