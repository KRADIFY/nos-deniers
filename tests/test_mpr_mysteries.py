"""Independent safeguards for the September 2026 documentary MPR corrections.

Expected figures come from NEB/RAP pages reviewed separately; no active database,
network, model, or candidate-builder is involved in these tests.
"""
import csv
import io
import unittest
from datetime import datetime

from budget_service import api, data_quality, topics
from budget_service.model import STAGES


def parent(program, cents, mission='TA', year=2024, stage='EXEC', measure='CP'):
    return dict(year=year, stage=stage, measure=measure, budget='BG',
                mission=mission, mission_label=mission, program=program,
                program_label=program, action='', action_label='', subaction='',
                subaction_label='', category='', title='', cents=cents,
                source='synthetic-parent', line=1, field=stage, approximate=0)


class MprMysteryTests(unittest.TestCase):
    def setUp(self):
        self.p = api.parameters({'topic': ['maprimerenov']})

    def explain(self, scope='', year=2024, stage='EXEC', indices=None, **params):
        p = dict(self.p, **params)
        cell = topics.subset(scope, year, stage, p, indices or {})
        return cell, data_quality.mpr(cell, p, year, stage, scope)

    def assert_missing(self, cell, status='topic_unavailable'):
        self.assertIsNone(cell['value'])
        self.assertIsNone(cell.get('nominal_cents'))
        self.assertEqual(cell['status'], status)

    def test_2021_opened_cp_is_programme_only_and_does_not_promote_ae_or_relance(self):
        rows = [r for r in topics.registry()['facts']
                if r['year'] == 2021 and r['stage'] == 'OUVERT']
        self.assertEqual([(r['program'], r['measure'], r['cents']) for r in rows],
                         [('174', 'CP', 74000000000)])
        row = rows[0]
        self.assertEqual((row['mission'], row['action'], row['subaction']), ('TA', '', ''))
        self.assertEqual((row['source'], row['page']), ('2f15709320cdd6cb8d0a', 54))
        self.assertIn('l21-792-211-1_mono.html#toc33', row['corroboration_url'])
        for scope in ('TA', 'TA/174'):
            with self.subTest(scope=scope):
                cell, _ = self.explain(scope, 2021, 'OUVERT')
                self.assertEqual((cell['status'], cell['nominal_cents']), ('ok', 74000000000))
        for scope, measure in (('', 'CP'), ('PR/362', 'CP'), ('TA/174', 'AE')):
            with self.subTest(scope=scope, measure=measure):
                self.assert_missing(self.explain(scope, 2021, 'OUVERT', measure=measure)[0])

    def test_2021_opened_cp_cannot_be_allocated_to_or_subtracted_from_a_finer_action(self):
        for scope, excluded in [('TA/174/02', []), ('TA/174/02/01', []),
                                ('TA/174', ['TA/174/02']), ('TA/174', ['TA/174/02/01'])]:
            with self.subTest(scope=scope, excluded=excluded):
                cell, explanation = self.explain(scope, 2021, 'OUVERT', exclude=excluded)
                self.assert_missing(cell, 'detail_unavailable')
                self.assertTrue(any('programme' in x and 'sous-action' in x
                                    for x in explanation['details']))
                records = [parent('174', 100000000000, year=2021, stage='OUVERT')]
                p = dict(self.p, topic_mode='without', exclude=excluded)
                base = api.cell(records, scope, 2021, 'OUVERT', dict(p, topic=''), {})
                result = topics.calculate(records, base, scope, 2021, 'OUVERT', p, {})
                self.assert_missing(result, 'detail_unavailable')
                self.assertNotIn('topic_subtracted_nominal', result)

    def test_six_mixed_observations_are_preserved_as_withdrawn_history(self):
        registry = topics.registry()
        self.assertFalse(any(r['year'] == 2024 and r['program'] == '135'
                             for r in registry['facts']))
        histories = [r for r in registry['observation_history']
                     if r.get('status') == 'excluded_mixed_envelope'
                     and r['observation']['year'] == 2024
                     and r['observation']['program'] == '135']
        expected = {(stage, measure): cents for stage, cents in
                    [('LFI', 112400000000), ('OUVERT', 38000000000), ('EXEC', 38020000000)]
                    for measure in ('AE', 'CP')}
        self.assertEqual(len(histories), 6)
        self.assertEqual({(h['observation']['stage'], h['observation']['measure']):
                          h['observation']['cents'] for h in histories}, expected)
        for history in histories:
            self.assertIsNotNone(datetime.fromisoformat(history['withdrawn_at']).tzinfo)
            self.assertIn(('dca85104653c2c5a3d17', 126),
                          {(r['source'], r['page']) for r in history['references']})
        coverages = [c for c in registry['coverage'] if c['year'] == 2024
                     and c['stage'] in ('LFI', 'OUVERT', 'EXEC')]
        self.assertEqual(len(coverages), 6)
        for coverage in coverages:
            self.assertNotIn('VA/135', coverage['paths'])
            self.assertIn('TA/174', coverage['paths'])

    def test_national_2024_missing_amount_is_distinct_from_a_printed_zero(self):
        for measure in ('AE', 'CP'):
            for stage in ('LFI', 'OUVERT', 'EXEC'):
                for scope in ('', 'VA', 'VA/135'):
                    with self.subTest(measure=measure, stage=stage, scope=scope):
                        self.assert_missing(self.explain(scope, stage=stage, measure=measure)[0])
            zero, _ = self.explain('PR/362', stage='EXEC', measure=measure)
            self.assertEqual((zero['status'], zero['nominal_cents'], zero['value']), ('ok', 0, 0))
            self.assertTrue(zero['citations'])

    def test_ecologie_2024_values_are_unchanged(self):
        expected = {'PLF': (2697000000, 2065000000), 'LFI': (2296000000, 2024000000),
                    'OUVERT': (1596000000, 1142000000), 'EXEC': (1168000000, 692017721)}
        for scope in ('TA', 'TA/174'):
            for stage, amounts in expected.items():
                for measure, euros in zip(('AE', 'CP'), amounts):
                    with self.subTest(scope=scope, stage=stage, measure=measure):
                        cell, explanation = self.explain(scope, stage=stage, measure=measure)
                        self.assertEqual((cell['status'], cell['nominal_cents']), ('ok', euros * 100))
                        self.assertFalse(explanation['contextual_amounts'])
                        self.assertTrue(cell['citations'])

    def test_mixed_context_is_cited_but_never_becomes_an_additive_component(self):
        for stage, cents in [('LFI', 112400000000), ('OUVERT', 38000000000), ('EXEC', 38020000000)]:
            for measure in ('AE', 'CP'):
                for scope in ('', 'VA/135'):
                    with self.subTest(stage=stage, measure=measure, scope=scope):
                        cell, explanation = self.explain(scope, stage=stage, measure=measure)
                        self.assert_missing(cell)
                        context = explanation['contextual_amounts']
                        self.assertEqual(len(context), 1)
                        self.assertEqual(context[0]['cents'], cents)
                        self.assertEqual((context[0]['source'], context[0]['page']),
                                         ('793f09813e0448b0055c', 62))
                        self.assertTrue(context[0]['caution'])
                        self.assertNotIn('value', context[0])
                        self.assertFalse(any(r['source'] in ('296835325a7d511d6a5a', '793f09813e0448b0055c')
                                             and r['cents'] == cents for r in explanation['known_components']))
                        self.assertIn(('dca85104653c2c5a3d17', 126),
                                      {(r['source'], r['page']) for r in explanation['references']})

    def test_2024_plf_thermal_renovation_context_is_not_the_policy_total(self):
        for measure in ('AE', 'CP'):
            cell, explanation = self.explain(stage='PLF', measure=measure)
            self.assert_missing(cell)
            context = explanation['contextual_amounts']
            self.assertEqual(len(context), 1)
            self.assertEqual(context[0]['cents'], 103830000000)
            self.assertEqual((context[0]['source'], context[0]['page']), ('b7dd7c6577809efa3c84', 116))
            self.assertTrue(context[0]['caution'])

    def test_context_follows_whole_programme_exclusions(self):
        for stage in ('PLF', 'LFI', 'OUVERT', 'EXEC'):
            for scope, excluded in [('', ['VA']), ('', ['VA/135']), ('TA', []),
                                    ('PR', []), ('VA/135', ['VA/135'])]:
                with self.subTest(stage=stage, scope=scope, excluded=excluded):
                    _, explanation = self.explain(scope, stage=stage, exclude=excluded)
                    self.assertEqual(explanation['contextual_amounts'], [])

    def test_excluding_one_action_does_not_resolve_the_mixed_programme(self):
        for scope, excluded in [('VA/135/04', []), ('VA/135/04/01', []),
                                ('', ['VA/135/04']), ('', ['VA/135/04/01'])]:
            for stage in ('LFI', 'OUVERT', 'EXEC'):
                with self.subTest(scope=scope, excluded=excluded, stage=stage):
                    self.assert_missing(self.explain(scope, stage=stage, exclude=excluded)[0],
                                        'detail_unavailable')

    def test_complete_exclusion_of_va_restores_only_the_documented_remaining_exec(self):
        for exclude in (['VA'], ['VA/135'], ['VA/135', 'VA/135/04']):
            cell, explanation = self.explain(exclude=exclude)
            self.assertEqual((cell['status'], cell['nominal_cents']), ('ok', 69201772100))
            self.assertEqual(explanation['contextual_amounts'], [])
            cell, _ = self.explain(measure='AE', exclude=exclude)
            self.assertEqual((cell['status'], cell['nominal_cents']), ('ok', 116800000000))

    def test_without_mode_never_silently_subtracts_a_partial_national_2024_total(self):
        for stage in ('LFI', 'OUVERT', 'EXEC'):
            records = [parent('174', 500000000000, stage=stage),
                       parent('362', 500000000000, mission='PR', stage=stage),
                       parent('135', 500000000000, mission='VA', stage=stage)]
            for constant in (False, True):
                p = dict(self.p, topic_mode='without', constant=constant)
                base = api.cell(records, '', 2024, stage, dict(p, topic=''), {2024: '100', 2025: '110'})
                self.assertIsNotNone(base['value'])
                result = topics.calculate(records, base, '', 2024, stage, p, {2024: '100', 2025: '110'})
                with self.subTest(stage=stage, constant=constant):
                    self.assert_missing(result)
                    self.assertNotIn('topic_subtracted_nominal', result)

    def test_inflation_neither_fills_missing_cells_nor_converts_context_to_facts(self):
        for stage in ('LFI', 'OUVERT', 'EXEC'):
            nominal, note = self.explain(stage=stage)
            for indices in ({2024: '100', 2025: '110'}, {}):
                constant, constant_note = self.explain(stage=stage, constant=True, indices=indices)
                self.assert_missing(constant)
                self.assertEqual(constant_note['contextual_amounts'], note['contextual_amounts'])
                self.assertEqual(constant['nominal_cents'], nominal['nominal_cents'])
        converted, _ = self.explain('TA/174', 2021, 'OUVERT', constant=True,
                                    indices={2021: '100', 2025: '110'})
        self.assertEqual(converted['nominal_cents'], 74000000000)
        self.assertEqual(converted['value'], 814000000)
        unavailable, _ = self.explain('TA/174', 2021, 'OUVERT', constant=True)
        self.assertEqual(unavailable['status'], 'inflation_missing')
        self.assertIsNone(unavailable['value'])
        self.assertEqual(unavailable['nominal_cents'], 74000000000)

    def test_ecologie_subtraction_and_unrelated_programmes_keep_their_amounts(self):
        records = [parent('174', 100000000000), parent('203', 200000000000)]
        p = dict(self.p, topic_mode='without', constant=True)
        indices = {2024: '100', 2025: '110'}
        base = api.cell(records, 'TA', 2024, 'EXEC', dict(p, topic=''), indices)
        result = topics.calculate(records, base, 'TA', 2024, 'EXEC', p, indices)
        self.assertEqual(result['nominal_cents'], 230798227900)
        self.assertEqual(result['value'], 2538780506.9)
        self.assertEqual(result['topic_subtracted_nominal'], 692017721)
        other_base = api.cell(records, 'TA/203', 2024, 'EXEC', dict(p, topic=''), indices)
        self.assertEqual(topics.calculate(records, other_base, 'TA/203', 2024, 'EXEC', p, indices), other_base)

    def test_csv_exports_missing_national_amount_as_empty_not_zero_or_context(self):
        for scope, amount, status in [('', '', 'topic_unavailable'),
                                     ('TA', '692017721,0', 'ok')]:
            p = dict(self.p, scope=scope)
            annual = {stage: topics.subset(scope, 2024, stage, p, {}) for stage in STAGES}
            annual['year'] = 2024
            data = dict(parameters=p, totals=[annual], rows=[], scope_label=scope or 'National',
                        exclusions=[], topic=topics.description(p))
            exported = list(csv.DictReader(io.StringIO(api.export_csv(data).decode('utf-8-sig')), delimiter=';'))
            row = next(r for r in exported if r['Étape'] == STAGES['EXEC'])
            self.assertEqual(row['Montant EUR'], amount)
            self.assertEqual(row['Statut'], status)
            self.assertNotIn('380200000', row['Montant EUR'])

    def test_2022_p362_explains_818_plus_related_costs_for_available_and_missing_cells(self):
        for scope in ('PR/362', ''):
            for stage in ('OUVERT', 'EXEC'):
                cell, explanation = self.explain(scope, 2022, stage)
                with self.subTest(scope=scope, stage=stage):
                    if stage == 'EXEC' and scope == 'PR/362':
                        self.assertEqual(cell['nominal_cents'], 81800000000)
                    if stage == 'OUVERT':
                        self.assertIsNone(cell['value'])
                    text = ' '.join(explanation['details'])
                    for token in ('818', '47,2', '5 M€', '870', '1 092'):
                        self.assertIn(token, text)
                    self.assertTrue({('72bbb96691ae9ed15695', 39), ('72bbb96691ae9ed15695', 40)} <=
                                    {(r['source'], r['page']) for r in explanation['references']})
                    self.assertEqual(explanation['contextual_amounts'], [])
        for scope, excluded in [('TA', []), ('', ['PR']), ('', ['PR/362'])]:
            _, explanation = self.explain(scope, 2022, 'EXEC', exclude=excluded)
            self.assertNotIn(('72bbb96691ae9ed15695', 39),
                             {(r['source'], r['page']) for r in explanation['references']})


    def test_agency_reserve_reference_resolves_to_downloadable_source(self):
        import sqlite3
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT)')
            for measure in ('AE', 'CP'):
                for stage in ('PLF', 'LFI', 'OUVERT', 'EXEC'):
                    _, explanation = self.explain('', 2026, stage, measure=measure)
                    ref = next(r for r in explanation['references'] if 'programmation 2026' in r.get('label', ''))
                    source = api.source(db, ref['source'])
                    self.assertEqual(source['sha256'], '49e40a23762335975cf21b334f5b2dd71193322ba843dfd56e5cb0808c6ae648')
                    self.assertEqual(ref['page'], 9)
                    self.assertEqual(source['format'], 'pdf')
                    self.assertFalse(source['numeric_import'])


if __name__ == '__main__':
    unittest.main()
