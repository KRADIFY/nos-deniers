"""Deliberately corrupt responses in memory. No site modification."""
import collections,copy,unittest
from decimal import Decimal
from oracle import Reference,STAGES,compare_cells
from audit import params,arithmetic,export_check

class SmallReference:
    sources={'source1':{}}
    children=collections.defaultdict(set)
    children[('BG','AE','')]={'AA'}
    indices={'2024':'100','2025':'102'}
    def children_in_period(self,p):return self.children[(p['budget'],p['measure'],p['scope'])]
    def expected(self,p,year,stage,path):return {('2024','PLF'):10000,('2025','PLF'):12000}.get((str(year),stage))
    def converted(self,amount,year,p):return None if amount is None else Decimal(amount)/100

def sample():
    p=params('BG','AE',start=2024,end=2025)
    series=[]
    for year,amount in ((2024,10000),(2025,12000)):
        r={'year':year}
        for s in STAGES:r[s]=dict(nominal_cents=None,nominal=None,value=None,status='missing',reason='Non renseigné',sources=[])
        r['PLF']=dict(nominal_cents=amount,nominal=amount/100,value=amount/100,status='ok',sources=['source1'])
        series.append(r)
    return p,dict(parameters=copy.deepcopy(p),years=[2024,2025],stages=STAGES,totals=copy.deepcopy(series),rows=[dict(id='AA',series=copy.deepcopy(series))])

class Detection(unittest.TestCase):
    def run_case(self,mutate):
        p,data=sample();mutate(data);self.assertTrue(compare_cells(SmallReference(),p,data)['errors'])
    def test_clean(self):
        p,d=sample();self.assertEqual(compare_cells(SmallReference(),p,d)['errors'],[])
    def test_one_cent(self):self.run_case(lambda d:d['totals'][0]['PLF'].update(nominal_cents=10001))
    def test_euros_wrong(self):self.run_case(lambda d:d['totals'][0]['PLF'].update(value=101))
    def test_wrong_year(self):self.run_case(lambda d:d['rows'][0]['series'].reverse())
    def test_wrong_programme(self):self.run_case(lambda d:d['rows'][0].update(id='BB'))
    def test_wrong_ae_cp(self):self.run_case(lambda d:d['parameters'].update(measure='CP'))
    def test_wrong_stage(self):
        def mutate(d):d['totals'][0]['PLF'],d['totals'][0]['LFI']=d['totals'][0]['LFI'],d['totals'][0]['PLF']
        self.run_case(mutate)
    def test_missing_row(self):self.run_case(lambda d:d.update(rows=[]))
    def test_duplicate_row(self):self.run_case(lambda d:d['rows'].append(copy.deepcopy(d['rows'][0])))
    def test_missing_as_zero(self):self.run_case(lambda d:d['totals'][0]['EXEC'].update(nominal_cents=0,nominal=0,value=0))
    def test_unknown_source(self):self.run_case(lambda d:d['totals'][0]['PLF'].update(sources=['fake']))
    def test_lost_source(self):self.run_case(lambda d:d['totals'][0]['PLF'].update(sources=[]))
    def test_rate_wrong(self):
        p,d=sample();d['totals'][1]['comparisons']={'CONSUMPTION':{'operands':['EXEC','LFI'],'value':100}}
        self.assertTrue(arithmetic(d,SmallReference.indices)['errors'])
    def test_empty_export(self):
        _,d=sample();self.assertTrue(export_check(d,b'Code;Ann\xc3\xa9e;\xc3\x89tape;Montant EUR\n')['errors'])
    def test_exclusion_union(self):
        r=Reference.__new__(Reference);r.amounts={('BG','AE',2024,'EXEC','AA/105'):1000,('BG','AE',2024,'EXEC','AA/105/01'):400,('BG','AE',2024,'EXEC','AA/105/02'):599}
        r.children=collections.defaultdict(set,{('BG','AE','AA/105'):{'AA/105/01','AA/105/02'}});r.blocked=set();r.leaves=set()
        key=('BG','AE',2024,'EXEC','AA/105')
        self.assertEqual(r.removed(key,['AA/105/01','AA/105/01']),(400,False))
        self.assertEqual(r.removed(key,['AA/105/01','AA/105/02']),(1000,True))
        self.assertEqual(r.removed(key,['AA/105','AA/105/01']),(1000,True))
    def test_blocked_branch(self):
        r=Reference.__new__(Reference);k=('BG','AE',2024,'EXEC','AA/105');r.amounts={k:100};r.blocked={k}
        self.assertEqual(r.removed(k,['AA/105/01']),(None,False))
class PeriodNavigation(unittest.TestCase):
    def setUp(self):
        self.ref=Reference.__new__(Reference)
        self.ref.children_by_year={('BG','AE',2023,'TA'):{'TA/174'},('BG','AE',2025,'TA'):{'TA/174','TA/235'},('BG','CP',2023,'TA'):{'TA/999'}}
    def test_future_programme_is_not_expected(self):
        self.assertEqual(self.ref.children_in_period(params('BG','AE','TA',start=2023,end=2024)),{'TA/174'})
    def test_wider_period_keeps_future_programme(self):
        self.assertEqual(self.ref.children_in_period(params('BG','AE','TA',start=2023,end=2025)),{'TA/174','TA/235'})
    def test_missing_applicable_row_remains_an_error(self):
        p,d=sample();d['rows']=[]
        self.assertTrue(any(e['cell']=='lignes / bonnes cases' for e in compare_cells(SmallReference(),p,d)['errors']))
if __name__=='__main__':unittest.main(verbosity=2)
