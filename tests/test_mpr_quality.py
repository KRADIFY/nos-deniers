"""The explanation must not convert mixed envelopes into policy observations."""
import unittest
from budget_service import api, topics, data_quality


class MprQualityTests(unittest.TestCase):
    def setUp(self):
        self.p = api.parameters({'topic':['maprimerenov'],'start':['2020'],'end':['2026']})

    def explanation(self, year, stage, scope='', measure='CP', **kwargs):
        p = dict(self.p, measure=measure, **kwargs)
        cell = topics.subset(scope, year, stage, p, {})
        return cell, data_quality.mpr(cell, p, year, stage, scope)

    def test_programme_observations_and_independently_documented_national_totals(self):
        expected = {
            (2020,'PLF'):(390,390), (2021,'PLF'):(740,740),
            (2022,'PLF'):(1700,1390), (2023,'PLF'):(2450,2300),
            (2024,'PLF'):(2697,2065), (2021,'LFI'):(740,740),
            (2022,'LFI'):(1700,1390), (2023,'LFI'):(2450,2300),
        }
        for (year, stage), amounts in expected.items():
            for measure, millions in zip(('AE','CP'),amounts):
                with self.subTest(year=year,stage=stage,measure=measure):
                    for scope in ('TA','TA/174','TA/174/02'):
                        c,_ = self.explanation(year, stage, scope, measure)
                        self.assertEqual(c['nominal_cents'], millions*100000000)
                    c,x = self.explanation(year, stage, '', measure)
                    national = {(2020,'PLF'):(390,390), (2021,'PLF'):(2740,1655),
                                (2021,'LFI'):(2740,1655), (2022,'PLF'):(1700,1955.5)}
                    if (year,stage) in national:
                        self.assertEqual(c['nominal_cents'],round(national[year,stage][measure=='CP']*100000000))
                    else:
                        self.assertIsNone(c['value'])
                        self.assertEqual(x['known_components'][0]['cents'], millions*100000000)
        c,_ = self.explanation(2022,'OUVERT','TA/174/02')
        self.assertEqual(c['nominal_cents'],141900000000)
        self.assertIsNone(self.explanation(2022,'OUVERT')[0]['value'])

    def test_2025_and_2026_known_lfi_bricks_are_context_only(self):
        for year, cents in [(2025,77990000000),(2026,60460000000)]:
            c,x = self.explanation(year,'LFI')
            self.assertIsNone(c['value'])
            self.assertEqual(x['contextual_amounts'][0]['cents'],cents)
            self.assertEqual(x['contextual_amounts'][0]['source'],'270aaa96aa51346f908e')
            self.assertFalse(any(r['cents']==cents for r in topics.registry()['facts']))
            self.assertIn(str(year),x['request_text'])
            self.assertIn('CP',x['request_text'])
            self.assertEqual(len(x['contacts']),3)
        self.assertFalse(self.explanation(2026,'LFI',measure='AE')[1]['contextual_amounts'])
        self.assertFalse(self.explanation(2026,'LFI',scope='TA')[1]['contextual_amounts'])
        self.assertFalse(self.explanation(2026,'LFI',exclude=['VA'])[1]['contextual_amounts'])

    def test_mixed_anah_total_is_never_a_mpr_fact(self):
        for measure, cents in [('AE',210990000000),('CP',200560000000)]:
            c,x = self.explanation(2025,'EXEC',measure=measure)
            self.assertIsNone(c['nominal_cents'])
            self.assertEqual(x['contextual_amounts'][0]['cents'],cents)
            self.assertIn('autres aides',x['contextual_amounts'][0]['caution'])
            self.assertIn(('d2c406b7e2bc73904e50',122),[(r['source'],r['page']) for r in x['references']])

    def test_no_request_for_non_applicable_or_documented_zero(self):
        for year,stage,scope in [(2019,'LFI',''),(2025,'EXEC','TA')]:
            c,x = self.explanation(year,stage,scope)
            self.assertEqual(x['contacts'],[])
            self.assertEqual(x['request_text'],'')

    def test_inflation_missing_is_not_missing_budget(self):
        c,x = self.explanation(2024,'EXEC','TA',constant=True,base=2025)
        self.assertEqual(c['status'],'inflation_missing')
        self.assertIn('indice annuel',x['details'][0])
        self.assertFalse(x['contacts'])
        self.assertTrue(c['nominal_cents'])

    def test_current_year_execution_is_explicitly_unfinished(self):
        c,x = self.explanation(2026,'EXEC')
        self.assertIsNone(c['value'])
        self.assertIn('exercice 2026 est en cours',' '.join(x['details']))

    def test_available_amount_keeps_precision_and_scope_warning(self):
        c,x = self.explanation(2024,'PLF','TA')
        self.assertTrue(c['approximate'])
        self.assertIn('part rattachée à la mission Écologie',' '.join(x['details']))
        self.assertFalse(x['contextual_amounts'])
        self.assertFalse(x['contacts'])

    def test_general_missing_means_not_imported_not_nonexistent(self):
        p=dict(self.p,topic='')
        c=api.cell([], 'TA', 2024, 'EXEC', p, {})
        x=data_quality.general(c,p,2024,'EXEC','TA')
        self.assertIn('Aucune valeur importée',x['summary'])
        self.assertIn('ne prouve',x['details'][0])
        self.assertIn('TA',x['request_text'])

    def test_known_policy_cannot_be_subtracted_without_parent_total(self):
        p=dict(self.p,topic_mode='without')
        base=api.cell([], 'TA', 2022, 'OUVERT', p, {})
        result=topics.calculate([],base,'TA',2022,'OUVERT',p,{})
        x=data_quality.mpr(result,p,2022,'OUVERT','TA')
        self.assertIsNone(result['value'])
        self.assertEqual(x['title'],'Total de départ nécessaire au retrait')
        self.assertEqual(x['known_components'][0]['cents'],141900000000)
        self.assertEqual(len(x['contacts']),1)
        self.assertIn('les crédits budgétaires',x['request_text'])
