"""Read-only QA of the 677-page pilot; not permission to reuse an old code contract."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import unittest
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT/'reports/audit-vectorisation-20260911/staging-smoke'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def words(text):
    return Counter(re.findall(r'\w+', unicodedata.normalize('NFC',str(text)).casefold()))


def sum_words(texts):
    count = Counter()
    for text in texts:
        count.update(words(text))
    return count


def inspect_pilot():
    from tokenizers import Tokenizer
    contract = json.loads((STAGE/'staging_contract.json').read_text('utf-8'))
    tokenizer = Tokenizer.from_file(contract['config']['tokenizer'])
    tokenizer.no_truncation()
    tokenizer.no_padding()
    assert sha(Path(contract['config']['tokenizer'])) == contract['config']['tokenizer_sha256']
    receipts = json.loads((STAGE/'receipts.json').read_text('utf-8'))
    prep = Path(contract['config']['output_root'])
    errors = []
    counts = Counter()
    examples, max_tokens, max_chunks = {}, 0, 0
    kinds = Counter()
    needed_whole_word_joins = []
    for receipt in receipts:
        file = Path(receipt['file'])
        if not file.is_absolute():
            file = ROOT/file
        assert sha(file) == receipt['sha256']
        assert receipt['contract'] == contract['contract']
        sha_source = receipt['source_sha256']
        source_file = prep/'extracted'/sha_source[:2]/(sha_source+'.jsonl.gz')
        assert sha(source_file) == receipt['source_shard_sha256']
        with gzip.open(file,'rt',encoding='utf-8') as staged, gzip.open(source_file,'rt',encoding='utf-8') as source:
            originals = (json.loads(line) for line in source)
            originals = (record for record in originals if record.get('kind')=='page')
            sentinel = object()
            for expected_page, line in enumerate(staged, 1):
                item = json.loads(line)
                original = next(originals, sentinel)
                assert original is not sentinel and original['page'] == item['page'] == expected_page
                assert digest(canonical(original)) == item['raw_record_sha256']
                counts['pages'] += 1
                counts['grid_alert_pages'] += item['grid_alert']
                if not item['review_required']:
                    continue
                counts['reviews'] += 1
                assert item['record'] == original
                assert item['numeric_fact_certified'] is False and item['allow_automatic_numeric_fact'] is False
                chunks = item['chunks']
                counts['chunks'] += len(chunks)
                counts['candidates'] += item['reconstruction']['accepted']
                counts['rejected_candidates'] += item['reconstruction']['rejected']
                max_chunks = max(max_chunks, len(chunks))
                raw = [chunk for chunk in chunks if chunk['kind']=='page_source_text']
                source_blocks = [str(block.get('text','')) for block in original.get('blocks',[])]
                source_words = sum_words(word[4] for word in original.get('words',[]))
                if source_words-sum_words(source_blocks):
                    source_blocks.append(' '.join(str(word[4]) for word in original.get('words',[])))
                recovered = ['']*len(source_blocks)
                for chunk in raw:
                    for segment in chunk['segments']:
                        index = segment['block']
                        assert len(recovered[index]) == segment['char_start']
                        assert segment['text'] == source_blocks[index][segment['char_start']:segment['char_end']]
                        recovered[index] += segment['text']
                assert recovered == source_blocks
                assert not source_words-sum_words(recovered)
                isolated_raw_deficit = source_words-sum_words(chunk['body'] for chunk in raw)
                if isolated_raw_deficit:
                    needed_whole_word_joins.append({'source':sha_source,'page':item['page'],
                        'missing_in_separate_chunks':dict(isolated_raw_deficit)})
                tables = {table['table_ref']:table for table in item['tables']}
                cells = defaultdict(dict)
                contexts = defaultdict(set)
                headers = defaultdict(dict)
                for chunk in chunks:
                    tokens = len(tokenizer.encode(chunk['text'], add_special_tokens=True).ids)
                    assert tokens == chunk['tokens'] and 0 < tokens <= 800
                    counts['tokens'] += tokens
                    kinds[chunk['kind']] += 1
                    max_tokens = max(max_tokens,tokens)
                    if chunk['kind']!='table_candidate':
                        continue
                    assert chunk['quality']['allow_automatic_numeric_fact'] is False
                    assert chunk['quality']['header_status']=='source_candidates_not_certified'
                    table = tables[chunk['table_ref']]
                    for segment in chunk['segments']:
                        target = cells if segment['kind']=='cell' else headers if segment['kind']=='header_candidate' else None
                        if target is not None:
                            state = target[chunk['table_ref']].setdefault(segment['field_ref'], {'text':'','end':0,'state':segment['state']})
                            assert state['end']==segment['char_start']
                            state['text'] += segment['text']
                            state['end'] = segment['char_end']
                        else:
                            contexts[chunk['table_ref']].add(segment['context_key'])
                for table_ref, table in tables.items():
                    original_table = table['table']
                    row_start = original_table.get('row_start',1)
                    expected_cell_refs = set()
                    for row_index,row in enumerate(original_table['rows'],row_start):
                        for column in range(1,table['column_count']+1):
                            key = f'r{row_index}c{column}'
                            expected_cell_refs.add(key)
                            value = row[column-1] if column <= len(row) else None
                            state = 'not_present' if column > len(row) else 'null' if value is None else 'empty_string' if value=='' else 'value'
                            text = '' if state!='value' else value if isinstance(value,str) else canonical(value)
                            assert cells[table_ref][key]['text']==text and cells[table_ref][key]['state']==state
                            counts['cell_'+state] += 1
                    assert set(cells[table_ref]) == expected_cell_refs
                    names = original_table.get('header',{}).get('names',[]) or []
                    assert len(headers[table_ref]) == len(names)
                    for index,name in enumerate(names,1):
                        expected = '' if name is None else name if isinstance(name,str) else canonical(name)
                        assert headers[table_ref]['header:'+str(index)]['text'] == expected
                    assert contexts[table_ref] == set(table['context'])
                if sha_source.startswith('f51582832fff') and item['page'] in (61,190,338):
                    missing_original = source_words-sum_words(cell for table in original.get('tables',[]) for row in table['rows'] for cell in row if cell is not None)
                    source_numeric = Counter({token:n for token,n in missing_original.items() if any(c.isdigit() for c in token)})
                    all_chunks_words = sum_words(chunk['body'] for chunk in chunks)
                    missing_after = source_numeric-all_chunks_words
                    examples[str(item['page'])] = {'original_numeric_tokens_outside_original_cells':dict(source_numeric),
                        'still_missing_in_chunks':dict(missing_after),
                        'combined_ae_cp_rejections':[entry.get('combined_ae_cp_columns') for entry in item['reconstruction']['rejected_candidates'] if entry.get('combined_ae_cp_columns')],
                        'data_like_header_candidates':[
                            table['table'].get('header',{}).get('names',[]) for table in tables.values()
                            if any(re.fullmatch(r'[+-]?\d[\d\s.,]*',str(name or ''))
                                   for name in table['table'].get('header',{}).get('names',[]))],
                        'ae_cp_groups_preserved':any(
                            "Autorisations d'engagement" in canonical(table['table']['rows'][:3])
                            and 'Crédits de paiement' in canonical(table['table']['rows'][:3])
                            for table in tables.values()),
                        'original_tables':len(original.get('tables',[])), 'preserved_tables':len(tables),
                        'review_required':item['review_required'], 'automatically_certified':item['numeric_fact_certified']}
            assert next(originals,sentinel) is sentinel
            assert expected_page==receipt['pages']
    status = json.loads((STAGE/'status.json').read_text('utf-8'))
    for key, source_key in [('pages','pages'),('grid_alert_pages','grid_alert_pages'),('reviews','review_pages'),('chunks','chunks'),('candidates','table_candidates'),('tokens','tokens')]:
        assert counts[key] == status[source_key]
    scale = 322172/counts['pages']
    current_codes = {name:sha(ROOT/'tools'/name) for name in contract['code']}
    return {'counts':dict(counts), 'kinds':dict(kinds), 'max_tokens':max_tokens,'max_chunks_per_page':max_chunks,
        'examples':examples,'old_code_contract':contract['code'],'current_code':current_codes,
        'matches_current_code':current_codes==contract['code'],
        'raw_chunks_requiring_join_for_full_words':needed_whole_word_joins,
        'functional_conservation_passed':True,'errors':errors,
        'extrapolation_not_representative_sample':{'pages':322172,'chunks':round(counts['chunks']*scale),
            'tokens':round(counts['tokens']*scale),'gzip_bytes':round(status['bytes']*scale),
            'worker_hours':round(sum(item['elapsed_seconds'] for item in receipts)*scale/3600,2),
            'ideal_four_worker_hours':round(sum(item['elapsed_seconds'] for item in receipts)*scale/3600/4,2)}}


class StagingSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (STAGE/'receipts.json').exists():
            raise unittest.SkipTest('Local pilot corpus unavailable')
        try:
            import tokenizers
        except ImportError:
            raise unittest.SkipTest('BGE tokenizer runtime unavailable')
        cls.report = inspect_pilot()

    def test_all_pages_counts_original_records_and_words_are_preserved(self):
        self.assertTrue(self.report['functional_conservation_passed'])
        self.assertEqual(self.report['counts']['pages'],677)
        self.assertEqual(self.report['counts']['reviews'],629)

    def test_actual_bge_budget_and_missing_cells(self):
        self.assertLessEqual(self.report['max_tokens'],800)
        self.assertGreater(self.report['counts']['cell_null'],0)
        self.assertGreater(self.report['counts']['cell_empty_string'],0)

    def test_previously_missing_page_numbers_are_available(self):
        for page in ('190','338'):
            self.assertFalse(self.report['examples'][page]['still_missing_in_chunks'])

    def test_page_61_ambiguity_is_explicit_and_not_certified(self):
        example = self.report['examples']['61']
        # This page actually retains separate AE/CP groups. Its first (continued)
        # table has a data row mistaken for candidate headers, kept unverified.
        self.assertTrue(example['data_like_header_candidates'])
        self.assertTrue(example['ae_cp_groups_preserved'])
        self.assertTrue(example['review_required'])
        self.assertFalse(example['automatically_certified'])

    def test_pilot_is_not_the_final_code_generation(self):
        self.assertFalse(self.report['matches_current_code'])


if __name__ == '__main__':
    program = unittest.main(verbosity=2, exit=False)
    if hasattr(StagingSmokeTests,'report'):
        print(json.dumps(StagingSmokeTests.report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
