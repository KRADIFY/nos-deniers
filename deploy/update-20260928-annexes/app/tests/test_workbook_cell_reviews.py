import unittest
from budget_service import api, cell_reviews

class WorkbookCellReviewTests(unittest.TestCase):
    def setUp(self):
        self.p=api.parameters({})
        self.row=dict(year=2025,stage='LFI',measure='CP',budget='BG',mission='AQ',mission_label='Audiovisuel',program='372',program_label='Projet',action='',action_label='',subaction='',subaction_label='',category='',title='',cents=100,source='a'*20,line=1,field='total',approximate=0)
        self.review=dict(year=2025,stage='LFI',measure='CP',budget='BG',path='AQ/372',status='not_applicable',explanation='Programme proposé au PLF ; financement voté en CCF.',method='Contrôle du RAP',proofs=[dict(source_id='a'*20,physical_page=2,evidence='Tableau du périmètre')])
        self.reviews={(2025,'LFI','CP','BG','AQ/372'):self.review}

    def test_non_applicable_is_never_numeric_zero(self):
        result=api.cell([], 'AQ/372',2025,'LFI',self.p,{},reviews=self.reviews)
        self.assertIsNone(result['value']);self.assertEqual(result['status'],'not_applicable')
        self.assertEqual(result['citations'][0]['page'],2)

    def test_applicability_is_specific_to_year_budget_stage_and_measure(self):
        for y,s,p in [(2024,'LFI',self.p),(2025,'PLF',self.p),(2025,'LFI',dict(self.p,measure='AE')),(2025,'LFI',dict(self.p,budget='CCF'))]:
            with self.subTest(y=y,s=s,p=p):
                self.assertEqual(api.cell([], 'AQ/372',y,s,p,{},reviews=self.reviews)['status'],'missing')

    def test_non_applicable_not_expected_but_real_missing_remains_partial(self):
        value=dict(self.row,program='373')
        result=api.cell([value], 'AQ',2025,'LFI',self.p,{},expected_programs={'372','373'},reviews=self.reviews)
        self.assertEqual(result['value'],1);self.assertEqual(result['status'],'ok')
        result=api.cell([value], 'AQ',2025,'LFI',self.p,{},expected_programs={'372','373','374'},reviews=self.reviews)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['missing_programs'][0]['code'],'374')

    def test_pending_and_verified_missing_do_not_fabricate_zero(self):
        for status in ('pending','verified'):
            reviews={k:dict(v,status=status) for k,v in self.reviews.items()}
            result=api.cell([], 'AQ/372',2025,'LFI',self.p,{},reviews=reviews)
            self.assertIsNone(result['value']);self.assertEqual(result['status'],'missing')

    def test_exclusion_does_not_get_overridden_by_review(self):
        result=api.cell([self.row], 'AQ/372',2025,'LFI',dict(self.p,exclude=['AQ/372']),{},reviews=self.reviews)
        self.assertEqual(result['value'],0);self.assertEqual(result['status'],'excluded')

    def test_documented_non_applicability_has_no_request_letter(self):
        x=cell_reviews.explain([self.review],dict(status='not_applicable'),None)
        self.assertFalse(x['contacts']);self.assertEqual(x['request_text'],'');self.assertTrue(x['references'])

    def test_one_review_does_not_replace_partial_total_explanation(self):
        prior=dict(summary='Ce total est partiel.',details=[],references=[])
        x=cell_reviews.explain([self.review],dict(status='partial'),prior,'AQ')
        self.assertEqual(x['summary'],'Ce total est partiel.')
        self.assertIn('AQ/372',x['details'][0])

if __name__=='__main__':unittest.main()
