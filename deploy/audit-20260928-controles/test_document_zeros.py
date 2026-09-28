import copy,json,tempfile,unittest
from pathlib import Path
from document_zeros import DocumentProofs,fact_key

class DocumentZeroTests(unittest.TestCase):
    def fixture(self,folder):
        f=dict(source='id',year=2024,stage='LFI',measure='AE',program='370')
        p=dict(fact=f,sha256='sha',kind='pdf',page=1,status='source_zero',raw='0',reason='Source relue',reviewed_on='2026-09-28',fragments=[dict(box=[0,0,10,10],text='0',role='value')])
        path=Path(folder)/'proof.json';path.write_text(json.dumps(dict(proofs=[p])),'utf-8')
        reader=DocumentProofs(path);return f,p,reader
    def test_fact_identity_includes_year_measure_and_stage(self):
        with tempfile.TemporaryDirectory() as t:
            f,p,r=self.fixture(t)
            for k,v in [('year',2023),('measure','CP'),('stage','EXEC'),('program','371')]:
                altered=dict(f,**{k:v});self.assertIsNone(r.inspect(altered,{'sha256':'sha'},Path('x')))
    def test_changed_hash_does_not_reuse_review(self):
        with tempfile.TemporaryDirectory() as t:
            f,p,r=self.fixture(t);self.assertEqual(r.inspect(f,{'sha256':'changed'},Path('x'))['status'],'undetermined')
    def test_pdf_blank_dash_and_nonzero_never_pass(self):
        with tempfile.TemporaryDirectory() as t:
            f,p,r=self.fixture(t)
            for value in ('0','','—','12'):
                r.page=lambda *args,v=value:([dict(text=v,xMin=1,xMax=9,yMin=1,yMax=9)] if v else [])
                self.assertEqual(r.inspect(f,{'sha256':'sha'},Path('x'))['status'],'source_zero' if value=='0' else 'undetermined')
    def test_calculated_zero_requires_both_published_operands(self):
        with tempfile.TemporaryDirectory() as t:
            f,p,r=self.fixture(t);p=copy.deepcopy(p);p['status']='calculated_zero';p['fragments'][0]['role']='operand_1'
            r.proofs[fact_key(f)]=p;r.page=lambda *args:[dict(text='0',xMin=1,xMax=9,yMin=1,yMax=9)]
            self.assertEqual(r.inspect(f,{'sha256':'sha'},Path('x'))['status'],'undetermined')
            p['fragments'].append(dict(p['fragments'][0],role='operand_2'))
            self.assertEqual(r.inspect(f,{'sha256':'sha'},Path('x'))['status'],'calculated_zero')
    def test_html_cell_and_heading_must_both_match(self):
        with tempfile.TemporaryDirectory() as t:
            f,p,r=self.fixture(t);p.update(kind='html',table=1,row=2,column=2,header=['Programme','AE','CP'],cells=['P370','0','12'])
            r.proofs[fact_key(f)]=p;path=Path(t)/'source.html'
            def check(header,ae):
                path.write_text('<table><tr><th>Programme</th><th>'+header+'</th><th>CP</th></tr><tr><td>P370</td><td>'+ae+'</td><td>12</td></tr></table>','utf-8');r.cache.clear()
                return r.inspect(f,{'sha256':'sha'},path)['status']
            self.assertEqual(check('AE','0'),'source_zero');self.assertEqual(check('AE',''),'undetermined');self.assertEqual(check('CP','0'),'undetermined')
if __name__=='__main__':unittest.main()
