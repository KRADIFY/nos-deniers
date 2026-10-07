import copy,csv,io,json,unittest,zipfile
from budget_service import api,evolution,exports,topics
from budget_service.model import STAGES
from budget_service.comparisons import compare


def annual(year,cents,status='ok',**extra):
    row={s:dict(value=None,nominal=None,nominal_cents=None,status='missing') for s in STAGES}
    row.update(year=year)
    row['EXEC']=dict(value=cents/100 if cents is not None else None,nominal=cents/100 if cents is not None else None,nominal_cents=cents,status=status,sources=[str(year)],approximate=False,**extra)
    row['comparisons']=compare(row)
    return row


class EvolutionTests(unittest.TestCase):
    def test_nominal_real_and_reference_rates_from_unrounded_values(self):
        series=[annual(2021,10000),annual(2022,11000),annual(2023,12100)]
        evolution.attach(series,{2021:'100',2022:'110',2023:'110'})
        rates=series[1]['evolution']['EXEC']
        self.assertEqual(rates['nominal_yoy']['value'],10)
        self.assertEqual(rates['real_yoy']['value'],0)
        self.assertEqual(series[2]['evolution']['EXEC']['real_from_start']['value'],10)
        self.assertEqual(rates['real_yoy']['sources'],['2021','2022'])
        self.assertEqual([op['nominal_cents'] for op in rates['real_yoy']['operands']],[10000,11000])

    def test_display_rounding_or_currency_does_not_change_rates(self):
        series=[annual(2021,3),annual(2022,4)]
        changed=copy.deepcopy(series)
        changed[0]['EXEC']['value']=.04;changed[1]['EXEC']['value']=.06
        indices={2021:'98.25',2022:'103.8'}
        evolution.attach(series,indices);evolution.attach(changed,indices)
        self.assertEqual(series[1]['evolution'],changed[1]['evolution'])
        self.assertEqual(series[1]['evolution']['EXEC']['nominal_yoy']['value'],33.3333)

    def test_partial_missing_and_not_applicable_never_get_rates(self):
        for status in ('partial','missing','not_applicable','detail_unavailable','topic_unavailable','inflation_missing'):
            series=[annual(2021,10000),annual(2022,11000,status)]
            evolution.attach(series,{2021:100,2022:110})
            self.assertTrue(all(c['value'] is None for c in series[1]['evolution']['EXEC'].values()),status)

    def test_first_year_and_gaps_do_not_invent_annual_comparisons(self):
        series=[annual(2021,10000),annual(2023,12100)]
        evolution.attach(series,{2021:100,2023:110})
        for a in series:self.assertIsNone(a['evolution']['EXEC']['nominal_yoy']['value'])
        self.assertEqual(series[0]['evolution']['EXEC']['real_from_start']['value'],0)
        self.assertEqual(series[1]['evolution']['EXEC']['real_from_start']['value'],10)

    def test_zero_negative_reference_and_real_zero_current(self):
        for n in (0,-10):
            series=[annual(2021,n),annual(2022,100)]
            evolution.attach(series,{2021:100,2022:100})
            self.assertEqual(series[1]['evolution']['EXEC']['real_yoy']['status'],'nonpositive_reference')
        series=[annual(2021,100),annual(2022,0)]
        evolution.attach(series,{2021:100,2022:100})
        self.assertEqual(series[1]['evolution']['EXEC']['real_yoy']['value'],-100)

    def test_missing_ipc_preserves_nominal_coverage(self):
        p=api.parameters({'constant':['1']})
        fact=dict(year=2025,stage='EXEC',mission='TA',program='174',action='',subaction='',cents=10000,source='s')
        c=api.cell([fact],'TA',2025,'EXEC',p,{},expected_programs={'174','203'})
        self.assertEqual(c['status'],'inflation_missing');self.assertEqual(c['nominal_status'],'partial')
        series=[annual(2024,9000),annual(2025,10000)];series[1]['EXEC']=c
        evolution.attach(series,{2024:100})
        self.assertIsNone(series[1]['evolution']['EXEC']['nominal_yoy']['value'])
        c=api.cell([fact],'TA',2025,'EXEC',p,{},expected_programs={'174'})
        series[1]['EXEC']=c;evolution.attach(series,{2024:100})
        self.assertEqual(series[1]['evolution']['EXEC']['nominal_yoy']['value'],11.1111)
        self.assertEqual(series[1]['evolution']['EXEC']['real_yoy']['status'],'inflation_missing')

    def test_missing_ipc_does_not_skip_the_policy_subtraction(self):
        p=api.parameters({'constant':['1'],'topic':['maprimerenov'],'topic_mode':['without']})
        fact=dict(year=2024,stage='EXEC',mission='TA',program='174',action='',subaction='',cents=100000000000,source='s')
        c=api.cell([fact],'TA',2024,'EXEC',p,{})
        c=topics.calculate([fact],c,'TA',2024,'EXEC',p,{})
        self.assertIsNone(c['value']);self.assertEqual(c['nominal_cents'],30798227900)
        self.assertEqual(c['nominal_status'],'ok')

    def test_exports_preserve_rates_status_proofs_and_column_alignment(self):
        series=[annual(2021,10000),annual(2022,11000)]
        series[1]['EXEC']['approximate']=True
        evolution.attach(series,{2021:100,2022:110})
        self.assertTrue(series[1]['evolution']['EXEC']['nominal_yoy']['approximate'])
        for topic in ('','maprimerenov'):
            p=api.parameters({'start':['2021'],'end':['2022'],'topic':[topic]})
            d=dict(parameters=p,scope_label='test',totals=series,rows=[],exclusions=[],notes=[],data_version='v',selection_id='s',inflation={},topic={'perimeter':'test'},calculation_version=evolution.VERSION)
            rows=list(csv.reader(io.StringIO(api.export_csv(d).decode('utf-8-sig')),delimiter=';'))
            self.assertTrue(all(len(r)==len(rows[0]) for r in rows))
            actual=next(r for r in rows[1:] if r[4]=='2022' and r[6]==STAGES['EXEC'])
            self.assertEqual(actual[rows[0].index('Variation annuelle courante %')],'10,0')
            with zipfile.ZipFile(io.BytesIO(exports.xlsx(d,[]))) as z:
                xml=z.read('xl/worksheets/sheet5.xml').decode()
                self.assertIn('Opérandes et indices',xml);self.assertIn('nominal_cents',xml)
                self.assertIn('Évolution annuelle',z.read('xl/workbook.xml').decode())
            self.assertNotEqual(exports.fingerprint(d),exports.fingerprint(dict(d,calculation_version='different')))


if __name__=='__main__':unittest.main()
