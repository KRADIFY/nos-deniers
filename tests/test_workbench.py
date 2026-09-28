import io,json,threading,unittest,zipfile
from urllib.request import urlopen
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from budget_service.comparisons import compare
from budget_service.exports import xlsx,fingerprint
from budget_service.web import Handler
from budget_service.model import STAGES


def value(n,status='ok',nominal=None):
    return dict(value=n,nominal=n if nominal is None else nominal,status=status,sources=['source'],reason='',approximate=False)


class WorkbenchTests(unittest.TestCase):
    def test_consumption_can_exceed_lfi_but_denominator_is_explicit(self):
        year={s:value(0) for s in STAGES};year.update(PLF=value(80),LFI=value(100),EXEC=value(120),OUVERT=value(150))
        self.assertEqual(compare(year)['LFI_PLF']['value'],20)
        self.assertEqual(compare(year)['EXEC_LFI']['value'],20)
        self.assertEqual(compare(year)['CONSUMPTION']['value'],120)
        self.assertEqual(compare(year,'OUVERT')['CONSUMPTION']['value'],80)

    def test_no_rate_for_missing_partial_or_zero_denominator(self):
        year={s:value(0) for s in STAGES};year.update(EXEC=value(20),LFI=value(0))
        self.assertEqual(compare(year)['CONSUMPTION']['status'],'zero_denominator')
        for c in [value(None,'missing'),value(100,'partial'),value(None,'inflation_missing')]:
            year['LFI']=c
            self.assertIsNone(compare(year)['CONSUMPTION']['value'])

    def test_rate_uses_unrounded_nominal_values_under_inflation(self):
        year={s:value(0) for s in STAGES};year.update(EXEC=value(.02,nominal=.01),LFI=value(.05,nominal=.03))
        self.assertEqual(compare(year)['CONSUMPTION']['value'],33.3333)

    def test_selection_fingerprint_depends_on_data_exclusions_and_ipc(self):
        d=dict(parameters={'exclude':[]},data_version='v1',inflation={'2025':'100'},topic_version='t1')
        h=fingerprint(d)
        self.assertEqual(h,fingerprint(dict(reversed(list(d.items())))))
        for key,v in [('data_version','v2'),('parameters',{'exclude':['TA/174']}),('inflation',{'2025':'101'})]:
            self.assertNotEqual(h,fingerprint(dict(d,**{key:v})))

    def test_xlsx_preserves_numeric_zero_blank_and_untrusted_text(self):
        annual={s:value(None,'missing') for s in STAGES};annual.update(year=2025,PLF=value(0));annual['comparisons']=compare(annual)
        d=dict(parameters=dict(scope='',budget='BG',measure='CP'),scope_label='=1+1',totals=[annual],rows=[],notes=[],inflation={},data_version='v',selection_id='s')
        data=xlsx(d,[])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml=z.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn('<v>0</v>',xml);self.assertNotIn('<f>',xml);self.assertIn('=1+1',xml)
            self.assertIn('xl/worksheets/sheet4.xml',z.namelist())

    def test_http_preserves_explicit_all_formats_value(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        class DB:
            def close(self):pass
        try:
            with patch('budget_service.web.api.connect',return_value=DB()),patch('budget_service.web.api.documents',side_effect=lambda db,q:{'format':q.get('format',['pdf'])[0]}):
                self.assertEqual(json.load(urlopen(f'http://127.0.0.1:{server.server_port}/api/documents?format='))['format'],'')
                self.assertEqual(json.load(urlopen(f'http://127.0.0.1:{server.server_port}/api/documents'))['format'],'pdf')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
