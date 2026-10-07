from copy import deepcopy
import sqlite3
import unittest
from budget_service.correction_ledger import verify_historical,HISTORICAL_KEY
from budget_service.import_pap_2026_national import FIELDS


class HistoricalCanonicalAuditTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.execute('create table facts('+','.join(FIELDS)+')')
        self.row=dict(zip(FIELDS,(2021,'OUVERT','AE','BA','ZC','Mission','612','Programme','','','','','','',100,'a'*20,5,'RAP total',1)))
        self.proof=dict(source='a'*20,sha256='b'*64,page=5,stage='OUVERT',measure='AE',amount_cents=100,
                        selected_total_cell=dict(amount_cents=100,raw_text='1 €'),source_grain='programme_total_all_titles',
                        source_units='EUR',stored_units='integer_cents')
        scope={k:self.row[k]for k in HISTORICAL_KEY}
        self.change=dict(id='one',after=self.row,proof=self.proof,absence_key_fields=list(HISTORICAL_KEY),
                         canonical_absence_check=dict(database_sha256='c'*64,where=scope,matching_rows=0))
        aggregate={k:self.row[k]for k in ('year','stage','measure','budget','mission')}
        self.ledger=dict(id='historical',source_database_sha256='c'*64,independent_published_totals_modified=False,
                         fact_replacements=[],fact_insertions=[self.change],facts_added=1,
                         counts=dict(by_budget_stage={'BA/OUVERT':1},explicit_zero_facts=0),
                         affected_aggregate_adjustments=[dict(aggregate,previous_fact_sum_cents=0,correction_cents=100,
                                                             corrected_fact_sum_cents=100,correction_ids=['one'])])
        self.insert(self.row)

    def insert(self,row):
        self.db.execute('insert into facts values('+','.join('?'for _ in FIELDS)+')',tuple(row[k]for k in FIELDS))

    def source(self,sid,sha):
        self.assertEqual((sid,sha),('a'*20,'b'*64));return dict(pages=8)

    def verify(self):
        return verify_historical(self.db,{'historical_canonical_import':self.ledger},self.source)

    def test_exact_whole_programme_fact_and_printed_currency_suffix(self):
        result=self.verify();self.assertEqual(result['facts'],1);self.assertTrue(result['programme_scope_unique'])

    def test_title_or_action_competitor_in_another_mission_is_refused(self):
        self.insert(dict(self.row,title='2',action='01',mission='ZZ'))
        with self.assertRaises(AssertionError):self.verify()

    def test_existing_fact_change_is_refused(self):
        self.db.execute('update facts set cents=101')
        with self.assertRaises(AssertionError):self.verify()

    def test_bad_source_page_or_amount_is_refused(self):
        original=deepcopy(self.proof)
        for changes in (dict(sha256='f'*64),dict(page=6),dict(amount_cents=101),dict(measure='CP')):
            self.proof.clear();self.proof.update(original);self.proof.update(changes)
            with self.subTest(changes=changes),self.assertRaises(AssertionError):self.verify()

    def test_blank_cell_cannot_validate_a_zero(self):
        self.row['cents']=self.proof['amount_cents']=self.proof['selected_total_cell']['amount_cents']=0
        self.proof['selected_total_cell']['raw_text']=''
        self.db.execute('update facts set cents=0')
        with self.assertRaises(AssertionError):self.verify()

    def test_aggregate_and_absence_receipts_are_checked(self):
        self.ledger['affected_aggregate_adjustments'][0]['correction_cents']=101
        with self.assertRaises(AssertionError):self.verify()
        self.ledger['affected_aggregate_adjustments'][0]['correction_cents']=100
        self.change['canonical_absence_check']['matching_rows']=1
        with self.assertRaises(AssertionError):self.verify()

    def test_ba_annex_total_requires_identified_actual_credit_column(self):
        self.proof['source_grain']='programme_total_all_titles_including_FDC'
        with self.assertRaises(AssertionError):self.verify()
        self.proof.update(origin='independent_PLR_annex2_programme_total',column_header_cells=[{'text':'Total des autorisations'}],total_column_header={'text':'Total des autorisations'})
        self.assertEqual(self.verify()['facts'],1)
        self.proof['origin']='forecast_FDC_PLF'
        with self.assertRaises(AssertionError):self.verify()


if __name__=='__main__':unittest.main()
