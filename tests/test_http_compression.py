import gzip,io,json,unittest
from unittest.mock import Mock
from budget_service.web import Handler,accepts_gzip

class CompressionTests(unittest.TestCase):
    def response(self,accept='gzip',command='GET',kind='application/json',payload=None):
        handler=object.__new__(Handler);handler.headers={'Accept-Encoding':accept}
        handler.command=command;handler.wfile=io.BytesIO();handler.send_headers=Mock()
        handler.reply(payload if payload is not None else {'evidence':['économie']*2000},kind=kind)
        return handler
    def test_explicit_refusal_wins_over_wildcard(self):
        for value in ('gzip;q=0, *;q=1','gzip;q=nan','gzip;q=2','br','gzip;q=bad'):
            self.assertFalse(accepts_gzip(value),value)
        self.assertTrue(accepts_gzip('br, gzip;q=0.5'))
    def test_payload_and_length_are_exact(self):
        h=self.response();body=h.wfile.getvalue()
        self.assertEqual(json.loads(gzip.decompress(body)),{'evidence':['économie']*2000})
        self.assertEqual(h.send_headers.call_args.args[2],len(body))
        self.assertEqual(h.send_headers.call_args.kwargs,{'encoding':'gzip','vary':True})
        self.assertLess(len(body),1000)
    def test_head_has_get_length_without_body(self):
        head=self.response(command='HEAD');get=self.response()
        self.assertEqual(head.send_headers.call_args,get.send_headers.call_args)
        self.assertEqual(head.wfile.getvalue(),b'')
    def test_identity_and_binary_download_unchanged(self):
        h=self.response(accept='gzip;q=0')
        self.assertIsNone(h.send_headers.call_args.kwargs['encoding'])
        self.assertEqual(json.loads(h.wfile.getvalue())['evidence'][0],'économie')
        h=self.response(kind='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',payload=b'x'*2000)
        self.assertEqual(h.wfile.getvalue(),b'x'*2000)
        self.assertEqual(h.send_headers.call_args.kwargs,{'encoding':None,'vary':False})

if __name__=='__main__':unittest.main()
