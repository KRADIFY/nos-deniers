import hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import update_existing as u

class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bundle=self.root/'bundle';self.bundle.mkdir()
  self.audit=self.root/'audit';self.audit.mkdir();self.budget=self.root/'budget';self.site=self.budget/'releases/current';(self.site/'data/derived').mkdir(parents=True)
  (self.site/'data/derived/budget.sqlite').write_bytes(b'unchanged database');(self.site/'compose.yaml').write_text('unchanged site compose')
  u.write(self.budget/'deployment.json',dict(release=str(self.site),data_version='version'))
  self.old=dict(services=dict(audit=dict(image='old:image',volumes=[str(self.site/'data')+':/reference/data:ro','/old/registries:/reference/registries:ro','/state:/audit-data'],environment={},ports=['127.0.0.1:8554:8095'])))
  u.write(self.audit/'compose.json',self.old);u.write(self.audit/'INSTALLED.json',dict(audit_image='old:image'))
  self.files={'web/index.html':b'index','web/app.js':b'app','web/memo.html':b'memo'}
  for name,body in self.files.items():
   p=self.bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
  u.write(self.bundle/'FILES.json',{n:hashlib.sha256(b).hexdigest() for n,b in self.files.items()})
  self.paths=patch.multiple(u,ROOT=self.audit,BUNDLE=self.bundle,BUDGET=self.budget,TARGET=self.audit/'releases'/u.TAG,COMPOSE=self.audit/'compose.json',RECEIPT=self.audit/'INSTALLED.json');self.paths.start()
 def tearDown(self):self.paths.stop();self.tmp.cleanup()
 def get(self,route):
  if route=='/api/status':return b'{"status":"complete"}'
  return self.files[{'/':'web/index.html','/app.js':'web/app.js','/memo':'web/memo.html'}[route]]
 def test_running_audit_is_not_interrupted(self):
  with patch.object(u,'get',return_value=b'{"status":"running"}'),patch.object(u,'run') as run:
   with self.assertRaisesRegex(ValueError,'Audit en cours'):u.main()
   run.assert_not_called()
  self.assertEqual(u.read(u.COMPOSE),self.old)
 def test_changed_bundle_stops_before_docker(self):
  (self.bundle/'web/app.js').write_bytes(b'changed')
  with patch.object(u,'run') as run:
   with self.assertRaisesRegex(ValueError,'Fichier different'):u.main()
   run.assert_not_called()
 def exercise(self,get):
  with patch.object(u,'get',side_effect=get),patch.object(u,'run') as run,patch.object(u,'output',return_value='web-id'),patch.object(u,'health'),patch.object(u.urllib.request,'urlopen',return_value=io.BytesIO(b'{"service":"nos-deniers-audit-independant"}')):
   u.main()
   return run.call_args_list
 def test_success_preserves_site_and_state_mount(self):
  calls=self.exercise(self.get);config=u.read(u.COMPOSE)
  self.assertEqual(config['services']['audit']['volumes'][-1],'/state:/audit-data')
  self.assertEqual((self.site/'data/derived/budget.sqlite').read_bytes(),b'unchanged database')
  self.assertEqual((self.site/'compose.yaml').read_text(),'unchanged site compose')
  self.assertEqual(config['services']['audit']['image'],'nos-deniers-audit:'+u.TAG)
  self.assertFalse(any('web' in c.args and 'up' in c.args for c in calls))
 def test_bad_served_assets_restores_previous_auditor(self):
  def wrong(route):return self.get(route) if route=='/api/status' else b'wrong assets'
  with self.assertRaisesRegex(ValueError,'Interface servie differente'):self.exercise(wrong)
  self.assertEqual(u.read(u.COMPOSE),self.old)
  self.assertEqual(u.read(u.RECEIPT)['audit_image'],'old:image')
if __name__=='__main__':unittest.main()
