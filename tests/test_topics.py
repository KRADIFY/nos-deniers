import csv
import io
import unittest
from budget_service import api, topics
from budget_service.model import STAGES, constant_cents


def fact(program, euros, mission='TA', stage='EXEC'):
    return dict(year=2024, stage=stage, measure='CP', budget='BG',
                mission=mission, mission_label=mission, program=program,
                program_label=program, action='', action_label='', subaction='',
                subaction_label='', category='', title='', cents=euros*100,
                source='parent', line=1, field=stage, approximate=0)


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.p=api.parameters({'topic':['maprimerenov']})

    def test_independent_official_table_totals_and_no_duplicate_facts(self):
        expected={2021:(2119900000,1259900000),2022:(2276400000,2101700000),
                  2023:(2411654906,1887372951)}
        for year, amounts in expected.items():
            for measure, amount in zip(('AE','CP'),amounts):
                c=topics.subset('',year,'EXEC',dict(self.p,measure=measure),{})
                self.assertEqual(c['nominal_cents'],amount*100)
        rows=topics.registry()['facts']
        keys=[(r['year'],r['measure'],r['stage'],r['program']) for r in rows]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertIsNone(topics.subset('',2024,'LFI',self.p,{})['value'])
        self.assertIsNone(topics.subset('',2024,'OUVERT',self.p,{})['value'])

    def test_mission_subset_does_not_include_other_missions(self):
        self.assertEqual(topics.subset('TA',2024,'EXEC',self.p,{})['value'],692017721)
        self.assertIsNone(topics.subset('VA',2024,'EXEC',self.p,{})['value'])
        self.assertEqual(topics.subset('PR',2023,'EXEC',self.p,{})['value'],287100000)

    def test_creation_date_is_not_a_zero_and_exclusion_preserves_earlier_budgets(self):
        self.assertEqual(topics.subset('',2019,'EXEC',self.p,{})['status'],'not_applicable')
        base={'value':123,'nominal':123,'status':'ok'}
        self.assertEqual(topics.calculate([],base,'',2019,'EXEC',dict(self.p,topic_mode='without'),{}),base)

    def test_mixed_anah_envelope_never_becomes_a_policy_amount(self):
        for year in (2025,2026):
            self.assertIsNone(topics.subset('',year,'EXEC',self.p,{})['value'])
        self.assertIsNone(topics.subset('',2024,'PLF',self.p,{})['value'])

    def test_real_zero_is_retained(self):
        value=topics.subset('PR/362',2023,'EXEC',dict(self.p,measure='AE'),{})
        self.assertEqual(value['value'],0)
        self.assertEqual(value['status'],'ok')
        self.assertTrue(value['sources'])

    def test_subtracts_policy_amount_and_keeps_remaining_program(self):
        rows=[fact('174',1000000000),fact('203',2000000000)]
        p=dict(self.p,topic_mode='without')
        base=api.cell(rows,'TA',2024,'EXEC',p,{})
        result=topics.calculate(rows,base,'TA',2024,'EXEC',p,{})
        self.assertEqual(result['value'],2307982279)
        self.assertEqual(result['topic_subtracted_nominal'],692017721)
        self.assertEqual(result['status'],'ok')

    def test_nominal_subtraction_precedes_inflation_rounding(self):
        rows=[fact('174',1000000001),fact('203',2000000000)]
        p=dict(self.p,topic_mode='without',constant=True)
        indices={2024:'99.07',2025:'100'}
        base=api.cell(rows,'TA',2024,'EXEC',p,indices)
        result=topics.calculate(rows,base,'TA',2024,'EXEC',p,indices)
        expected=constant_cents(230798228000,2024,2025,indices)
        self.assertEqual(round(result['value']*100),expected)

    def test_explicit_program_exclusion_is_not_subtracted_twice(self):
        rows=[fact('174',1000000000),fact('203',2000000000)]
        p=dict(self.p,topic_mode='without',exclude=['TA/174','TA/174/02'])
        base=api.cell(rows,'TA',2024,'EXEC',p,{})
        result=topics.calculate(rows,base,'TA',2024,'EXEC',p,{})
        self.assertEqual(result['value'],2000000000)

    def test_no_guessed_allocation_to_action_or_subaction(self):
        for scope in ('VA/135/04','TA/174/02/01'):
            self.assertEqual(topics.subset(scope,2024,'EXEC',self.p,{})['status'],'detail_unavailable')
        self.assertEqual(topics.subset('TA/174/02',2024,'LFI',self.p,{})['status'],'detail_unavailable')
        self.assertEqual(topics.subset('TA/174/02',2022,'EXEC',self.p,{})['status'],'detail_unavailable')
        p=dict(self.p,exclude=['TA/174/02'])
        self.assertIsNone(topics.subset('',2024,'EXEC',p,{})['value'])

    def test_documented_action_allows_mpr_and_remainder_without_program_allocation(self):
        from budget_service import action_details
        from tests.test_action_details import SourceDB
        import copy
        for year,amount in [(2023,1216572951),(2024,692017721)]:
            group=next(g for g in action_details.registry()[0]['groups'] if (g['year'],g['stage'],g['measure'],g['program'])==(year,'EXEC','CP','174'))
            records=action_details.attach([copy.deepcopy(group['parent'])],SourceDB())
            p=dict(self.p,topic_mode='without')
            base=api.cell(records,'TA/174/02',year,'EXEC',p,{})
            subset=topics.subset('TA/174/02',year,'EXEC',p,{})
            rest=topics.calculate(records,base,'TA/174/02',year,'EXEC',p,{})
            self.assertEqual(subset['value'],amount)
            self.assertEqual(rest['nominal_cents']+subset['nominal_cents'],base['nominal_cents'])
            self.assertEqual({r['page'] for r in rest['citations']},{421,439} if year==2023 else {426,446})
            links=api.exports.citation_urls(rest,{})
            for citation in rest['citations']:
                self.assertIn('#page='+str(citation['page']),links)
            p=dict(p,exclude=['TA/174/02'])
            base=api.cell(records,'TA/174',year,'EXEC',p,{})
            self.assertEqual(topics.calculate(records,base,'TA/174',year,'EXEC',p,{}),base)
            p=dict(p,exclude=['TA/174/03'])
            base=api.cell(records,'TA/174',year,'EXEC',p,{})
            rest=topics.calculate(records,base,'TA/174',year,'EXEC',p,{})
            self.assertEqual(rest['nominal_cents'],base['nominal_cents']-amount*100)

    def test_missing_parent_prevents_subtraction_even_with_known_policy(self):
        rows=[fact('203',2000000000)]
        p=dict(self.p,topic_mode='without')
        base=api.cell(rows,'TA',2024,'EXEC',p,{})
        self.assertIsNone(topics.calculate(rows,base,'TA',2024,'EXEC',p,{})['value'])

    def test_policy_cannot_exceed_parent_and_missing_base_is_not_zero(self):
        p=dict(self.p,topic_mode='without')
        for rows in ([],[fact('174',600000000)]):
            base=api.cell(rows,'TA',2024,'EXEC',p,{})
            self.assertIsNone(topics.calculate(rows,base,'TA',2024,'EXEC',p,{})['value'])

    def test_unaffected_program_and_other_budgets_keep_their_amount(self):
        base={'value':100,'status':'ok'}
        p=dict(self.p,topic_mode='without')
        self.assertEqual(topics.calculate([],base,'TA/203',2025,'EXEC',p,{}),base)
        self.assertEqual(topics.calculate([],base,'',2024,'EXEC',dict(p,budget='CAS'),{}),base)
        self.assertEqual(topics.subset('',2024,'EXEC',dict(p,budget='CAS'),{})['status'],'not_applicable')

    def test_query_validation(self):
        for query in ({'topic':['unknown']},{'topic_mode':['all']},{'topic':['../../file']}):
            with self.assertRaises(ValueError): api.parameters(query)

    def test_export_carries_perimeter_precision_and_pdf_page(self):
        annual={s:topics.subset('TA',2024,s,self.p,{}) for s in STAGES}
        annual['year']=2024
        data=dict(parameters=self.p,totals=[annual],rows=[],scope_label='MaPrimeRénov’',exclusions=[],topic=topics.description(self.p))
        records=list(csv.DictReader(io.StringIO(api.export_csv(data).decode('utf-8-sig')),delimiter=';'))
        executed=next(r for r in records if r['Étape']==STAGES['EXEC'])
        self.assertEqual(executed['Montant EUR'],'692017721,0')
        self.assertEqual(executed['Dossier'],'MaPrimeRénov’')
        self.assertIn('#page=446',executed['Sources officielles'])
        self.assertIn('1 € (RAP)',executed['Précision source'])
        missing=next(r for r in records if r['Étape']==STAGES['FDC'])
        self.assertEqual(missing['Montant EUR'],'')

    def test_rap_refinement_retains_old_observations_without_adding_them(self):
        history=[h for h in topics.registry()['observation_history'] if 'replaced_at' in h]
        self.assertEqual(len(history),4)
        expected={(2023,'AE'):202795490600,(2023,'CP'):121657295100,
                  (2024,'AE'):116800000000,(2024,'CP'):69201772100}
        for h in history:
            old=h['observation']
            row=next(r for r in topics.registry()['facts'] if (r['year'],r['stage'],r['measure'],r['program'])==(old['year'],old['stage'],old['measure'],old['program']))
            self.assertEqual(row['cents'],expected[(row['year'],row['measure'])])
            self.assertLessEqual(abs(row['cents']-old['cents']),5000000)
            self.assertEqual(row['page'],439 if row['year']==2023 else 446)
            self.assertEqual(row['precision'],'1 € (RAP)')
            self.assertEqual(old['source'],'296835325a7d511d6a5a')
        self.assertEqual(len(topics.registry()['facts']),65)


if __name__=='__main__': unittest.main()
