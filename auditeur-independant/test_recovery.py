import argparse,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from audit import Campaign,params

class RecoveryTests(unittest.TestCase):
    def test_checkpoint_retains_completed_retries_incomplete_and_refuses_changed_version(self):
        with tempfile.TemporaryDirectory() as t:
            refpath=Path(t)/'ref';refpath.mkdir();(refpath/'manifest.json').write_text('{}')
            ref=Mock();ref.meta={'fact_count':1,'data_version':'stable','indices':{}}
            client=Mock();client.get.side_effect=lambda p,*a:{'meta':ref.meta} if p=='/api/bootstrap' else b'asset'
            a=argparse.Namespace(reference=refpath,output=Path(t)/'results',url='https://budget.test',delay=0,quick=True,no_browser=False)
            with patch('audit.Reference',return_value=ref),patch('audit.Management'),patch('audit.Client',return_value=client),patch('audit.plan',return_value=[('tree',params('BG','CP'))]):
                first=Campaign(a);first.record('good','tree',{},dict(errors=[]));first.record('retry','tree',{},dict(errors=[],incomplete=True));first.db.close()
                resumed=Campaign(a);self.assertIn('good',resumed.done);self.assertNotIn('retry',resumed.done);resumed.db.close()
                client.get.side_effect=lambda p,*args:{'meta':ref.meta} if p=='/api/bootstrap' else b'changed asset'
                with self.assertRaisesRegex(ValueError,'modifiés'):Campaign(a)
if __name__=='__main__':unittest.main()
