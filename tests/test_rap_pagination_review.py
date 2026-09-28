"""Independent regression review: bounded pages, complete downloads and gap evidence."""
import copy,json,sqlite3,unittest
from unittest.mock import Mock,patch
from budget_service import rap_movements,rap_quality,reserves,web

class MovementPaginationReview(unittest.TestCase):
    def setUp(self):
        self.result=dict(count=1003,items=[{'id':str(i)} for i in range(1003)],proofs=[{'cells':[None,0,1]}],evidence_rows=[{'cells':[None,0,1]}],table_totals=[{'total':0}],evidence_row_count=1,table_total_count=1,selection_id='stable',sources=[{'id':'a'*20}],reconciliations=[{'status':'exact'}])
    def test_pages_cover_each_row_once_and_keep_selection_metadata(self):
        original=copy.deepcopy(self.result);parts=[]
        for offset,wanted in [(0,500),(500,500),(1000,3)]:
            page=rap_movements.page_result(self.result,offset,500);parts+=page['items']
            self.assertEqual(len(page['items']),wanted);self.assertEqual(page['count'],1003)
            self.assertEqual(page['displayed_count'],min(offset+500,1003));self.assertEqual(page['has_more'],offset<1000)
            self.assertEqual(page['next_offset'],offset+500 if offset<1000 else None)
            self.assertEqual(page['sources'],original['sources']);self.assertEqual(page['selection_id'],'stable')
            for field in ('proofs','evidence_rows','table_totals'):self.assertNotIn(field,page)
        self.assertEqual(parts,original['items']);self.assertEqual(self.result,original)
    def test_empty_and_out_of_range_page_counters_do_not_exceed_total(self):
        for count,offset in [(0,0),(0,500),(1003,1500)]:
            page=rap_movements.page_result(dict(self.result,count=count,items=self.result['items'][:count]),offset)
            self.assertEqual(page['items'],[]);self.assertFalse(page['has_more']);self.assertIsNone(page['next_offset'])
            self.assertLessEqual(page['displayed_count'],count)
    def test_invalid_direct_page_arguments_are_rejected(self):
        for offset,limit in [(-1,500),(0,0),(0,501),(True,500),(0,True),('0',500),(0,1.5)]:
            with self.subTest(offset=offset,limit=limit),self.assertRaises(ValueError):rap_movements.page_result(self.result,offset,limit)
    def request(self,url):
        handler=object.__new__(web.Handler);handler.path=url;handler.reply=Mock();db=sqlite3.connect(':memory:')
        with patch.object(web.api,'connect',return_value=db),patch.object(web.api,'metadata',return_value={}),patch.object(web.rap_movements,'query',return_value=copy.deepcopy(self.result)) as query:
            handler.do_GET()
        return handler.reply,query
    def test_http_summary_is_paged_but_download_preserves_all_rows_and_proofs(self):
        common='/api/rap-movements?start=2024&end=2025&scope=TA&measure=AE'
        reply,query=self.request(common+'&view=summary&offset=500&limit=500');result=reply.call_args.args[0]
        self.assertEqual(len(result['items']),500);self.assertEqual(result['items'][0]['id'],'500');self.assertFalse(query.call_args.kwargs['include_evidence'])
        reply,query=self.request(common+'&view=summary&offset=500&limit=500&download=1');result=reply.call_args.args[0]
        self.assertEqual(len(result['items']),1003);self.assertEqual(result['proofs'][0]['cells'],[None,0,1]);self.assertTrue(query.call_args.kwargs['include_evidence'])
        self.assertIn('attachment;',reply.call_args.kwargs['disposition']);self.assertNotIn('next_offset',result)
    def test_invalid_http_page_is_400_before_query(self):
        for params in ('offset=-1','limit=0','limit=501','offset=nope'):
            reply,query=self.request('/api/rap-movements?view=summary&'+params)
            self.assertEqual(reply.call_args.args[1],400);query.assert_not_called()

