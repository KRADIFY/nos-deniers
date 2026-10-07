"""Source-backed annual AE adjustments must never become dated RAP movements."""
import copy,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
from budget_service import rap_movements,rap_validation

class AnnualAEAdjustments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=json.loads((Path(__file__).parent/'fixtures/rap_ba_2019_p613_annual_adjustment.json').read_text(encoding='utf8'))
        cls.complete=fixture['complete'];cls.partial=fixture['partial']
    def query(self,registry=None,scope='XC/613',bad_source=False,measure='AE'):
        reg=registry or self.complete;db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY,data TEXT)')
        for source in reg['sources']:
            metadata=dict(source)
            if bad_source and source['id']==reg['annual_adjustments'][0]['source']:metadata['sha256']='0'*64
            db.execute('INSERT INTO sources VALUES (?,?)',(source['id'],json.dumps(metadata)))
        p=dict(start=2019,end=2019,budget='BA',measure=measure,scope=scope,exclude=[],constant=False,base=2025,topic='',topic_mode='only')
        with patch.object(rap_movements,'_all_registries',return_value=[reg]),patch.object(rap_movements.rap_quality,'gaps',return_value=[]):
            return rap_movements.query(db,p,{'indices':{'2019':100,'2025':100}})
    def test_both_previous_partial_and_completed_fixture_validate(self):
        rap_validation.validate_movements(self.partial);rap_validation.validate_movements(self.complete)
        for key in ('items','evidence_rows','table_totals'):
            self.assertEqual(self.partial[key],self.complete[key])
    def test_exact_published_recycling_amount_changes_only_annual_identity(self):
        rec=next(r for r in self.complete['reconciliations'] if r['measure']=='AE')
        self.assertEqual(rec['annual_adjustment_cents'],50924129)
        self.assertEqual(rec['lfi_plus_reported_cents'],150699386700)
        self.assertEqual(rec['reconciled_total_cents'],150750310829)
        self.assertEqual(rec['canonical_cents'],150750310798)
        self.assertEqual(rec['difference_cents'],31)
    def test_rejects_adjustment_without_proof_or_wrong_cell_header_date_scope(self):
        changes=[lambda a:a.pop('proof'),lambda a:a.update(amount_cents=a['amount_cents']+1),
                 lambda a:a['proof']['selected_total_cell'].update(raw_text='1,00'),
                 lambda a:a['proof']['column_header_cells'][0].update(text='Rétablissement de crédits'),
                 lambda a:a.update(date='2019-12-31'),lambda a:a.update(measure='CP'),
                 lambda a:a.update(program='612'),lambda a:a['proof'].update(page=999),
                 lambda a:a.update(sha256='0'*64),lambda a:a['proof']['selected_total_cell'].update(visual_column_bounds=[0,1])]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                reg=copy.deepcopy(self.complete);change(reg['annual_adjustments'][0])
                with self.assertRaises((AssertionError,KeyError)):rap_validation.validate_movements(reg)
    def test_rejects_duplicate_recycling_and_unlinked_free_sum(self):
        for mode in ('duplicate','free_sum','missing_adjustment','date_item'):
            reg=copy.deepcopy(self.complete)
            if mode=='duplicate':reg['annual_adjustments'].append(copy.deepcopy(reg['annual_adjustments'][0]))
            elif mode=='free_sum':reg['reconciliations'][0]['annual_adjustment_cents']+=1
            elif mode=='missing_adjustment':reg['annual_adjustments']=[]
            else:reg['items'].append(dict(reg['annual_adjustments'][0],row_id='invented'))
            with self.assertRaises((AssertionError,KeyError)):rap_validation.validate_movements(reg)
    def test_api_exposes_separate_annual_amount_citation_and_no_false_date(self):
        result=self.query();adjustment=result['annual_adjustments'][0]
        self.assertEqual(adjustment['value_cents'],50924129);self.assertIsNone(adjustment['date'])
        self.assertEqual(adjustment['date_precision'],'annual');self.assertEqual(adjustment['status'],'published')
        self.assertIn('#page=112',adjustment['citation']['url']);self.assertIn('Annexe 2',adjustment['citation']['label'])
        expected=[i for i in self.complete['items'] if i['measure']=='AE']
        self.assertEqual(result['count'],len(expected))
        self.assertEqual(sum(i['nominal_cents'] for i in result['items']),sum(i['sign']*i['amount_cents'] for i in expected))
        self.assertNotIn(adjustment['id'],[i['id'] for i in result['items']])
        self.assertEqual(rap_movements.page_result(result)['annual_adjustments'],result['annual_adjustments'])
    def test_source_hash_failure_hides_annual_amount_and_reconciliation_only(self):
        result=self.query(bad_source=True)
        self.assertEqual(result['annual_adjustments'],[]);self.assertEqual(result['reconciliations'],[])
        self.assertTrue(result['items']);self.assertTrue(all(i['status']=='published' for i in result['items']))
    def test_no_fine_scope_allocation_and_no_cp_recycling(self):
        fine=self.query(scope='XC/613/01')['annual_adjustments'][0]
        self.assertEqual(fine['status'],'detail_unavailable');self.assertIsNone(fine['nominal_cents']);self.assertIsNone(fine['value_cents'])
        self.assertEqual(self.query(measure='CP')['annual_adjustments'],[])
    def test_unique_registry_year_trimming_covers_annual_adjustments(self):
        one=copy.deepcopy(self.complete);mixed=copy.deepcopy(one);mixed['scope']['years']=[2019,2020]
        for key in ('sources','items','evidence_rows','table_totals','reconciliations','annual_adjustments'):
            mixed[key].extend(dict(x,year=2020) for x in copy.deepcopy(mixed[key]))
        regs=rap_movements._unique_registries([one,mixed])
        self.assertEqual(len(regs),2);self.assertEqual([x['year'] for x in regs[1]['annual_adjustments']],[2020])

if __name__=='__main__':unittest.main()
