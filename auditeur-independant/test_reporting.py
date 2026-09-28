import copy,csv,io,json,tempfile,unittest
from pathlib import Path
from audit import arithmetic
from reporting import number,summarize,write_outputs
from oracle import Reference

class Variations(unittest.TestCase):
    def errors(self,current=None,reference=None,rate=-100):
        current=current or dict(value=0,nominal=0,status='excluded')
        reference=reference or dict(value=150726156,nominal=150726156,nominal_cents=15072615600,status='ok')
        data=dict(parameters=dict(scope='YB',start=2017,denominator='LFI'),rows=[],totals=[dict(year=2017,PLF=reference,evolution={}),dict(year=2018,PLF=current,evolution=dict(PLF=dict(nominal_yoy=dict(reference_year=2017,value=rate))))])
        return [e for e in arithmetic(data,{})['errors'] if e['cell']=='YB 2018 PLF nominal_yoy']
    def test_excluded_zero_yields_minus_hundred_percent(self):self.assertEqual(self.errors(),[])
    def test_real_rate_error_still_detected(self):self.assertEqual(len(self.errors(rate=-99)),1)
    def test_missing_value_not_converted_to_zero(self):self.assertEqual(len(self.errors(current=dict(value=None,nominal=None,status='missing'))),1)
    def test_excluded_reference_zero_has_no_rate(self):self.assertEqual(self.errors(reference=dict(value=0,nominal=0,status='excluded'),rate=None),[])
    def test_explicit_cents_take_precedence(self):self.assertEqual(len(self.errors(current=dict(value=0,nominal=0,nominal_cents=100000000,status='excluded'))),1)

class Reporting(unittest.TestCase):
    def source_issue(self,kind='topic',measure='CP'):
        return dict(kind=kind,cell=f'BG | {measure} | PR/362 | 2024 | LFI sources',expected='références présentes',actual=[],params=dict(budget='BG',measure=measure,scope='PR',topic='maprimerenov',topic_mode='only'))
    def test_repeated_signal_grouped_but_credits_distinct(self):
        s=summarize([self.source_issue(),self.source_issue('export'),self.source_issue(measure='AE')])
        self.assertEqual((s['finding_count'],s['raw_signal_count'],s['family_count']),(2,3,1));self.assertEqual(s['findings'][0]['occurrences'],2)
    def test_percent_is_not_euros(self):
        s=summarize([dict(kind='exclusion',cell='YB 2018 PLF nominal_yoy',expected=None,actual=-100.0,params=dict(exclude=['YB/783']))])['findings'][0]
        self.assertEqual((s['unit'],s['actual'],s['expected']),('%','-100 %','Non calculable'))
    def test_money_converted_from_cents(self):
        s=summarize([dict(kind='ordinary',cell='montant en centimes',expected=10000,actual=10001,params={})])['findings'][0]
        self.assertEqual((s['expected'],s['actual']),('100 €','100,01 €'))
    def test_fractional_negative_sign_preserved(self):self.assertEqual(number(-0.5),'-0,5')
    def test_hidden_absence_count_and_raw_evidence_preserved(self):
        issues=[self.source_issue()]
        r=dict(summary=summarize(issues),issues=issues,counts=dict(amounts=640058,calculations=5816160,missing=1252622),verdict='ANOMALIES DÉTECTÉES',passed=False,cases=3,at='2026-09-28',identity=dict(data_version='test'))
        with tempfile.TemporaryDirectory() as d:
            write_outputs(d,r,'http://localhost:8552')
            page=(Path(d)/'rapport.html').read_text('utf-8');top,detail=page.split('<details id="technical">')
            self.assertNotIn('1 252 622',top);self.assertIn('1 252 622',detail);self.assertIn('Il ne compte pas des erreurs.',detail)
            self.assertIn('POINTS À VÉRIFIER',top);self.assertIn('un écart de montant reste signalé',top)
            friendly=list(csv.DictReader(io.StringIO((Path(d)/'anomalies.csv').read_text('utf-8-sig')),delimiter=';'))
            raw=list(csv.DictReader(io.StringIO((Path(d)/'anomalies-techniques.csv').read_text('utf-8-sig')),delimiter=';'))
            self.assertEqual(friendly[0]['Observé'],'Aucune référence fournie');self.assertEqual(raw[0]['Observé'],'[]')
    def test_incomplete_never_becomes_pass(self):
        r=dict(summary=summarize([]),issues=[],counts={},verdict='INCOMPLET',passed=False,cases=0,at='2026-09-28',identity={})
        with tempfile.TemporaryDirectory() as d:
            write_outputs(d,r,'http://localhost');self.assertIn('pas une validation complète',(Path(d)/'rapport.html').read_text('utf-8'))

class TopicOracle(unittest.TestCase):
    def test_coverage_without_fact_cannot_prove_zero(self):
        r=Reference.__new__(Reference);r.mpr=dict(carriers=[dict(path='PR/362')],facts=[],coverage=[dict(year=2024,stage='LFI',measure='CP',paths=['PR/362'])])
        p=dict(budget='BG',measure='CP',exclude=[])
        self.assertIsNone(r.topic_amount(p,2024,'LFI','PR/362'))
        r.mpr['facts']=[dict(year=2024,stage='LFI',measure='CP',mission='PR',program='362',action='',subaction='',cents=0)]
        self.assertEqual(r.topic_amount(p,2024,'LFI','PR/362'),0)

if __name__=='__main__':unittest.main()
