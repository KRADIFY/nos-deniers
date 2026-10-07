"""MPR perimeter evidence is distinct from additive monetary observations."""
import copy
import csv
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest import mock

from budget_service import api, exports, topics
from budget_service.model import STAGES, constant_cents


RAP_2020 = 'df8d92ccd79f7b889547'
# Independently checked against RAP 2020 pp. 414–415 and the canonical CSV
# action 02 rows, including cents and the cheque-energie commitment withdrawals.
EXPECTED_2020 = {
    ('LFI', 'AE'): (39000000000, [127190000000], 88190000000),
    ('LFI', 'CP'): (39000000000, [121212704300], 82212704300),
    ('EXEC', 'AE'): (57500000000, [2226764089, 126833576257], 71560340346),
    ('EXEC', 'CP'): (45500000000, [1792166014, 112448771472], 68740937486),
}


def parent(cents, year=2025, stage='EXEC', measure='CP', program='174', action=''):
    return dict(year=year, stage=stage, measure=measure, budget='BG', mission='TA',
                mission_label='Écologie', program=program, program_label=program,
                action=action, action_label=action, subaction='', subaction_label='',
                category='', title='', cents=cents, source='parent-csv', line=1,
                field=stage + ' ' + measure, approximate=0)


def action_2020(stage, measure):
    amounts = EXPECTED_2020[stage, measure][1]
    rows = [parent(amount, 2020, stage, measure, action='02') for amount in amounts]
    for index, row in enumerate(rows):
        row.update(category='31' if len(rows) == 2 and index == 0 else '61',
                   title='3' if len(rows) == 2 and index == 0 else '6', line=1288 + index)
    return rows


