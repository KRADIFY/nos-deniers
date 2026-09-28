import collections,csv,json,tempfile,unittest
from pathlib import Path
from zeros import meaning,Reader,classify_cell
from oracle import digest

class ZeroTests(unittest.TestCase):
    def test_numeric_and_blank_are_distinct(self):
        for raw in (0,0.0,'0','0,00','0.00',' 0 '):self.assertEqual(meaning(raw)[0],'source_zero')
        for raw in ('',None,'  '):self.assertEqual(meaning(raw)[0],'source_blank')
        for raw in ('-','—','–'):self.assertEqual(meaning(raw)[0],'source_dash')
        self.assertEqual(meaning('sans objet')[0],'source_not_applicable')
        self.assertEqual(meaning('0,0001')[0],'nonzero_source')
    def test_column_and_hash_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.csv';p.write_text('Programme;CP;AE;Vide;Report_N-1;Report_N+1\n174;0;12;;-;0\n','utf-8')
            source=dict(id='x',path='source.csv',format='csv',sha256=digest(p))
            reader=Reader(tmp)
            check=lambda name:reader.inspect(dict(field=name,line=2),source)['status']
            self.assertEqual(check('CP'),'source_zero');self.assertEqual(check('AE'),'nonzero_source')
            self.assertEqual(check('Vide'),'source_blank');self.assertEqual(check('Report_N-1'),'source_dash')
            self.assertEqual(check('Report_N+1'),'source_zero');self.assertEqual(check('CP + Vide'),'source_blank')
            self.assertEqual(check('CP + Report_N+1'),'calculated_zero')
            source['sha256']='bad';self.assertEqual(Reader(tmp).inspect(dict(field='CP',line=2),source)['status'],'undetermined')
    def test_wrong_coordinate_and_duplicate_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'s.csv';p.write_text('CP;CP\n0;0\n')
            s=dict(id='x',path='s.csv',format='csv',sha256=digest(p))
            self.assertEqual(Reader(tmp).inspect(dict(field='CP',line=2),s)['status'],'undetermined')
    def test_absence_does_not_claim_a_blank_source(self):
        r=classify_cell(None,{},2024,'LFI','TA',dict(value=None,status='missing',reason='Pas de ligne importée'))
        self.assertEqual(r['status'],'missing');self.assertNotEqual(r['status'],'source_blank')
    def test_computational_zero_is_not_source_zero(self):
        r=classify_cell(None,{},2024,'LFI','TA',dict(value=0,nominal=0,status='excluded'))
        self.assertEqual(r['status'],'excluded')
        r=classify_cell(None,{'topic':'maprimerenov'},2024,'LFI','PR/362',dict(value=0,nominal=0,status='ok',sources=[]))
        self.assertEqual(r['status'],'unproven_zero')
if __name__=='__main__':unittest.main()
