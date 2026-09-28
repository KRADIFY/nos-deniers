"""Exercise coverage gaps and keep unallocated device figures out of calculations."""
import json
import sqlite3
import unittest
from budget_service import rap_movements, reserves, rap_quality


class RapQualityTests(unittest.TestCase):
    def setUp(self):
        self.p = dict(start=2023,end=2025,budget='BG',measure='CP',scope='',exclude=[],
                      constant=False,base=2025,topic='',topic_mode='only')
        self.meta = {'indices':{'2023':100,'2024':110,'2025':120}}
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT)')
        sources = rap_quality.registry()[0]['sources'] + [s for r in rap_movements._all_registries() for s in r['sources']]
        for s in sources:
            self.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?)',(s['id'],json.dumps(s)))

    def movements(self, **changes):
        return rap_movements.query(self.db,dict(self.p,**changes),self.meta)

    def reserve(self, **changes):
        return reserves.query(dict(self.p,**changes),self.meta)

    def test_audited_programmes_visible_including_missing_tables(self):
        result = self.reserve()
        self.assertEqual((result['count'],result['integrated_table_count'],result['programmes_without_table_count']),(379,331,48))
        keys = {(r['year'],r['path'],r['measure']) for r in result['items']}
        self.assertEqual(len(keys),379)
        self.assertEqual(len(self.movements()['programmes_without_recap']),22)

    def test_exemption_is_evidenced_not_a_zero(self):
        row = self.reserve(scope='AD/384',start=2025)['items'][0]
        self.assertFalse(row['table_available'])
        for cell in row['cells'].values():
            self.assertIsNone(cell['value'])
            self.assertEqual(cell['status'],'not_applicable')
            self.assertIn('aucune mesure de mise en réserve',cell['explanation']['summary'])
            self.assertTrue(any(r['page']==146 for r in cell['explanation']['references']))
            self.assertEqual(cell['explanation']['contacts'],[])
        # An exemption from reserve does not mean absence of other movements.
        gap = self.movements(scope='AD/384',start=2025)['programmes_without_recap'][0]
        self.assertIn('reports automatiques',gap['explanation']['summary'])
        self.assertEqual(gap['status'],'table_unavailable')

    def test_unknown_reserve_table_is_not_exempt_or_zero(self):
        cell = self.reserve(scope='EB/114',start=2024,end=2024)['items'][0]['cells']['initial']
        self.assertEqual(cell['status'],'table_unavailable')
        self.assertIsNone(cell['value'])
        self.assertIn('ni un montant nul', ' '.join(cell['explanation']['details']))
        self.assertIn('EB/114',cell['explanation']['request_text'])
        self.assertIn('2024, CP',cell['explanation']['request_text'])

    def test_movement_device_filter_preserves_other_programmes_and_proofs(self):
        full = self.movements(scope='TA',start=2024,end=2024)
        without = self.movements(scope='TA',start=2024,end=2024,topic='maprimerenov',topic_mode='without')
        original = {r['id']:r for r in full['items']}
        self.assertTrue(any(r['program']=='203' for r in without['items']))
        for row in without['items']:
            if row['program']=='174':
                self.assertIsNone(row['value'])
                self.assertEqual(row['status'],'detail_unavailable')
                self.assertIn('MaPrimeRénov',row['explanation']['request_text'])
            else:
                self.assertEqual(row,original[row['id']])
        only = self.movements(scope='TA',start=2024,end=2024,topic='maprimerenov')
        self.assertEqual({r['program'] for r in only['items']},{'174'})
        self.assertEqual(only['proofs'],[r for r in rap_movements.registry()['evidence_rows'] if r['year']==2024])
        self.assertFalse(only['evidence_scope']['applies_to_selection'])

    def test_gap_selection_obeys_programme_year_and_exclusions(self):
        gaps = self.movements(scope='AD',start=2024,end=2024,exclude=['AD/365'])['programmes_without_recap']
        self.assertEqual([(r['year'],r['program']) for r in gaps],[(2024,'370')])
        self.assertIn('13 mars 2025',gaps[0]['explanation']['summary'])
        self.assertIn('2025',gaps[0]['explanation']['summary'])
        self.assertEqual(self.movements(budget='BA')['programmes_without_recap'],[])
        self.assertEqual(self.movements(topic='maprimerenov')['programmes_without_recap'],[])

    def test_narrative_absence_does_not_generate_dated_zero(self):
        q = self.movements(scope='AD/370',start=2023,end=2023)
        self.assertEqual(q['items'],[])
        gap = q['programmes_without_recap'][0]
        self.assertIn('aucune ouverture de crédit',gap['explanation']['summary'])
        self.assertEqual(gap['explanation']['references'][0]['page'],159)

    def test_unverified_gap_does_not_offer_a_verified_reference(self):
        q = self.movements(scope='AD/370',start=2023,end=2023)
        self.db.execute('DELETE FROM sources WHERE id=?',(q['programmes_without_recap'][0]['source'],))
        gap = self.movements(scope='AD/370',start=2023,end=2023)['programmes_without_recap'][0]
        self.assertEqual(gap['status'],'source_unverified')
        self.assertEqual(gap['explanation']['references'],[])

    def test_missing_line_and_printed_difference_have_specific_explanations(self):
        row = self.reserve(scope='TA/217',start=2023,end=2023)['items'][0]
        self.assertEqual(row['cells']['remaining']['value'],25941092)
        self.assertIn('1 €',row['cells']['remaining']['explanation']['summary'])
        missing = row['cells']['cancellations']
        self.assertIsNone(missing['value'])
        self.assertIn('dégel peut précéder une annulation',' '.join(missing['explanation']['details']))

    def test_fine_scope_request_does_not_guess_allocation(self):
        cell = self.reserve(scope='TA/203/41',start=2024,end=2024)['items'][0]['cells']['initial']
        self.assertIsNone(cell['value'])
        self.assertIn('TA/203/41',cell['explanation']['request_text'])
        self.assertTrue(cell['explanation']['references'])

    def test_2026_has_dated_situation_explanation_without_annual_figures(self):
        for q in (self.reserve(start=2026,end=2026), self.movements(start=2026,end=2026)):
            self.assertEqual(q['items'],[])
            note = q['year_explanations'][0]['explanation']
            self.assertIn('exercice est en cours',' '.join(note['details']))
            self.assertIn('dernière situation disponible',note['request_text'])

    def test_historical_complete_net_does_not_invent_dated_movements(self):
        row=next(r for r in rap_quality.registry()[0]['investigations']if r['year']<2023 and r.get('annual_net_cents') is not None)
        p=dict(self.p,start=row['year'],end=row['year'],budget=row['budget'],scope=row['mission']+'/'+row['program'])
        q=rap_movements.query(self.db,p,self.meta)
        self.assertFalse(q['items'])
        gap=q['programmes_without_recap'][0]
        self.assertEqual(gap['status'],'table_unavailable')
        self.assertEqual(gap['explanation']['contextual_amounts'][0]['cents'],0)
        self.assertIn('Un solde nul ne prouve pas',gap['explanation']['contextual_amounts'][0]['caution'])
        fine=rap_movements.query(self.db,dict(p,scope=p['scope']+'/01'),self.meta)
        self.assertFalse(fine['items'])
        self.assertIn('sans ventilation',fine['programmes_without_recap'][0]['explanation']['contextual_amounts'][0]['caution'])

    def test_historical_recovered_annual_references_do_not_create_dated_movements(self):
        registry=rap_quality.registry()[0]
        rows=[r for r in registry['investigations'] if r['year']<2023]
        self.assertFalse([r for r in rows if r.get('outcome')=='annual_reference_partial_dated_table_absent'])
        recovered={
            (2019,'CAS','721'):{('OUVERT','AE'),('OUVERT','CP')},
            (2019,'CAS','796'):{('OUVERT','AE'),('OUVERT','CP')},
            (2019,'CCF','854'):{('OUVERT','AE'),('OUVERT','CP')},
            (2019,'CCF','853'):{('OUVERT','AE')},
            (2018,'CCF','869'):{('LFI','CP'),('OUVERT','CP')},
        }
        sources={s['id']:s for s in registry['sources']}
        checked=[]
        for key,expected in recovered.items():
            with self.subTest(programme=key):
                matches=[r for r in rows if (r['year'],r['budget'],r['program'])==key]
                self.assertEqual(len(matches),1)
                row=matches[0]
                self.assertEqual(row['outcome'],'annual_reference_available_dated_table_absent')
                cells={(c['stage'],c['measure']):c['amount_cents'] for c in row['annual_reference_cells']}
                self.assertEqual(set(cells),{(stage,measure) for stage in ('LFI','OUVERT') for measure in ('AE','CP')})
                for stage,measure in expected:
                    proofs=[p for p in row['annual_summary_proofs'] if (p['stage'],p['measure'])==(stage,measure)]
                    self.assertEqual(len(proofs),1)
                    proof=proofs[0];checked.append(proof)
                    self.assertEqual(cells[stage,measure],0)
                    self.assertEqual(proof['amount_cents'],0)
                    self.assertEqual(proof['sha256'],sources[proof['source']]['sha256'])
                    self.assertGreater(proof['page'],0)
                    self.assertTrue(proof['headers']);self.assertTrue(proof['cells'])
                    if (key,stage,measure)==((2018,'CCF','869'),'OUVERT','CP'):
                        self.assertEqual(proof['kind'],'exact_algebraic_reconstruction_from_published_balance')
                        self.assertIsNone(proof['selected_total_cell'])
                        self.assertEqual(proof['blank_published_opened_cell']['raw_text'],'')
                        self.assertEqual(proof['derivation']['operator'],'add')
                        self.assertEqual([t['role'] for t in proof['derivation']['terms']],['consumed','opened_minus_consumed'])
                        self.assertEqual([c['raw_text'] for c in proof['cells']],['0','0'])
                        self.assertEqual(sum(c['amount_cents'] for c in proof['cells']),proof['derivation']['result_cents'])
                        self.assertEqual(proof['derivation']['result_cents'],0)
                    else:
                        self.assertEqual(proof['kind'],'direct_published_cell')
                        self.assertEqual(proof['selected_total_cell']['raw_text'],'0')
                        self.assertEqual(proof['selected_total_cell']['amount_cents'],0)
                for measure in ('AE','CP'):
                    q=self.movements(start=row['year'],end=row['year'],budget=row['budget'],measure=measure,scope=row['mission']+'/'+row['program'])
                    self.assertEqual(q['items'],[])
                    self.assertEqual(len(q['programmes_without_recap']),1)
                    gap=q['programmes_without_recap'][0]
                    self.assertEqual(gap['status'],'table_unavailable')
                    amounts=gap['explanation']['contextual_amounts']
                    self.assertEqual(len(amounts),1)
                    self.assertEqual(amounts[0]['cents'],0)
                    self.assertIn('Un solde nul ne prouve pas',amounts[0]['caution'])
                    self.assertTrue(gap['explanation']['references'])
        self.assertEqual(len(checked),9)
        self.assertEqual(sum(p['kind']=='direct_published_cell' for p in checked),8)


if __name__=='__main__':
    unittest.main()
