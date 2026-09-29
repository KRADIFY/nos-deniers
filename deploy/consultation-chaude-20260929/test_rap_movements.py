import io
import copy
import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

from budget_service import rap_movements


class RapMovementsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT)')
        self.reg = copy.deepcopy(rap_movements.registry())
        for source in self.reg['sources']:
            self.db.execute('INSERT INTO sources VALUES (?, ?)',
                            (source['id'], json.dumps(dict(source, title='RAP test', path='private/path.pdf'))))
        self.p = dict(start=2023, end=2025, budget='BG', measure='CP', scope='TA/174', exclude=[],
                      constant=False, base=2025, topic='', topic_mode='only')
        self.meta = {'indices': {'2023': 100, '2024': 110, '2025': 120}, 'inflation_source': 'ipc'}

    def query(self, **changes):
        with patch.object(rap_movements, 'registry', return_value=self.reg), patch.object(rap_movements, 'national_registry', return_value={'registries':[]}):
            return rap_movements.query(self.db, dict(self.p, **changes), self.meta)

    def test_published_registry_counts_and_original_evidence(self):
        q = self.query()
        self.assertEqual(q['count'], 20)
        self.assertEqual(self.query(measure='AE')['count'], 18)
        self.assertEqual(q['evidence_row_count'], 20)
        self.assertEqual(len(q['table_totals']), 19)
        self.assertEqual(len(q['reconciliations']), 15)
        self.assertEqual(q['proofs'], self.reg['evidence_rows'])
        self.assertTrue(all(len(row['cells']) == 8 for row in q['proofs']))
        self.assertTrue(any(cell['amount_cents'] is None for row in q['proofs'] for cell in row['cells']))

    def test_selected_year_measure_and_budget(self):
        for measure in ['AE', 'CP']:
            q = self.query(start=2024, end=2024, measure=measure)
            self.assertTrue(q['items'])
            self.assertTrue(all(row['year'] == 2024 and row['measure'] == measure for row in q['items']))
            self.assertTrue(all(row['year'] == 2024 for row in q['proofs'] + q['table_totals'] + q['reconciliations']))
            self.assertEqual(len(q['sources']), 1)
        self.assertEqual(self.query(budget='BA')['items'], [])

    def test_signed_amounts_and_link_to_same_journal_operation(self):
        rows = [row for row in self.query(start=2024, end=2024)['items'] if row['date'] == '2024-02-21']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['kind'], 'ANNULATION')
        self.assertEqual(row['nominal_cents'], -row['amount_cents'])
        self.assertLess(row['value'], 0)
        self.assertEqual(row['linked_act_id'], 'JORFTEXT000049180270')
        self.assertEqual(row['linked_act_relation'], 'same_operation')
        self.assertEqual(row['citation']['url'], '/api/download/' + row['source'] + '#page=' + str(row['page']))

    def test_inflation_is_applied_after_sign(self):
        self.reg['items'][0].update(year=2023, measure='CP', sign=-1, amount_cents=101)
        row_id = self.reg['items'][0]['id']
        row = next(row for row in self.query(constant=True)['items'] if row['id'] == row_id)
        self.assertEqual(row['nominal_cents'], -101)
        self.assertEqual(row['value_cents'], -121)
        self.assertEqual(row['value'], -1.21)

    def test_missing_inflation_keeps_nominal_but_no_adjusted_value(self):
        self.meta['indices'].pop('2023')
        row = self.query(start=2023, end=2023, constant=True)['items'][0]
        self.assertEqual(row['status'], 'inflation_missing')
        self.assertIsNone(row['value'])
        self.assertIsNotNone(row['nominal_cents'])

    def test_zero_is_preserved_and_not_reported_is_not_zero(self):
        self.reg['items'][0].update(measure='CP', amount_cents=0)
        row_id = self.reg['items'][0]['id']
        row = next(row for row in self.query()['items'] if row['id'] == row_id)
        self.assertEqual(row['status'], 'published')
        self.assertEqual(row['value'], 0)
        self.reg['items'][0]['amount_cents'] = None
        row = next(row for row in self.query()['items'] if row['id'] == row_id)
        self.assertEqual(row['status'], 'not_reported')
        self.assertIsNone(row['value'])

    def test_programme_context_cannot_be_allocated_to_actions(self):
        expected_proofs = {row['row_id'] for row in self.reg['evidence_rows']}
        for changes in [dict(scope='TA/174/02'), dict(scope='TA/174/02/01'),
                        dict(exclude=['TA/174/02']), dict(scope='TA', exclude=['TA/174/02'])]:
            q = self.query(**changes)
            pilot = [row for row in q['items'] if row['program'] == '174']
            self.assertTrue(pilot)
            for row in pilot:
                self.assertEqual(row['status'], 'detail_unavailable')
                self.assertIsNone(row['value'])
                self.assertIsNone(row['nominal_cents'])
            self.assertTrue(expected_proofs.issubset({row['row_id'] for row in q['proofs']}))
            self.assertFalse(q['evidence_scope']['applies_to_selection'])

    def test_mpr_isolation_and_subtraction_have_no_estimated_allocation(self):
        for mode in ['only', 'without']:
            q = self.query(topic='maprimerenov', topic_mode=mode)
            self.assertTrue(all(row['status'] == 'detail_unavailable' and row['value'] is None for row in q['items']))
            self.assertTrue(all('MaPrimeRénov' in row['reason'] for row in q['items']))

    def test_unrelated_scope_or_excluded_whole_programme(self):
        for changes in [dict(scope='VA/135'), dict(scope='TA/203'), dict(exclude=['TA/174']),
                        dict(exclude=['TA']), dict(scope='TA/174/02', exclude=['TA/174/02'])]:
            q = self.query(**changes)
            for key in ['items', 'proofs', 'table_totals', 'reconciliations', 'sources']:
                self.assertEqual(q[key], [], key)
        self.assertTrue(all(row['status'] == 'published' for row in self.query(exclude=['TA/203/01'])['items']))

    def test_source_hash_is_checked_again_on_every_query(self):
        before = self.query(start=2024, end=2024)
        self.assertTrue(all(row['source_verified'] for row in before['items']))
        source = before['sources'][0]['id']
        self.db.execute('UPDATE sources SET data=? WHERE id=?', (json.dumps({'sha256': '0' * 64}), source))
        after = self.query(start=2024, end=2024)
        self.assertNotEqual(before['selection_id'], after['selection_id'])
        self.assertTrue(after['items'])
        for row in after['items']:
            self.assertEqual(row['status'], 'source_unverified')
            for field in ['amount_cents', 'value', 'value_cents', 'nominal', 'nominal_cents', 'citation']:
                self.assertIsNone(row[field], field)
        for key in ['sources', 'proofs', 'table_totals', 'reconciliations']:
            self.assertEqual(after[key], [])

    def test_missing_catalogue_source_and_conflicting_evidence_hash_fail_closed(self):
        source = self.reg['sources'][0]['id']
        self.db.execute('DELETE FROM sources WHERE id=?', (source,))
        self.assertEqual(self.query(start=2023, end=2023)['proofs'], [])
        self.db.execute('INSERT INTO sources VALUES (?, ?)', (source, json.dumps(self.reg['sources'][0])))
        self.reg['evidence_rows'][0]['sha256'] = 'f' * 64
        self.assertEqual(self.query(start=2023, end=2023)['proofs'], [])

    def test_dates_retain_signature_or_month_precision(self):
        q = self.query()
        months = [row for row in q['items'] if row['date_kind'] == 'month']
        self.assertTrue(months)
        self.assertTrue(all(len(row['date']) == 7 and row['date_precision'] == 'month' for row in months))
        for row in q['items']:
            self.assertNotIn('publication_date', row)
            self.assertNotIn('effective_date', row)
        self.assertTrue(all(row['date_kind'] in ['month', 'signature'] for row in q['items']))

    def test_export_keeps_nulls_and_does_not_mutate_cached_registry(self):
        original = copy.deepcopy(self.reg)
        q = self.query()
        decoded = json.loads(json.dumps(q, ensure_ascii=False, allow_nan=False))
        self.assertEqual(decoded['proofs'], original['evidence_rows'])
        q['proofs'][0]['cells'][0]['amount_cents'] = 123
        self.assertEqual(self.reg, original)
        self.assertEqual(self.query()['proofs'], original['evidence_rows'])
        self.assertTrue(all('path' not in source for source in q['sources']))

    def test_partial_coverage_never_returns_mission_or_combined_total(self):
        q = self.query(start=2022, end=2026, scope='')
        self.assertEqual(q['years_without_integrated_rows'], [2022, 2026])
        for key in ['total', 'totals', 'events']:
            self.assertNotIn(key, q)
        self.assertEqual(q['evidence_scope']['grain'], 'programme')
        self.assertTrue(any(scope['program'] == '174' for scope in q['evidence_scope']['scopes']))

    def test_selection_changes_with_inflation_scope_or_registry(self):
        before = self.query()['selection_id']
        self.assertNotEqual(before, self.query(constant=True)['selection_id'])
        self.assertNotEqual(before, self.query(scope='TA')['selection_id'])
        self.meta['indices']['2025'] = 121
        self.assertNotEqual(before, self.query()['selection_id'])
        self.reg['updated_at'] = 'test-version'
        self.assertNotEqual(before, self.query()['selection_id'])

    def test_real_http_route_and_json_download_use_the_same_selection(self):
        from budget_service import web
        handler = object.__new__(web.Handler)
        handler.path = '/api/rap-movements?start=2024&end=2024&scope=TA/174&measure=AE&download=1'
        handler.reply = Mock()
        handler.headers={};handler.command='GET';handler.wfile=io.BytesIO();handler.send_headers=Mock()
        with patch.object(web.api, 'connect', return_value=self.db), patch.object(web.api, 'metadata', return_value=self.meta):
            with patch.object(web.consultation,'CACHE',web.consultation.ResponseCache(max_bytes=0)):
                handler.do_GET()
            if handler.wfile.tell():
                handler.reply(json.loads(handler.wfile.getvalue()),disposition=handler.send_headers.call_args.args[3])
        handler.reply.assert_called_once()
        result = handler.reply.call_args.args[0]
        self.assertEqual(result['parameters']['measure'], 'AE')
        self.assertEqual(result['parameters']['start'], 2024)
        self.assertTrue(result['items'])
        self.assertTrue(all(row['year'] == 2024 and row['measure'] == 'AE' for row in result['items']))
        self.assertEqual(handler.reply.call_args.kwargs['disposition'], 'attachment; filename=nos-deniers-mouvements-rap.json')
        self.assertEqual(json.loads(json.dumps(result))['proofs'], result['proofs'])


if __name__ == '__main__':
    unittest.main()
