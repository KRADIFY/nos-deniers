import copy,tempfile,unittest
from pathlib import Path
from coverage import compare_rows,numeric_cells,column_ends

class DocumentaryMutationTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(source='official',sha256='a'*64,year=2020,budget='BG',program='174',measure='CP',opening_gap_cents=0,closing_gap_cents=0,cells={
          'LFI':dict(cents=10000,page=12,raw='100,00',bbox=[1,2,3,4]),
          'EXEC':dict(cents=8000,page=12,raw='80,00',bbox=[5,2,7,4])})
        self.facts=[dict(year=2020,budget='BG',program='174',measure='CP',stage=s,cents=c['cents']) for s,c in self.row['cells'].items()]
    def states(self,facts,rows=None,reviews=None):return [r['status'] for r in compare_rows(rows or [self.row],facts,reviews or [])]
    def test_matching_source_and_position(self):self.assertEqual(self.states(self.facts),['matched','matched'])
    def test_deleted_line_detected(self):self.assertIn('missing',self.states(self.facts[1:]))
    def test_entire_forgotten_table_detected(self):self.assertEqual(self.states([]),['missing','missing'])
    def test_ae_cp_swap_detected(self):
        f=copy.deepcopy(self.facts);f[0]['measure']='AE';self.assertIn('missing',self.states(f))
    def test_wrong_year_detected(self):
        f=copy.deepcopy(self.facts);f[0]['year']=2021;self.assertIn('missing',self.states(f))
    def test_wrong_column_detected(self):
        f=copy.deepcopy(self.facts);f[0]['cents'],f[1]['cents']=f[1]['cents'],f[0]['cents'];self.assertEqual(self.states(f),['different','different'])
    def test_amount_error_of_one_cent_not_suppressed(self):
        f=copy.deepcopy(self.facts);f[0]['cents']+=1;self.assertIn('different',self.states(f))
    def test_duplicate_detected(self):self.assertIn('ambiguous',self.states(self.facts+[self.facts[0]]))
    def test_fabricated_zero_in_blank_cell_detected(self):
        r=copy.deepcopy(self.row);r['cells']['LFI'].update(cents=None,raw='');f=copy.deepcopy(self.facts);f[0]['cents']=0
        self.assertIn('different',self.states(f,rows=[r]))
    def test_reader_does_not_infer_zero_from_blank(self):
        with self.assertRaisesRegex(ValueError,'vide'):numeric_cells([],anchors=[42])
    def test_justification_requires_right_value_document_and_hash(self):
        r=dict(year=2020,budget='BG',path='TA/174',measure='CP',stage='LFI',status='pending',source_cents=10000,proofs=[dict(source_id='official',sha256='a'*64)])
        self.assertIn('documented_pending',self.states(self.facts[1:],reviews=[r]))
        for field,value in [('source_id','other'),('sha256','b'*64)]:
            bad=copy.deepcopy(r);bad['proofs'][0][field]=value;self.assertIn('missing',self.states(self.facts[1:],reviews=[bad]))

if __name__=='__main__':unittest.main()
