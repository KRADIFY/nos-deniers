import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch,Mock
import service
from site_link import patch as patch_link

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=service.STATE;service.STATE=Path(self.tmp.name);service.process=None
        self.server=service.ThreadingHTTPServer(('127.0.0.1',0),service.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();service.STATE=self.old;service.process=None;self.tmp.cleanup()
    def request(self,path,data=None,headers=None):
        req=urllib.request.Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def test_health_and_page(self):
        code,b,h=self.request('/healthz');self.assertEqual(code,200);self.assertTrue(json.loads(b)['read_only_reference'])
        code,b,h=self.request('/');self.assertEqual(code,200);self.assertIn(b'Lancer la',b);self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])
    def test_files_not_exposed(self):
        for p in ('/worker.py','/reference/budget.sqlite','/../service.py','/reports/20260928-120000-abcdef/checkpoints.sqlite','/reports/../../service.py'):
            self.assertEqual(self.request(p)[0],404)
    def test_cross_origin_and_untrusted_target(self):
        self.assertEqual(self.request('/api/run',{}, {'Content-Type':'application/json','Origin':'https://example.org'})[0],403)
        for d in ({'url':'http://internal'},{'resume':'yes'},{'path':'/tmp/xx'}):
            self.assertEqual(self.request('/api/run',d, {'Content-Type':'application/json','Origin':service.PUBLIC})[0],400)
    def test_single_flight(self):
        child=Mock();child.poll.return_value=None
        with patch('service.subprocess.Popen',return_value=child) as spawn:
            a,code=service.start();self.assertEqual(code,202)
            b,code=service.start();self.assertEqual(code,202);self.assertEqual(a['run_id'],b['run_id']);spawn.assert_called_once()
    def test_targeted_run_is_separate_and_single_flight(self):
        child=Mock();child.poll.return_value=None
        with patch('service.subprocess.Popen',return_value=child) as spawn:
            headers={'Content-Type':'application/json','Origin':service.PUBLIC}
            code,body,_=self.request('/api/run',{'mode':'delta'},headers)
            self.assertEqual(code,202)
            state=json.loads(body);self.assertEqual(state['mode'],'delta')
            self.assertTrue(spawn.call_args.args[0][2].endswith('controle_cible.py'))
            code,body,_=self.request('/api/run',{'mode':'full'},headers)
            self.assertEqual(code,202)
            self.assertEqual(json.loads(body)['run_id'],state['run_id'])
            spawn.assert_called_once()
        self.assertEqual(self.request('/api/run',{'mode':'unknown'},headers)[0],400)

    def test_dead_worker_can_resume(self):
        child=Mock();child.poll.return_value=None
        with patch('service.subprocess.Popen',return_value=child):a,_=service.start()
        child.poll.return_value=137
        self.assertEqual(service.current()['status'],'interrupted')
        new=Mock();new.poll.return_value=None
        with patch('service.subprocess.Popen',return_value=new):b,code=service.start(True)
        self.assertEqual(code,202);self.assertEqual(a['run_id'],b['run_id'])
    def test_completed_scan_cooldown(self):
        import time
        service.write(service.STATE/'service-state.json',dict(status='complete',started_unix=time.time()))
        self.assertEqual(service.start()[1],429)
    def test_link_is_only_change_and_idempotent(self):
        h='<nav class="nav"><button>Crédits</button></nav><p>Inchangé</p>';c='body{color:blue}'
        hh,cc=patch_link(h,c);self.assertEqual(patch_link(hh,cc),(hh,cc))
        self.assertEqual(hh.replace(__import__('site_link').LINK,''),h);self.assertEqual(cc.removesuffix(__import__('site_link').CSS),c)
if __name__=='__main__':unittest.main()