class MprPerimeterTests(unittest.TestCase):
    def setUp(self):
        self.p = api.parameters({'topic': ['maprimerenov'], 'start': ['2020'], 'end': ['2025']})

    def evidence_citations(self, stage='EXEC', measure='CP'):
        evidence = topics.perimeter_evidence('TA', [], 2025, stage, measure)
        self.assertTrue(evidence, 'The 2025 perimeter statement must be documented')
        return {(r['source'], r['page']) for e in evidence for r in e['references']}

    def provenance(self, rows, p, year, stage, scope, indices=None):
        # Exercise real api.provenance, topics.calculate and monetary proof
        # construction; mock only the database boundary and source catalogue.
        with mock.patch.object(api, 'selected_records', return_value=rows), \
             mock.patch.object(api, 'metadata', return_value={'indices': indices or {}}), \
             mock.patch.object(api, 'source', side_effect=lambda db, sid: {
                 'id': sid, 'title': sid, 'url': 'https://example.invalid/' + sid,
                 'sha256': 'a' * 64, 'path': sid + '.pdf'}):
            return api.provenance(object(), p, year, stage, scope)

    def test_2020_four_observations_are_explicit_action_amounts(self):
        facts = [r for r in topics.registry()['facts'] if r['year'] == 2020 and r['stage'] in ('LFI','EXEC')]
        self.assertEqual(len(facts), 4)
        self.assertEqual({(r['stage'], r['measure']): r['cents'] for r in facts},
                         {key: expected[0] for key, expected in EXPECTED_2020.items()})
        for row in facts:
            self.assertEqual((row['mission'], row['program'], row['action'], row['subaction']),
                             ('TA', '174', '02', ''))
            self.assertEqual(row['source'], RAP_2020)
            self.assertEqual(row['page'], 415)
            self.assertFalse(row['approximate'])
            self.assertIn('€', row['precision'])
            for scope in ('TA', 'TA/174', 'TA/174/02'):
                with self.subTest(stage=row['stage'], measure=row['measure'], scope=scope):
                    cell = topics.subset(scope, 2020, row['stage'], dict(self.p, measure=row['measure']), {})
                    self.assertEqual((cell['status'], cell['nominal_cents'], cell['count']),
                                     ('ok', row['cents'], 1))
                    self.assertIn({'source': RAP_2020, 'page': 415}, cell['citations'])
                    self.assertIn({'source': RAP_2020, 'page': 414}, cell['citations'])

    def test_2020_transferred_funding_is_not_a_second_expenditure(self):
        for scope in ('VA', 'VA/135', 'PR', 'PR/362'):
            for stage in ('LFI', 'EXEC'):
                for measure in ('AE', 'CP'):
                    with self.subTest(scope=scope, stage=stage, measure=measure):
                        cell = topics.subset(scope, 2020, stage, dict(self.p, measure=measure), {})
                        self.assertEqual(cell['value'],0)
                        self.assertTrue(cell['evidence'])
                        self.assertEqual(cell['count'],0)
        for stage in ('FDC', 'REPORT_ENTRANT'):
            self.assertIsNone(topics.subset('TA', 2020, stage, self.p, {})['value'])
        self.assertEqual(topics.subset('TA/174/02/01', 2020, 'EXEC', self.p, {})['status'],
                         'detail_unavailable')

    def test_coverage_is_required_even_when_a_monetary_observation_exists(self):
        registry = copy.deepcopy(topics.registry())
        self.assertTrue(registry.get('coverage'))
        registry['coverage'] = [r for r in registry['coverage'] if r['year'] != 2020]
        with mock.patch.object(topics, 'registry', return_value=registry):
            cell = topics.subset('TA', 2020, 'EXEC', self.p, {})
        self.assertIsNone(cell['value'])
        self.assertEqual(cell['status'], 'topic_unavailable')

    def test_2025_transfer_evidence_and_published_plf_cp_are_distinct(self):
        facts = [r for r in topics.registry()['facts'] if r['year'] == 2025]
        self.assertEqual(len(facts), 3)
        self.assertEqual({(r['mission'], r['program']): r['cents'] for r in facts},
                         {('TA', '174'): 0, ('PR', '362'): 0, ('VA', '135'): 137800000000})
        self.assertEqual({(r['stage'], r['measure']) for r in facts}, {('PLF', 'CP')})
        self.assertTrue(all(r['source'] == '0bda7f84a57258b9143c' and r['page'] == 18 for r in facts))

        # The transfer evidence remains a non-monetary perimeter statement for
        # AE, LFI and execution. It must not manufacture a national zero.
        for stage, measure in (('PLF', 'AE'), ('LFI', 'AE'), ('LFI', 'CP'),
                               ('EXEC', 'AE'), ('EXEC', 'CP')):
            expected = self.evidence_citations(stage, measure)
            for scope in ('TA', 'TA/174', 'TA/174/02'):
                with self.subTest(stage=stage, measure=measure, scope=scope):
                    cell = topics.subset(scope, 2025, stage, dict(self.p, measure=measure), {})
                    self.assertEqual((cell['value'], cell['nominal_cents'], cell['count'], cell['status']),
                                     (0, 0, 0, 'ok'))
                    self.assertEqual({(c['source'], c['page']) for c in cell['citations']}, expected)

        # CP at PLF is a published table: the programme-level zero is explicit.
        for scope, count in (('TA', 1), ('TA/174', 1), ('TA/174/02', 0)):
            cell = topics.subset(scope, 2025, 'PLF', dict(self.p, measure='CP'), {})
            self.assertEqual((cell['value'], cell['nominal_cents'], cell['count'], cell['status']),
                             (0, 0, count, 'ok'))
            if count:
                self.assertIn({'source': '0bda7f84a57258b9143c', 'page': 18}, cell['citations'])

    def test_2025_perimeter_evidence_never_extrapolates_to_other_scopes_years_or_stages(self):
        expected_plf_cp = {
            '': 1378000000, 'VA': 1378000000, 'VA/135': 1378000000,
            'PR': 0, 'PR/362': 0,
        }
        for scope, amount in expected_plf_cp.items():
            with self.subTest(scope=scope):
                cell = topics.subset(scope, 2025, 'PLF', dict(self.p, measure='CP'), {})
                self.assertEqual((cell['value'], cell['status']), (amount, 'ok'))
                self.assertIn({'source': '0bda7f84a57258b9143c', 'page': 18}, cell['citations'])

        for scope in ('', 'VA', 'VA/135', 'PR', 'PR/362'):
            for stage, measure in (('PLF', 'AE'), ('LFI', 'AE'), ('LFI', 'CP'),
                                   ('EXEC', 'AE'), ('EXEC', 'CP')):
                with self.subTest(scope=scope, stage=stage, measure=measure):
                    self.assertIsNone(topics.subset(scope, 2025, stage,
                                                   dict(self.p, measure=measure), {})['value'])
        for year, stages in ((2025, ('OUVERT', 'FDC', 'REPORT_ENTRANT')),
                             (2026, ('PLF', 'LFI', 'EXEC', 'OUVERT'))):
            for stage in stages:
                self.assertIsNone(topics.subset('TA', year, stage, self.p, {})['value'])

    def test_2025_without_preserves_base_amount_and_zero_subtraction(self):
        for stage, measure in (('PLF', 'AE'), ('PLF', 'CP'), ('LFI', 'AE'), ('LFI', 'CP'),
                               ('EXEC', 'AE'), ('EXEC', 'CP')):
            with self.subTest(stage=stage, measure=measure):
                rows = [parent(12000000123, stage=stage, measure=measure),
                        parent(5000000045, stage=stage, measure=measure, program='203')]
                p = dict(self.p, topic_mode='without', measure=measure)
                base = api.cell(rows, 'TA', 2025, stage, p, {})
                base['citations'] = [{'source': 'parent-csv', 'page': 42}]
                before = copy.deepcopy(base)
                cell = topics.calculate(rows, base, 'TA', 2025, stage, p, {})
                for key in ('value', 'nominal', 'nominal_cents', 'status'):
                    self.assertEqual(cell[key], base[key], key)
                self.assertEqual(cell['count'], base['count'] + (1 if (stage, measure) == ('PLF', 'CP') else 0))
                self.assertEqual(cell['topic_subtracted_nominal'], 0)
                expected = self.evidence_citations(stage, measure) | {('parent-csv', 42)}
                if (stage, measure) == ('PLF', 'CP'):
                    expected.add(('0bda7f84a57258b9143c', 18))
                self.assertEqual({(c['source'], c['page']) for c in cell['citations']}, expected)
                self.assertEqual(base, before)

    def test_missing_base_cannot_be_replaced_by_documented_zero_subtraction(self):
        p = dict(self.p, topic_mode='without')
        base = api.cell([], 'TA', 2025, 'EXEC', p, {})
        cell = topics.calculate([], base, 'TA', 2025, 'EXEC', p, {})
        self.assertIsNone(cell['value'])
        self.assertEqual(cell['status'], 'missing')

    def test_2020_subtraction_preserves_canonical_cents_and_withdrawals(self):
        for (stage, measure), (amount, _, remainder) in EXPECTED_2020.items():
            for scope in ('TA', 'TA/174', 'TA/174/02'):
                with self.subTest(stage=stage, measure=measure, scope=scope):
                    rows = action_2020(stage, measure)
                    p = dict(self.p, topic_mode='without', measure=measure)
                    base = api.cell(rows, scope, 2020, stage, p, {})
                    cell = topics.calculate(rows, base, scope, 2020, stage, p, {})
                    self.assertEqual(cell['status'], 'ok')
                    self.assertEqual(cell['nominal_cents'], remainder)
                    self.assertEqual(cell['nominal_cents'] + amount, base['nominal_cents'])
                    self.assertEqual(cell['count'], len(rows) + 1)

    def test_2020_missing_or_insufficient_parent_blocks_subtraction(self):
        p = dict(self.p, topic_mode='without')
        for rows in ([parent(900000000000, 2020, program='203')],
                     [parent(45499999999, 2020, action='02'), parent(900000000000, 2020, program='203')]):
            base = api.cell(rows, 'TA', 2020, 'EXEC', p, {})
            cell = topics.calculate(rows, base, 'TA', 2020, 'EXEC', p, {})
            self.assertIsNone(cell['value'])
            self.assertEqual(cell['status'], 'detail_unavailable')

    def test_2020_complete_action_or_program_exclusion_is_not_subtracted_twice(self):
        rows = action_2020('EXEC', 'CP') + [parent(12345, 2020, action='03'),
                                           parent(67890, 2020, program='203')]
        for excluded, expected in ((['TA/174/02'], 80235),
                                   (['TA/174', 'TA/174/02'], 67890)):
            p = dict(self.p, topic_mode='without', exclude=excluded)
            base = api.cell(rows, 'TA', 2020, 'EXEC', p, {})
            cell = topics.calculate(rows, base, 'TA', 2020, 'EXEC', p, {})
            self.assertEqual(cell, base)
            self.assertEqual(cell['nominal_cents'], expected)
        p = dict(self.p, topic_mode='without', exclude=['TA/174/03'])
        base = api.cell(rows, 'TA', 2020, 'EXEC', p, {})
        cell = topics.calculate(rows, base, 'TA', 2020, 'EXEC', p, {})
        self.assertEqual(cell['nominal_cents'], 68740937486 + 67890)

    def test_2020_inflation_is_applied_once_after_nominal_subtraction(self):
        rows = action_2020('EXEC', 'AE')
        p = dict(self.p, topic_mode='without', measure='AE', constant=True, base=2025)
        indices = {2020: '100', 2025: '120'}
        base = api.cell(rows, 'TA/174/02', 2020, 'EXEC', p, indices)
        with mock.patch.object(topics, 'constant_cents', wraps=constant_cents) as convert:
            cell = topics.calculate(rows, base, 'TA/174/02', 2020, 'EXEC', p, indices)
        convert.assert_called_once_with(71560340346, 2020, 2025, indices)
        self.assertEqual(cell['nominal_cents'], 71560340346)
        self.assertEqual(round(cell['value'] * 100), 85872408415)

    def test_missing_inflation_keeps_the_2020_nominal_remainder(self):
        rows = action_2020('EXEC', 'CP')
        p = dict(self.p, topic_mode='without', constant=True)
        base = api.cell(rows, 'TA', 2020, 'EXEC', p, {})
        cell = topics.calculate(rows, base, 'TA', 2020, 'EXEC', p, {})
        self.assertIsNone(cell['value'])
        self.assertEqual(cell['status'], 'inflation_missing')
        self.assertEqual(cell['nominal_cents'], 68740937486)

    def test_2020_provenance_proves_the_signed_subtraction_and_both_pages(self):
        rows = action_2020('EXEC', 'CP')
        p = dict(self.p, topic_mode='without', scope='TA/174/02')
        proof = self.provenance(rows, p, 2020, 'EXEC', p['scope'])
        self.assertEqual(proof['calculation']['base_nominal'], 1142409374.86)
        self.assertEqual(proof['calculation']['subtracted_nominal'], 455000000)
        self.assertEqual(proof['calculation']['result_nominal'], 687409374.86)
        self.assertEqual(sum(r['cents'] for r in proof['rows']), 68740937486)
        subtraction = [r for r in proof['rows'] if r.get('operation') == 'subtract']
        self.assertEqual(len(subtraction), 1)
        self.assertEqual(subtraction[0]['cents'], -45500000000)
        self.assertEqual({(c['source'], c['page']) for c in proof['citations']},
                         {(RAP_2020, 414), (RAP_2020, 415)})

    def test_2025_provenance_has_evidence_without_fabricating_monetary_rows(self):
        rows = [parent(123456789)]
        for mode in ('only', 'without'):
            p = dict(self.p, topic_mode=mode, scope='TA')
            proof = self.provenance(rows, p, 2025, 'EXEC', 'TA')
            self.assertTrue(proof['evidence'])
            expected = self.evidence_citations()
            self.assertEqual({(c['source'], c['page']) for c in proof['citations']}, expected)
            self.assertTrue({source for source, _ in expected}.issubset({s['id'] for s in proof['sources']}))
            self.assertFalse([r for r in proof['rows'] if r.get('operation') == 'subtract'])
            self.assertEqual(proof['count'], 0 if mode == 'only' else 1)
            self.assertEqual(sum(r['cents'] for r in proof['rows']), 0 if mode == 'only' else 123456789)
            self.assertEqual(proof['calculation']['result_nominal'], 0 if mode == 'only' else 1234567.89)
            if mode == 'without':
                self.assertEqual(proof['calculation']['subtracted_nominal'], 0)

    def test_2025_csv_and_xlsx_export_the_zero_with_its_perimeter_citations(self):
        p = dict(self.p, start=2025, end=2025, scope='TA')
        annual = {stage: topics.subset('TA', 2025, stage, p, {}) for stage in STAGES}
        annual.update(year=2025, comparisons={})
        data = dict(parameters=p, totals=[annual], rows=[], scope_label='MPR · Écologie',
                    exclusions=[], topic=topics.description(p), data_version='fixture',
                    selection_id='fixture-selection', inflation={}, notes=[])
        records = list(csv.DictReader(io.StringIO(api.export_csv(data).decode('utf-8-sig')), delimiter=';'))
        for stage in ('PLF', 'LFI', 'EXEC'):
            row = next(r for r in records if r['Étape'] == STAGES[stage])
            self.assertEqual(float(row['Montant EUR'].replace(',', '.')), 0)
            self.assertEqual(row['Statut'], 'ok')
            self.assertTrue(row['Motif de disponibilité'])
            for source, page in self.evidence_citations(stage):
                self.assertIn(source, row['Identifiants sources'])
                self.assertIn('#page=' + str(page), row['Sources officielles'])
        self.assertEqual(next(r for r in records if r['Étape'] == STAGES['OUVERT'])['Montant EUR'], '')
        sources = [{'id': sid, 'title': sid} for sid in annual['EXEC']['sources']]
        with zipfile.ZipFile(io.BytesIO(exports.xlsx(data, sources))) as archive:
            sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            exported = [{c.attrib['r'].rstrip('0123456789'): ''.join(c.itertext())
                         for c in row.findall('s:c', ns)} for row in sheet.findall('.//s:row', ns)]
            executed = next(r for r in exported if r.get('G') == STAGES['EXEC'])
            self.assertEqual(float(executed['H']), 0)
            for source, page in self.evidence_citations():
                self.assertIn(source + ' · PDF p. ' + str(page), executed['O'])
            source_sheet = archive.read('xl/worksheets/sheet4.xml').decode('utf-8')
            for source, _ in self.evidence_citations():
                self.assertIn(source, source_sheet)


if __name__ == '__main__':
    unittest.main()
