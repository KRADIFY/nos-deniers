"""Selection, exclusion and incomplete/rounded branches keep source amounts."""
import unittest
from budget_service import api,action_details

ROOT='VA/177/12'
def node(path,cents,children=(),partial=False):
 bits=path.split('/')
 r=dict(year=2026,stage='PLF',measure='CP',budget='BG',mission='VA',mission_label='Mission',
        program='177',program_label='Programme',action='12',action_label='Action',
        subaction=bits[3] if len(bits)>3 else '',subaction_label='Dispositif' if len(bits)>3 else '',
        budget_path=path,cents=cents,title='',category='',source='source',line=3,page=3,
        field='CP annuel',approximate=1,precision='Précision publiée conservée.',
        _reviewed_internal_node=True,_detail_note='Écart documentaire non réparti.')
 if children:r['_action_details']=list(children)
 if partial:r['_partial_action_coverage']=True
 return r

class ReviewedInternalTests(unittest.TestCase):
 def cell(self,tree,scope=ROOT,excluded=()):
  p=dict(api.parameters({}),start=2026,end=2026,scope=scope,exclude=list(excluded))
  return api.cell([tree],scope,2026,'PLF',p,{})
 def amount(self,c):return c.get('nominal_cents',0 if c['status']=='excluded' else None)
 def tree(self,partial=False):
  a=node(ROOT+'/01',60000000)
  b=node(ROOT+'/02',40000000,[node(ROOT+'/02/01',25000000),node(ROOT+'/02/02',15000000)])
  return node(ROOT,100000001,[a,b],partial)
 def test_complete_rounded_branch_does_not_distribute_the_cent(self):
  t=self.tree();self.assertEqual(self.amount(self.cell(t)),100000001)
  self.assertEqual(self.amount(self.cell(t,ROOT+'/01')),60000000)
  self.assertEqual(self.amount(self.cell(t,excluded=[ROOT+'/02'])),60000001)
  for excluded in [[ROOT+'/01',ROOT+'/02'],[ROOT+'/01',ROOT+'/02/01',ROOT+'/02/02']]:
   self.assertEqual(self.amount(self.cell(t,excluded=excluded)),0)
 def test_partial_branch_keeps_unexplained_remainder(self):
  self.assertEqual(self.amount(self.cell(self.tree(True),excluded=[ROOT+'/01',ROOT+'/02/01',ROOT+'/02/02'])),1)
 def test_duplicates_ancestors_and_permutations_do_not_double_subtract(self):
  t=self.tree();one=self.cell(t,excluded=[ROOT+'/02'])
  self.assertEqual(one,self.cell(t,excluded=[ROOT+'/02/01',ROOT+'/02',ROOT+'/02',ROOT+'/02/02']))
  self.assertEqual(self.amount(self.cell(t,ROOT+'/02/01',[ROOT+'/02'])),0)
 def test_partial_exclusions_cannot_invent_negative_remainder(self):
  t=node(ROOT,100,[node(ROOT+'/01',120),node(ROOT+'/02',30)],True)
  c=self.cell(t,excluded=[ROOT+'/01']);self.assertIsNone(c['value']);self.assertEqual(c['status'],'detail_unavailable')
 def test_complete_exclusion_precedes_negative_remainder_guard(self):
  t=node(ROOT,100,[node(ROOT+'/01',120),node(ROOT+'/02',30)])
  self.assertEqual(self.amount(self.cell(t,excluded=[ROOT+'/01',ROOT+'/02'])),0)
 def test_unknown_child_is_not_zero_or_complete(self):
  t=self.tree();self.assertIsNone(self.cell(t,ROOT+'/99')['value'])
  self.assertIsNone(self.cell(t,excluded=[ROOT+'/99'])['value'])
 def test_deep_paths_remain_bounded_and_numeric(self):
  self.assertEqual(api.valid_path(ROOT+'/04/01'),ROOT+'/04/01')
  for path in [ROOT+'/bad',ROOT+'/01'*6,ROOT+'/01?x=1']:
   with self.assertRaises(ValueError):api.valid_path(path)

if __name__=='__main__':unittest.main()
