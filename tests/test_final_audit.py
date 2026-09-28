"""Independent financial cases and regression guards from the final review."""
import unittest
from budget_service import api, topics, events, data_quality

class FinalAuditTests(unittest.TestCase):
    def test_source_difference_follows_only_contributing_lines(self):
        rows=[dict(source='a',line=147),dict(source='b',line=2)]
        issues=[dict(source='a',row=147,kind='opening_identity',difference_cents=-40246200),
                dict(source='a',row=3,kind='opening_identity',difference_cents=100)]
        notes=data_quality.source_discrepancies(rows,issues)
        self.assertEqual(len(notes),1)
        self.assertIn('402 462,00 €',notes[0])
        self.assertFalse(data_quality.source_discrepancies([],issues))

    def p(self, **extra):
        return dict(api.parameters({'start':['2020'],'end':['2026'],'topic':['maprimerenov']}),**extra)

    def test_2020_funding_transfer_reconciles_once(self):
        for stage, amounts in [('PLF',(390,390)),('LFI',(390,390)),('OUVERT',(575,575)),('EXEC',(575,455))]:
            for measure, millions in zip(('AE','CP'), amounts):
                p=self.p(measure=measure)
                c=topics.subset('',2020,stage,p,{})
                self.assertEqual(c['nominal_cents'],millions*100000000)
                self.assertEqual(c['count'],1)
                self.assertTrue(any(x['path']=='VA/135' for x in c['evidence']))

    def test_lfi2021_is_not_lfr_or_multiyear_total(self):
        for measure, expected in [('AE',2740000000),('CP',1655000000)]:
            c=topics.subset('',2021,'LFI',self.p(measure=measure),{})
            self.assertEqual(c['nominal'],expected)
        self.assertIsNone(topics.subset('',2021,'OUVERT',self.p(),{})['value'])

    def test_plf2022_does_not_impute_lfi_or_future_collectives(self):
        self.assertEqual(topics.subset('',2022,'PLF',self.p(),{})['nominal'],1955500000)
        self.assertIsNone(topics.subset('',2022,'LFI',self.p(),{})['value'])
        self.assertIsNone(topics.subset('',2022,'OUVERT',self.p(),{})['value'])

    def test_excluding_carrier_keeps_only_the_other_funding(self):
        p=self.p(exclude=['TA/174'])
        self.assertEqual(topics.subset('',2021,'LFI',p,{})['nominal'],915000000)

    def test_inflation_applies_after_nominal_funding_sum(self):
        p=self.p(constant=True,base=2025)
        c=topics.subset('',2021,'LFI',p,{2021:'100',2025:'110'})
        self.assertEqual(c['nominal'],1655000000)
        self.assertEqual(c['value'],1820500000)

    def event(self, mission='TA', program='345', year=2024):
        return dict(year=year,budget='BG',measure='CP',mission=mission,program=program,
                    amount_cents=10000,sign=-1,publication_date=f'{year}-02-22',act_id='act',action='',subaction='')

    def test_policy_exclusion_preserves_unrelated_programme_events(self):
        rows=events.select([self.event()],self.p(topic_mode='without'),{})
        self.assertEqual(rows[0]['value'],-100)
        self.assertEqual(rows[0]['nominal'],-100)
        self.assertEqual(events.select([self.event()],self.p(topic_mode='only'),{}),[])

    def test_ambiguous_event_has_no_usable_selection_amount(self):
        for mode in ('only','without'):
            row=events.select([self.event(program='174')],self.p(topic_mode=mode),{})[0]
            self.assertEqual(row['status'],'detail_unavailable')
            self.assertIsNone(row['value']);self.assertIsNone(row['nominal'])

    def test_before_creation_does_not_hide_unrelated_annual_event(self):
        p=self.p(start=2019,end=2019)
        row=self.event(program='174',year=2019)
        self.assertEqual(events.select([row],dict(p,topic_mode='only'),{})[0]['status'],'not_applicable')
        self.assertEqual(events.select([row],dict(p,topic_mode='without'),{})[0]['value'],-100)

if __name__=='__main__':unittest.main()
