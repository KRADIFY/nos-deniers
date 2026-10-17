"""New internal credits use existing totals, including native multi-title parents."""
import copy
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from budget_service import action_details,api,cell_reviews,internal_details

SOURCE='a'*20
SHA='b'*64
PATH='EA/999/01'

class SourceDB:
    def __init__(self,changed=False):self.changed=changed
    def execute(self,sql,args):return self
    def fetchone(self):return (json.dumps({'sha256':'0'*64 if self.changed else SHA}),)

def fact(cents=200000000,subaction=''):
    return dict(year=2025,stage='PLF',measure='CP',budget='BG',mission='EA',
                mission_label='Mission de test',program='999',program_label='Programme de test',
                action='01',action_label='Action de test',subaction=subaction,
                subaction_label='Poste déjà présent' if subaction else '',title='',category='',
                cents=cents,source='c'*20,line=1,field='PLF CP',approximate=0)

def child(code,cents):
    return dict(code=code,label='Détail '+code,cents=cents,source=SOURCE,sha256=SHA,page=3,
                annual_label_variants=['Détail '+code],unit='EUR',unit_inferred=True,
                printed_unit=None,source_evidence=[dict(source=SOURCE,page=3)],
                source_description=dict(precision='Unité EUR déduite ; chiffres conservés.',
                                        document='PAP 2025',column='Total CP'))

def partition(rows,existing=False):
    fields=sorted(rows[0]);guard=[{k:r.get(k) for k in fields} for r in rows]
    children=([dict(code='01',cents=200000000,preserve_existing=True),child('02',0)]
              if existing else [child('01',120000000),child('02',80000000)])
    return dict(key=[2025,'PLF','CP','BG','EA','999','01'],path=PATH,kind='native_action_facts',
                parent_cents=200000000,fact_guard_fields=fields,
                program_facts_sha256=hashlib.sha256(internal_details._encode(guard).encode()).hexdigest(),
                source_dependencies=[dict(source=SOURCE,sha256=SHA)],children=children)

class InternalDetailTests(unittest.TestCase):
    def attach(self,rows,part,db=None):
        with patch.object(internal_details,'registry',return_value={tuple(part['key'][:-1]):[part]}):
            return internal_details.attach(copy.deepcopy(rows),db or SourceDB(),action_details.published_row)

    def cell(self,rows,scope=PATH,excluded=()):
        p=dict(api.parameters({}),scope=scope,exclude=list(excluded),start=2025,end=2025)
        return api.cell(rows,scope,2025,'PLF',p,{})

    def test_positive_details_preserve_parent_and_all_exclusion_forms(self):
        raw=[fact()];rows=self.attach(raw,partition(raw))
        self.assertEqual(self.cell(rows)['nominal_cents'],200000000)
        self.assertEqual(self.cell(rows,PATH+'/01')['nominal_cents'],120000000)
        one=self.cell(rows,excluded=[PATH+'/01'])
        self.assertEqual(one['nominal_cents'],80000000)
        self.assertEqual(one,self.cell(rows,excluded=[PATH+'/01',PATH+'/01']))
        for excluded in [[PATH,PATH+'/01'],[PATH+'/01',PATH+'/02']]:
            self.assertEqual(self.cell(rows,excluded=excluded)['value'],0)

    def test_native_existing_child_does_not_hide_a_new_zero_in_explorer(self):
        raw=[fact(subaction='01')];rows=self.attach(raw,partition(raw,existing=True))
        self.assertLess(len(list(action_details.navigation(rows))),10)
        p=dict(api.parameters({}),scope=PATH+'/02',start=2025,end=2025)
        meta=dict(indices={'2025':'100'},built_at='fixture')
        with sqlite3.connect(':memory:') as db,patch.object(api,'selected_records',return_value=cell_reviews.Records(rows,{})),patch.object(api,'metadata',return_value=meta):
            result=api.explorer(db,p)['totals'][0]['PLF']
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['nominal_cents'],0)
        self.assertEqual(self.cell(rows)['nominal_cents'],200000000)
        self.assertIsNone(self.cell(rows,PATH+'/99')['value'])

    def test_changed_canonical_fact_disables_new_details(self):
        raw=[fact()];part=partition(raw);changed=[fact(cents=200000001)]
        rows=self.attach(changed,part)
        self.assertEqual(self.cell(rows)['nominal_cents'],200000001)
        self.assertIsNone(self.cell(rows,PATH+'/01')['value'])

    def test_changed_primary_source_disables_new_details(self):
        raw=[fact()];rows=self.attach(raw,partition(raw),SourceDB(changed=True))
        self.assertEqual(self.cell(rows)['nominal_cents'],200000000)
        self.assertIsNone(self.cell(rows,PATH+'/01')['value'])

if __name__=='__main__':unittest.main()