class InvestigationEvidenceReview(unittest.TestCase):
    def setUp(self):
        self.p=dict(start=2023,end=2025,budget='BG',measure='CP',scope='',exclude=[],constant=False,base=2025,topic='',topic_mode='only')
        self.meta={'indices':{'2023':100,'2024':110,'2025':120}}
    def test_all_48_reserve_gaps_remain_non_numeric_after_investigation(self):
        for measure in ('AE','CP'):
            result=reserves.query(dict(self.p,measure=measure),self.meta);rows=[r for r in result['items'] if not r['table_available']]
            self.assertEqual(len(rows),48)
            for r in rows:
                for cell in r['cells'].values():
                    self.assertIsNone(cell['value']);self.assertIsNone(cell.get('nominal_cents'));self.assertNotIn('contextual_amounts',cell.get('explanation',{}))
    def test_370_2025_permanent_exemption_has_current_evidence_without_numeric_zeros(self):
        source='2ec6de25d671f24e0e80'
        sha='2ec6de25d671f24e0e80229b9631b3f63fd7f5c380a23e6778b3714ac1612072'
        for measure in ('AE','CP'):
            with self.subTest(measure=measure):
                p=dict(self.p,start=2025,end=2025,scope='AD/370',measure=measure)
                row=next(r for r in rap_quality.reserve_placeholders()
                         if r['year']==2025 and r['program']=='370' and r['measure']==measure)
                x=rap_quality.explanation(p,row,'reserves','table_unavailable')
                self.assertIn('exemption documentée',x['title'].lower())
                refs=[r for r in x['references'] if r.get('source')==source]
                self.assertEqual({r['page'] for r in refs},{5,6})
                self.assertTrue(all(r['sha256']==sha and r['url'].startswith('https://www.diplomatie.gouv.fr/') for r in refs))
                self.assertIn(('18a66d93f7cacc822267',137),
                              {(r.get('source'),r.get('page')) for r in x['references']})
                # A permanent rule, still cited by RAP 2025, is not an annual flow table.
                self.assertEqual(x['status'],'table_unavailable')
                result=reserves.query(p,self.meta)
                self.assertEqual(len(result['items']),1)
                actual=result['items'][0]
                self.assertFalse(actual['table_available']);self.assertTrue(actual['cells'])
                for cell in actual['cells'].values():
                    self.assertEqual(cell['status'],'table_unavailable')
                    self.assertIsNone(cell['value']);self.assertIsNone(cell['nominal_cents'])
                    self.assertIsNone(cell['source_cells'])
    def test_partial_cp_finding_does_not_become_full_ae_reserve(self):
        p=dict(self.p,start=2025,end=2025,scope='PR/362',measure='AE')
        row=next(r for r in rap_quality.reserve_placeholders() if r['year']==2025 and r['program']=='362' and r['measure']=='AE')
        x=rap_quality.explanation(p,row,'reserves','table_unavailable')
        self.assertIn('CP',x['title']);self.assertNotIn('contextual_amounts',x)
        finding=next(r for r in rap_quality.registry()[0]['investigations']
                     if r['kind']=='reserves' and r['year']==2025 and r['program']=='362')
        self.assertEqual(finding['evidence_scope']['annual_no_freeze_measures'],['CP'])
        self.assertFalse(finding['evidence_scope']['annual_execution_table_found'])
        self.assertIn('AE',finding['limitation'])
        self.assertIn(('d712fb3178eaed0285d2',23),
                      {(r.get('source'),r.get('page')) for r in x['references']})
        actual=reserves.query(p,self.meta)['items']
        self.assertEqual(len(actual),1);self.assertFalse(actual[0]['table_available'])
        self.assertTrue(actual[0]['cells'])
        for cell in actual[0]['cells'].values():
            self.assertEqual(cell['status'],'table_unavailable')
            self.assertIsNone(cell['value']);self.assertIsNone(cell['nominal_cents'])
            self.assertIsNone(cell['source_cells'])
    def test_fine_selection_keeps_annual_net_explicitly_at_programme_scope(self):
        row=next(r for r in rap_quality.registry()[0]['gaps'] if r['year']==2023 and r['program']=='382')
        for p in (dict(self.p,scope='AC/382/01'),dict(self.p,scope='AC/382',exclude=['AC/382/01'])):
            x=rap_quality.explanation(p,row,'movements','table_unavailable');context=x['contextual_amounts'][0]
            self.assertEqual(context['cents'],0)
            words=' '.join(x['details']+[context['label'],context['caution']]).lower()
            self.assertRegex(words,r'programme entier|programme 382')
            self.assertRegex(words,r'action|sous-action')
    def test_unverified_primary_source_suppresses_contextual_amount(self):
        row=next(r for r in rap_quality.registry()[0]['gaps'] if r['year']==2023 and r['program']=='382')
        x=rap_quality.explanation(self.p,row,'movements','source_unverified');self.assertEqual(x['references'],[]);self.assertNotIn('contextual_amounts',x)

if __name__=='__main__':unittest.main()
