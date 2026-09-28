"""Table serialization must preserve cells and context under a real token budget."""
from copy import deepcopy
from pathlib import Path
import types
import unittest

from tools.vectorisation_table_text import serialize_table


class CharacterTokenizer:
    truncation = None

    def encode(self, text, add_special_tokens=True):
        return types.SimpleNamespace(ids=list(text)+(list('##') if add_special_tokens else []))


CONTEXT = {'source_id':'source-123', 'page':8, 'table_id':'indicateur-1', 'document':'RAP 2021'}


def fields(result):
    collected = {}
    for chunk in result['chunks']:
        for item in chunk['segments']:
            collected.setdefault(item['field_ref'], '')
            collected[item['field_ref']] += item['text']
    return collected


class TableTextTests(unittest.TestCase):
    def serialize(self, table, context=None, tokenizer=None):
        result = serialize_table(table, context or CONTEXT, tokenizer or CharacterTokenizer())
        self.assertTrue(result['contract']['source_text_conserved'])
        for chunk in result['chunks']:
            self.assertLessEqual(chunk['tokens'], 800)
            self.assertIn('page 8', chunk['text'])
            self.assertIn('source-123', chunk['text'])
            self.assertFalse(chunk['quality']['allow_automatic_numeric_fact'])
            self.assertTrue(chunk['field_refs'])
        return result

    def test_null_empty_zero_false_and_ragged_columns_are_distinct(self):
        result = self.serialize({'rows':[[0, None, '', False], ['12']], 'column_count':4})
        cells = {s['field_ref']:s for c in result['chunks'] for s in c['segments'] if s['kind']=='cell'}
        self.assertEqual(len(cells), 8)
        self.assertEqual(cells['r1c1']['text'], '0')
        self.assertEqual(cells['r1c2']['state'], 'null')
        self.assertEqual(cells['r1c3']['state'], 'empty_string')
        self.assertEqual(cells['r1c4']['text'], 'false')
        self.assertEqual(cells['r2c2']['state'], 'not_present')

    def test_ten_thousand_character_cell_is_lossless(self):
        value = ('aé € 0123456789\n')*700
        result = self.serialize({'rows':[[value]]})
        self.assertGreater(len(value), 10000)
        self.assertEqual(fields(result)['r1c1'], value)
        parts = [s for c in result['chunks'] for s in c['segments'] if s['field_ref']=='r1c1']
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0]['char_start'], 0)
        self.assertEqual(parts[-1]['char_end'], len(value))

    def test_multilevel_headers_remain_candidates(self):
        names = ['2021\nRéalisation\nAE', '2021\nRéalisation\nCP', '2023\nPrévision\nAE', '2023\nPrévision\nCP']
        result = self.serialize({'rows':[['80 000', '60 000', '100 000', '90 000']], 'header':{'names':names}})
        rebuilt = fields(result)
        for index, name in enumerate(names, 1):
            self.assertEqual(rebuilt['header:'+str(index)], name)
        self.assertEqual(rebuilt['r1c3'], '100 000')
        self.assertEqual(result['raw_table']['table']['header']['names'], names)
        self.assertTrue(all(c['quality']['header_status']=='source_candidates_not_certified' for c in result['chunks']))

    def test_external_bad_header_not_promoted_to_dimension(self):
        result = self.serialize({'rows':[['80 000', '90 000']], 'header':{'names':['(du point de vue du citoyen)']}})
        self.assertEqual(fields(result)['header:1'], '(du point de vue du citoyen)')
        cells = [s for c in result['chunks'] for s in c['segments'] if s['kind']=='cell']
        self.assertTrue(all('year' not in c and 'stage' not in c and 'measure' not in c for c in cells))
        self.assertEqual(cells[0]['header_candidate_ref'], 'header:1')
        self.assertEqual(cells[0]['header_assignment'], 'positional_candidate_unverified')
        self.assertIsNone(cells[1]['header_candidate_ref'])

    def test_oversized_header_and_context_are_fully_recoverable(self):
        name = '2023 prévision AE / CP et contexte source. '*300
        context = {**CONTEXT, 'long_note':'Contexte exact. '*600}
        result = self.serialize({'rows':[['42']], 'header':{'names':[name]}}, context)
        self.assertEqual(fields(result)['header:1'], name)
        self.assertEqual(result['raw_table']['context'], context)
        context_fragments = [c for c in result['chunks'] if any(s.get('context_key')=='long_note' for s in c['segments'])]
        self.assertGreater(len(context_fragments), 1)

    def test_unicode_combining_emoji_and_whitespace_survive(self):
        value = ('e\u0301 👩🏽\u200d💻 中文\u202f€\r\n\t')*150
        result = self.serialize({'rows':[[value]]})
        self.assertEqual(fields(result)['r1c1'], value)

    def test_multiple_rows_grouped_instead_of_one_vector_per_cell(self):
        result = self.serialize({'rows':[[str(i), str(i+1), 'AE'] for i in range(6)]})
        cell_chunks = [c for c in result['chunks'] if any(s['kind']=='cell' for s in c['segments'])]
        self.assertLess(len(cell_chunks), 18)
        self.assertTrue(any(sum(s['kind']=='cell' for s in c['segments']) >= 3 for c in cell_chunks))
        self.assertEqual(len([k for k in fields(result) if k.startswith('r')]), 18)

    def test_coordinates_and_input_are_preserved(self):
        table = {'rows':[['1','2']], 'bbox':[0,10,100,30], 'cell_bboxes':[[[0,10,50,30],[50,10,100,30]]],
                 'header':{'names':['AE','CP'], 'external':True, 'bbox':[0,0,100,10]}}
        before = deepcopy(table)
        result = self.serialize(table)
        self.assertEqual(table, before)
        self.assertEqual(result['raw_table']['table'], before)
        result['raw_table']['table']['rows'][0][0] = 'changed'
        self.assertEqual(table, before)

    def test_truncating_tokenizer_and_impossible_budget_are_rejected(self):
        truncated = CharacterTokenizer()
        truncated.truncation = {'max_length':800}
        with self.assertRaisesRegex(ValueError, 'truncation'):
            serialize_table({'rows':[['42']]}, CONTEXT, truncated)
        with self.assertRaisesRegex(ValueError, 'budget'):
            serialize_table({'rows':[['42']]}, CONTEXT, CharacterTokenizer(), max_tokens=64)

    def test_real_bge_tokenizer_budget_and_conservation(self):
        path = Path('C:/Users/Jean-Christophe/Documents/ChatGPT/Mises à jour auto/hatvp_exploitation_20260908/assets/tokenizer.json')
        if not path.exists():
            self.skipTest('Shared BGE tokenizer fixture unavailable')
        try:
            from tokenizers import Tokenizer
        except ImportError:
            self.skipTest('tokenizers runtime unavailable')
        tokenizer = Tokenizer.from_file(str(path))
        tokenizer.no_truncation()
        tokenizer.no_padding()
        value = ('AE 2021\u202f: 80 000 € ; CP 2023\u202f: 95 100 €. 👩🏽\u200d💻\n')*300
        result = self.serialize({'rows':[[value, None, 0]], 'header':{'names':['Réalisation AE', 'CP', 'Écart']}}, tokenizer=tokenizer)
        self.assertEqual(fields(result)['r1c1'], value)
        self.assertEqual(fields(result)['r1c3'], '0')
        for chunk in result['chunks']:
            self.assertEqual(chunk['tokens'], len(tokenizer.encode(chunk['text']).ids))


if __name__ == '__main__':
    unittest.main()
