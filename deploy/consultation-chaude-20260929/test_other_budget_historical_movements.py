import io
"""Regression tests for independently sourced historical movements outside BG."""
import copy
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from budget_service import rap_movements, rap_validation, web

class OtherBudgetHistoricalMovements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = rap_movements.other_budget_historical_registry()
        cls.registries = cls.data['registries']
        cls.previous_partial=json.loads((Path(__file__).parent/'fixtures/rap_ba_2019_p613_annual_adjustment.json').read_text(encoding='utf8'))
        cls.meta = {'indices': {str(y):100 for y in range(2017,2026)}, 'inflation_source':'test'}
    def database(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT)')
        for reg in self.registries:
            for source in reg['sources']:
                db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)', (source['id'],json.dumps(source)))
        self.addCleanup(db.close)
        return db
    def parameters(self, budget='CAS', year=2019, scope='YF/741', measure='AE', **changes):
        p = dict(start=year,end=year,budget=budget,measure=measure,scope=scope,exclude=[],constant=False,base=2025,topic='',topic_mode='only')
        p.update(changes)
        return p
    def chosen(self, year, program):
        return next(r for r in self.registries if r['scope']['years']==[year] and r['scope']['program']==program)
    def http(self, budget, year, scope, measure='AE', suffix=''):
        db=self.database();handler=object.__new__(web.Handler)
        handler.path=f'/api/rap-movements?budget={budget}&start={year}&end={year}&scope={scope}&measure={measure}'+suffix
        handler.reply=Mock()
        handler.headers={};handler.command='GET';handler.wfile=io.BytesIO();handler.send_headers=Mock()
        with patch.object(web.api,'connect',return_value=db),patch.object(web.api,'metadata',return_value=self.meta):
            with patch.object(web.consultation,'CACHE',web.consultation.ResponseCache(max_bytes=0)):
                handler.do_GET()
            if handler.wfile.tell():
                handler.reply(json.loads(handler.wfile.getvalue()),disposition=handler.send_headers.call_args.args[3])
        self.assertEqual(handler.reply.call_count,1)
        self.assertEqual(len(handler.reply.call_args.args),1,handler.reply.call_args)
        return handler.reply.call_args.args[0]
    def test_all_177_registries_preserve_budget_columns_and_independent_opened_proofs(self):
        self.assertEqual(len(self.registries),177)
        self.assertEqual({r['scope']['budget'] for r in self.registries},{'BA','CAS','CCF'})
        for reg in self.registries:
            rap_validation.validate_movements(reg)
            for obj in reg['items']+reg['evidence_rows']+reg['table_totals']:
                self.assertEqual(obj['budget'],reg['scope']['budget'])
            for total in reg['table_totals']:
                self.assertEqual([{'dépenses de personnel':'titre 2','autres dépenses':'autres titres'}.get(h['printed_label'].lower(),h['printed_label'].lower()) for h in total['headers']],['titre 2','autres titres']*4)
            for check in reg['reconciliations']:
                if reg.get('source_validation',{}).get('independent_annual_reference_check') is False:
                    self.assertEqual(check['status'],'annual_reference_unavailable')
                    self.assertIsNone(check['canonical_cents']);self.assertIsNone(check['difference_cents'])
                    self.assertFalse(check['canonical_reference_sql_fact']);continue
                self.assertIn(check['canonical_reference_origin'],('RAP_published_total','PLR_annex2_published_total'))
                self.assertTrue(check['canonical_reference_sql_fact'])
                proofs=[p for p in check['reference_proofs'] if p['stage']=='OUVERT']
                self.assertEqual(len(proofs),1)
                self.assertEqual(proofs[0]['amount_cents'],check['canonical_cents'])
                self.assertGreater(proofs[0]['page'],0)
                self.assertLessEqual(abs(check['difference_cents']),1000)
    def test_http_cas_and_ccf_keep_their_budgets_and_export_opened_source_cells(self):
        for year,program in [(2019,'741'),(2020,'834'),(2017,'624'),(2022,'612')]:
            reg=self.chosen(year,program);scope=reg['scope'];path=scope['mission']+'/'+program
            for measure in ('AE','CP'):
                result=self.http(scope['budget'],year,path,measure,'&download=1')
                expected=[i for i in reg['items'] if i['measure']==measure]
                self.assertEqual(result['count'],len(expected))
                self.assertEqual({i['budget'] for i in result['items']},{scope['budget']})
                self.assertTrue(all(i['status']=='published' and i['source_verified'] for i in result['items']))
                self.assertEqual(sum(i['nominal_cents'] for i in result['items']),sum(i['sign']*i['amount_cents'] for i in expected))
                self.assertTrue(result['proofs']);self.assertTrue(result['table_totals'])
                self.assertTrue(result['reconciliations'][0]['reference_proofs'])
                wrong=self.http('BG',year,path,measure)
                self.assertEqual(wrong['items'],[])
    def test_http_ba_partial_keeps_printed_movements_without_annual_zero(self):
        reg=self.previous_partial['partial']
        with patch.object(rap_movements,'_all_registries',return_value=[reg]):
            result=self.http('BA',2019,'XC/613')
        self.assertEqual(result['count'],len([x for x in reg['items'] if x['measure']=='AE']))
        self.assertTrue(result['items'])
        self.assertTrue(all(x['status']=='published' and x['annual_reconciliation_status']=='annual_reference_unavailable' for x in result['items']))
        self.assertTrue(all(x['value_cents'] is not None for x in result['items']))
        self.assertIsNone(result['reconciliations'][0]['canonical_cents'])
        self.assertIsNone(result['reconciliations'][0]['difference_cents'])
        self.assertEqual(result['reconciliations'][0]['status'],'annual_reference_unavailable')
        self.assertIn('avec tableaux détaillés vérifiés et rapprochement annuel indisponible',result['coverage'])

    def test_partial_contract_rejects_missing_proof_total_false_annual_and_category(self):
        original=self.previous_partial['partial']
        changes=[lambda r:r['source_validation'].pop('column_hierarchy_proofs'),
                 lambda r:r['table_totals'].pop(),
                 lambda r:r['reconciliations'][0].update(canonical_cents=0),
                 lambda r:r['source_validation']['column_hierarchy_proofs'][0]['direction_headers'][0].update(text='Annulations'),
                 lambda r:r['items'][0].update(kind='VIREMENT')]
        for change in changes:
            candidate=copy.deepcopy(original);change(candidate)
            with self.assertRaises((AssertionError,KeyError,StopIteration)):
                rap_validation.validate_movements(candidate)

    def test_former_partial_programmes_have_independent_annex_opened_proofs(self):
        keys={tuple(key) for key in self.previous_partial['original_partial_keys']}
        self.assertEqual(len(keys),18)
        plan=json.loads((rap_movements.DATA/'validated-fact-replay.json').read_text('utf8'))
        batches=[b for b in plan['correction_batches'] if b['ledger_meta_key']=='historical_canonical_import']
        self.assertEqual(len(batches),1)
        ledger=batches[0]['ledger'];self.assertEqual(ledger['facts_added'],589)
        inserted=[change['after'] for change in ledger['fact_insertions']]
        self.assertEqual(len(inserted),589);self.assertFalse(ledger['fact_replacements'])
        recovered=[c for c in ledger['fact_insertions'] if (c['after']['year'],c['after']['budget'],c['after']['program']) in keys and c['after']['stage']=='OUVERT']
        self.assertEqual(len(recovered),36)
        for c in recovered:
            self.assertEqual(c['proof']['origin'],'independent_PLR_annex2_programme_total')
            self.assertEqual(c['proof']['selected_total_cell']['amount_cents'],c['after']['cents'])
        all_ba_opened=[c for c in ledger['fact_insertions'] if c['after']['budget']=='BA' and c['after']['stage']=='OUVERT']
        self.assertEqual(len(all_ba_opened),60)
        self.assertEqual(len({(c['after']['year'],c['after']['program'],c['after']['measure']) for c in all_ba_opened}),60)
        for c in all_ba_opened:
            self.assertIn(c['proof']['origin'],('independent_PLR_annex2_programme_total','RAP_BA_explicit_opened_or_LFI_total','RAP_BA_explicit_programme_resources_total'))
            self.assertEqual(c['proof']['selected_total_cell']['amount_cents'],c['after']['cents'])
            self.assertTrue(c['proof']['selected_total_cell']['raw_text'].strip())
            self.assertEqual(c['proof']['source'],c['after']['source'])
            self.assertEqual(c['proof']['page'],c['after']['line'])
            self.assertGreater(c['proof']['page'],0)

    def test_p721_annual_zero_is_separate_from_dated_details(self):
        reg=next(r for r in rap_movements.historical_registry()['registries'] if r['scope']['budget']=='CAS' and r['scope']['program']=='721' and r['scope']['years']==[2018])
        self.assertTrue(reg['source_validation']['annual_total_only'])
        db=self.database()
        for source in reg['sources']:db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(source['id'],json.dumps(source)))
        q=rap_movements.query(db,self.parameters('CAS',2018,reg['scope']['mission']+'/721'),self.meta)
        self.assertTrue(q['items'])
        self.assertTrue(all(x['date_precision']=='annual' and x['kind']=='TOTAL' and x['value_cents']==0 for x in q['items']))
        self.assertEqual(q['proofs'][0]['row_kind'],'published_annual_total')
        self.assertIsNone(q['proofs'][0]['source_date'])
        self.assertNotIn(reg,rap_movements._historical_details())
        counts=rap_movements.historical_validation_counts()
        historical=[r for r in rap_movements._all_registries() if all(y<=2022 for y in r['scope']['years'])]
        self.assertEqual(sum(counts.values()),sum(len(rap_movements._registry_keys(r)) for r in historical))
        self.assertEqual(counts['detailed_reconciled']+counts['detailed_without_annual_reference'],848)

    def test_undeclared_source_hash_masks_other_budget_amounts_and_proofs(self):
        reg=self.chosen(2020,'834');p=self.parameters('CCF',2020,reg['scope']['mission']+'/834')
        db=self.database();before=rap_movements.query(db,p,self.meta)
        db.execute('UPDATE sources SET data=? WHERE id=?',(json.dumps({'sha256':'0'*64}),reg['sources'][0]['id']))
        after=rap_movements.query(db,p,self.meta)
        self.assertNotEqual(before['selection_id'],after['selection_id'])
        self.assertTrue(after['items'])
        self.assertTrue(all(i['status']=='source_unverified' and i['nominal_cents'] is None for i in after['items']))
        self.assertEqual(after['reconciliations'],[]);self.assertEqual(after['proofs'],[])
    def test_fine_scope_retains_proof_without_allocating_programme_movements(self):
        reg=self.chosen(2020,'834');path=reg['scope']['mission']+'/834'
        q=rap_movements.query(self.database(),self.parameters('CCF',2020,path+'/01'),self.meta)
        self.assertTrue(q['items']);self.assertTrue(q['proofs'])
        self.assertTrue(all(i['status']=='detail_unavailable' and i['nominal_cents'] is None for i in q['items']))
    def test_overlapping_registers_never_duplicate_a_year_or_discard_another_year(self):
        reg=copy.deepcopy(self.chosen(2020,'834'));mixed=copy.deepcopy(reg);mixed['scope']['years']=[2020,2021]
        for field in ('sources','items','evidence_rows','table_totals','reconciliations'):
            mixed[field]+= [dict(x,year=2021) for x in copy.deepcopy(mixed[field])]
        original=copy.deepcopy(mixed)
        result=rap_movements._unique_registries([reg,mixed,reg])
        self.assertEqual([r['scope']['years'] for r in result],[[2020],[2021]])
        self.assertEqual(sum(len(r['items']) for r in result),2*len(reg['items']))
        self.assertTrue(all(r['year']==2021 for r in result[1]['items']))
        self.assertEqual(mixed,original)
        with patch.object(rap_movements,'registry',return_value=reg),patch.object(rap_movements,'national_registry',return_value={'registries':[reg]}),patch.object(rap_movements,'historical_detail_registry',return_value={'registries':[reg]}),patch.object(rap_movements,'other_budget_historical_registry',return_value={'registries':[reg]}),patch.object(rap_movements,'historical_registry',return_value={'registries':[reg]}):
            self.assertEqual(len(rap_movements._all_registries()),1)
    def test_selection_version_covers_the_new_registry_file(self):
        reg=self.chosen(2020,'834');p=self.parameters('CCF',2020,reg['scope']['mission']+'/834');db=self.database()
        with patch.object(rap_movements,'_file_fingerprint',return_value='a'):
            old=rap_movements.query(db,p,self.meta)['selection_id']
        with patch.object(rap_movements,'_file_fingerprint',side_effect=lambda name:'b' if name=='mouvements-rap-autres-budgets-historique.json' else 'a'):
            new=rap_movements.query(db,p,self.meta)['selection_id']
        self.assertNotEqual(old,new)

if __name__=='__main__':
    unittest.main()
