import importlib.util,unittest,threading,tempfile,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
spec=importlib.util.spec_from_file_location('link_probe',Path(__file__).resolve().parents[1]/'tools/check_document_links.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  code,kind,body={'/pdf':(200,'application/pdf',b'%PDF-1.7\nexample'),'/fake.pdf':(200,'text/html',b'<html>Error</html>'),'/empty':(200,'application/pdf',b''),'/missing':(404,'text/html',b'no'),'/blocked':(403,'text/html',b'blocked'),'/file.xlsx':(200,'application/octet-stream',b'PK\x03\x04example'),'/html':(200,'text/html',b'<html>Page document</html>')}[self.path]
  self.send_response(code);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(body)
class LinksTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever);cls.thread.start();cls.base='http://127.0.0.1:'+str(cls.server.server_port)
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
 def test_pdf_and_office_open(self):
  for path,fmt in [('/pdf','pdf'),('/file.xlsx','xlsx'),('/html','html')]:self.assertEqual(m.probe(self.base+path,fmt)['status'],'accessible')
 def test_html_is_not_accepted_as_pdf(self):self.assertEqual(m.probe(self.base+'/fake.pdf','pdf')['status'],'defaut')
 def test_empty_not_accepted(self):self.assertEqual(m.probe(self.base+'/empty','pdf')['status'],'defaut')
 def test_missing_and_blocked_are_distinct(self):
  self.assertEqual(m.probe(self.base+'/missing')['status'],'introuvable');self.assertEqual(m.probe(self.base+'/blocked')['status'],'non_verifie')
 def test_unsafe_scheme_not_requested(self):self.assertEqual(m.probe('javascript:alert(1)')['status'],'defaut')
 def test_deduplicate_fragments_and_keep_report(self):
  with tempfile.TemporaryDirectory() as d:
   links={u:dict(url=u,label='PDF') for u in [self.base+'/pdf#page=1',self.base+'/pdf#page=431']}
   summary=m.run(self.base,d,links,delay=0,catalogue=False)
   self.assertEqual(summary['planned'],1);self.assertEqual(summary['accessible'],1);self.assertTrue(summary['finished']);self.assertTrue((Path(d)/'rapport-liens.html').exists())
 def test_invalid_page_reported(self):
  with tempfile.TemporaryDirectory() as d:
   url=self.base+'/pdf#page=0';summary=m.run(self.base,d,{url:dict(url=url)},delay=0,catalogue=False);self.assertEqual(summary['broken'],1)
if __name__=='__main__':unittest.main()
