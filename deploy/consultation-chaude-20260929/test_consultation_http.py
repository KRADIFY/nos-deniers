import gzip,json,threading,unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from budget_service import web,consultation as c

class CacheHTTPTests(unittest.TestCase):
    def setUp(self):
        self.payload={'amount':12.34,'zero':0,'missing':None,'sources':['x']*800}
        self.cache_patch=patch.object(c,'CACHE',c.ResponseCache());self.cache_patch.start()
        self.build_patch=patch.object(c,'build',return_value=c.Payload.encode(self.payload,'attachment; filename=test.json'))
        self.build=self.build_patch.start()
        self.server=web.BudgetHTTPServer(('127.0.0.1',0),web.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.build_patch.stop();self.cache_patch.stop()
    def fetch(self,headers=None,method='GET'):
        with urlopen(Request(self.url+'/api/explorer',headers=headers or {},method=method),timeout=5) as r:
            return dict(r.headers),r.read()
    def test_gzip_identity_and_head_share_one_computation(self):
        h,b=self.fetch({'Accept-Encoding':'gzip'})
        self.assertEqual(json.loads(gzip.decompress(b)),self.payload)
        self.assertEqual(int(h['Content-Length']),len(b));self.assertEqual(h['Content-Encoding'],'gzip')
        h,plain=self.fetch({'Accept-Encoding':'gzip;q=0'})
        self.assertEqual(json.loads(plain),self.payload);self.assertNotIn('Content-Encoding',h)
        h,head=self.fetch({'Accept-Encoding':'gzip'},'HEAD')
        self.assertEqual(head,b'');self.assertEqual(int(h['Content-Length']),len(b))
        self.assertEqual(h['Content-Disposition'],'attachment; filename=test.json')
        self.assertEqual(h['Cache-Control'],'no-store');self.assertIn('default-src',h['Content-Security-Policy'])
        self.assertEqual(self.build.call_count,1)
    def test_overload_has_json_and_recovers(self):
        original=self.server.slots;self.server.slots=threading.BoundedSemaphore(0)
        with self.assertRaises(HTTPError) as caught:self.fetch()
        self.assertEqual(caught.exception.code,503)
        self.assertTrue(json.loads(caught.exception.read())['error'])
        self.server.slots=original
        self.assertEqual(json.loads(self.fetch()[1]),self.payload)
    def test_invalid_filter_does_not_read_or_cache_data(self):
        with self.assertRaises(HTTPError) as caught:urlopen(self.url+'/api/explorer?measure=BAD',timeout=5)
        self.assertEqual(caught.exception.code,400);self.build.assert_not_called()
        self.assertEqual(c.CACHE.status()['entries'],0)
    def test_busy_calculation_has_friendly_json(self):
        self.build.side_effect=c.Busy('Capacity')
        with self.assertRaises(HTTPError) as caught:self.fetch()
        self.assertEqual(caught.exception.code,503);self.assertIn('error',json.loads(caught.exception.read()))
        self.assertEqual(c.CACHE.status()['entries'],0)

if __name__=='__main__':unittest.main()
