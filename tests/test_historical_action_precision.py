import copy,json,unittest
from budget_service import action_details,exports
from budget_service.api import cell,parameters

class HistoricalActionPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.group=next(g for g in action_details.registry()[0]['groups']if
            (g['year'],g['budget'],g['program'],g['measure'],g['stage'])==(2021,'BG','101','AE','EXEC'))
        class SourceDB:
            def execute(inner,*args):return inner
            def fetchone(inner):return (json.dumps({'sha256':self.group['sha256']}),)
        self.records=action_details.attach([copy.deepcopy(self.group['parent'])],SourceDB())
    def value(self,scope,exclude=()):
        p=dict(parameters({}),measure='AE',exclude=list(exclude))
        return cell(self.records,scope,2021,'EXEC',p,{})
    def test_cent_precision_and_excel_locator_survive_into_api_and_export(self):
        result=self.value('JA/101/01')
        self.assertEqual(result['nominal_cents'],55306477480)
        self.assertFalse(result['approximate'])
        self.assertEqual(result['citations'],[])
        self.assertIn('Crédits!S730',exports.source_locators(result))
        self.assertNotIn('PDF',exports.source_locators(result))
    def test_exact_source_parent_and_exclusion_reconcile_to_cent(self):
        parent=self.value('JA/101');child=self.value('JA/101/01')
        remainder=self.value('JA/101',exclude=['JA/101/01'])
        self.assertEqual(parent['nominal_cents'],60131290203)
        self.assertEqual(remainder['nominal_cents']+child['nominal_cents'],parent['nominal_cents'])
        self.assertIn('Crédits!S730',exports.source_locators(remainder))

if __name__=='__main__':unittest.main()
