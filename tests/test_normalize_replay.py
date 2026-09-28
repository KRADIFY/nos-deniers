import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from budget_service import normalize
from budget_service.normalize_replay import Replay, FIELDS, KEY_FIELDS, extend
from budget_service.normalize_validated import check_preserved


class SourceIdentityTests(unittest.TestCase):
    def test_explicit_id_is_kept_and_legacy_id_unchanged(self):
        record = {'path': 'public/source.pdf'}
        legacy = hashlib.sha256(record['path'].encode()).hexdigest()[:20]
        self.assertEqual(normalize.source_id(record), legacy)
        self.assertEqual(normalize.source_id(dict(record, id='f' * 20)), 'f' * 20)

    def test_invalid_ids_and_catalogue_collisions_are_rejected_before_import(self):
        for bad in (None, '', 'g' * 20, 'A' * 20, 'a' * 19, 123):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize.Importer([dict(path='a', id=bad)])
        record = dict(path='a')
        for records in ([record, dict(path='b', id=normalize.source_id(record))],
                        [record, dict(path='a', id='f' * 20)]):
            with self.assertRaises(ValueError):
                normalize.Importer(records)


class ReviewedReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = dict(path='old.csv', id='a'*20)
        self.new = dict(path='new.pdf', id='b'*20, pages=3)
        for source in (self.old, self.new):
            path = self.root / source['path']; path.write_bytes(source['path'].encode())
            source['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.before = dict(zip(FIELDS, (2023,'LFI','AE','BG','RD','Mission','200','Programme',
                                        '','','','','','HT2',100,self.old['id'],2,'LFI',1)))
        self.after = dict(self.before, cents=147, source=self.new['id'], line=3, field='RAP', approximate=0)
        self.change = dict(id='precision', before=self.before, after=self.after,
                           csv_evidence=dict(source=self.old['id'], sha256=self.old['sha256'], row=2),
                           rap_evidence=dict(source=self.new['id'], sha256=self.new['sha256'], page=3))

    def importer(self, rows=None):
        return SimpleNamespace(manifest=[self.old,self.new], facts=[tuple(r[k] for k in FIELDS) for r in (rows if rows is not None else [self.before])],
                               issues=[], reconciled_totals=[(2023,'LFI','AE','BG','RD',100,self.old['id'])], used=set())

    def state(self, rows=None):
        return Replay(self.importer(rows), self.root)

    def batch(self):
        scope = {k:self.after[k] for k in ('year','stage','measure','budget','mission')}
        ledger = dict(id='precision', independent_published_totals_modified=False,
                      fact_replacements=[self.change], fact_insertions=[],
                      affected_aggregate_adjustments=[dict(scope, previous_fact_sum_cents=100,
                          correction_cents=47, corrected_fact_sum_cents=147, correction_ids=['precision'])])
        return dict(id='precision', ledger_meta_key='recent_reconciliation_corrections', ledger=ledger)

    def test_replacement_is_exact_idempotent_and_preserves_independent_total(self):
        state = self.state(); before_totals = copy.deepcopy(state.totals)
        self.assertEqual(state.change(self.change), 'replaced')
        self.assertEqual(state.change(self.change), 'already_present')
        self.assertEqual(state.facts, [tuple(self.after[k] for k in FIELDS)])
        self.assertEqual(state.totals, before_totals)
        self.assertEqual(len(state.verified),2)

    def test_changed_before_missing_before_and_duplicate_before_are_refused(self):
        for rows in ([dict(self.before,cents=101)], [], [self.before,self.before]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.state(rows).change(self.change)

    def test_physical_source_sha_and_proof_page_are_mandatory(self):
        (self.root/self.new['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'fichier source'):
            self.state().change(self.change)
        (self.root/self.new['path']).write_bytes(self.new['path'].encode())
        bad = copy.deepcopy(self.change);bad['rap_evidence']['page']=2
        with self.assertRaisesRegex(ValueError, 'Page/ligne'):
            self.state().change(bad)
        bad = copy.deepcopy(self.change);bad['csv_evidence']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError, 'catalogue'):
            self.state().change(bad)

    def test_future_candidate_amount_and_measure_must_match_its_proof(self):
        for extra in ({'amount_cents':148},{'measure':'CP'},{'euros':1.48}):
            change=copy.deepcopy(self.change);change['rap_evidence'].update(extra)
            with self.subTest(extra=extra),self.assertRaisesRegex(ValueError,'preuve|euros'):
                self.state().change(change)

    def test_archived_proof_path_keeps_exact_source_id_and_hash(self):
        change=copy.deepcopy(self.change)
        change['csv_evidence']['path']='archive/copy-of-original.csv'
        self.assertEqual(self.state().change(change),'replaced')

    def test_broad_absence_key_blocks_action_and_title_double_count(self):
        insertion = dict(id='whole-program', after=dict(self.after,title=''), proof=self.change['rap_evidence'],
                         absence_key_fields=['year','budget','program','stage','measure'])
        for existing in (self.before, dict(self.before, action='01', title='2',mission='ZZ')):
            with self.subTest(existing=existing), self.assertRaisesRegex(ValueError,'Absence'):
                self.state([existing]).change(insertion)
        state=self.state([])
        self.assertEqual(state.change(insertion),'inserted')
        self.assertEqual(state.change(insertion),'already_present')

    def test_aggregate_adjustment_cannot_be_a_tolerance(self):
        state=self.state();state.batch(self.batch())
        self.assertEqual(state.totals[0][5],100)
        invalid=self.batch();invalid['ledger']['affected_aggregate_adjustments'][0]['correction_cents']=46
        with self.assertRaisesRegex(ValueError,'Ajustement'):
            self.state().batch(invalid)

    def test_replayed_fact_must_match_the_complete_predecessor(self):
        state=self.state();state.change(self.change)
        with sqlite3.connect(':memory:') as db:
            db.execute('create table facts('+','.join(FIELDS)+')')
            db.execute('insert into facts values('+','.join('?'for _ in FIELDS)+')',tuple(self.after[k]for k in FIELDS))
            with self.assertRaisesRegex(ValueError,'Base servie conservée'):
                check_preserved(db,self.importer().facts)
            check_preserved(db,state.facts)
        db.close()

    def minimal_plan(self):
        names=('pap-ecologie-2026.json','pap-2026-national.json','rap-explicit-zeros.json','rap-investigation.json')
        for name in names:(self.root/name).write_text('{}',encoding='utf8')
        shas={name:hashlib.sha256((self.root/name).read_bytes()).hexdigest()for name in names}
        receipts={'pap2026_ecology':{},'pap2026_national':{'plan_sha256':shas[names[1]]},
                  'rap_explicit_zeros':{'plan_sha256':shas[names[2]]},'rap_investigation':{}}
        plan=dict(version='validated-fact-replay-1', plan_sha256s=shas, receipts=receipts,
                  source_evidence=[], correction_batches=[self.batch()])
        path=self.root/'validated-fact-replay.json';path.write_text(json.dumps(plan),encoding='utf8')
        return plan,path

    def test_failed_extension_leaves_importer_unchanged_and_drops_no_unknown_receipt(self):
        self.minimal_plan();importer=self.importer();saved=copy.deepcopy(importer.__dict__)
        with patch('budget_service.normalize_replay.replay_standard_plans'), self.assertRaisesRegex(ValueError,'sans adaptateur'):
            extend(importer,self.root,previous_meta={'new_validated_import':{'facts':3}},plan_dir=self.root)
        self.assertEqual(importer.__dict__,saved)

    def test_receipts_are_preserved_only_after_replay_and_plan_sha_check(self):
        plan,path=self.minimal_plan();importer=self.importer()
        previous=copy.deepcopy(plan['receipts']);previous['recent_reconciliation_corrections']=plan['correction_batches'][0]['ledger']
        with patch('budget_service.normalize_replay.replay_standard_plans'):
            extend(importer,self.root,previous_meta=previous,plan_dir=self.root)
        for key,value in previous.items():self.assertEqual(importer.replayed_meta[key],value)
        saved=copy.deepcopy(importer.__dict__)
        (self.root/'rap-investigation.json').write_text('{"changed":true}',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'Plan modifié'):
            extend(importer,self.root,plan_dir=self.root)
        self.assertEqual(importer.__dict__,saved)

    def test_save_replays_before_preservation_and_writes_receipts_only_to_fixture(self):
        plan,_=self.minimal_plan()
        derived=self.root/'derived';derived.mkdir();target=derived/'budget.sqlite'
        previous=copy.deepcopy(plan['receipts'])
        previous['recent_reconciliation_corrections']=plan['correction_batches'][0]['ledger']
        with sqlite3.connect(target)as db:
            db.execute('create table facts('+','.join(FIELDS)+')')
            db.execute('insert into facts values('+','.join('?'for _ in FIELDS)+')',tuple(self.after[k]for k in FIELDS))
            db.execute('create table meta(key text,value text)')
            db.executemany('insert into meta values(?,?)',[(k,json.dumps(v))for k,v in previous.items()])
        db.close()
        importer=normalize.Importer([self.old,self.new])
        importer.facts=[tuple(self.before[k]for k in FIELDS)]
        def replay_candidate(importer,data,previous_meta):
            return extend(importer,data,previous_meta=previous_meta,plan_dir=self.root)
        with patch.object(normalize,'DATA',self.root),patch('budget_service.normalize_replay.extend',side_effect=replay_candidate),patch('budget_service.normalize_replay.replay_standard_plans'),patch('builtins.print'):
            importer.save()
        with sqlite3.connect(target)as db:
            self.assertEqual(db.execute('select *from facts').fetchall(),[tuple(self.after[k]for k in FIELDS)])
            actual={k:json.loads(v)for k,v in db.execute('select *from meta')}
            for key,value in previous.items():self.assertEqual(actual[key],value)
        db.close()
        self.assertEqual(len(list((derived/'rebuild-backups').glob('*/budget.sqlite'))),1)

    def test_save_refuses_empty_predecessor_before_creating_a_database(self):
        importer=normalize.Importer([])
        with patch.object(normalize,'DATA',self.root), self.assertRaisesRegex(ValueError,'vierge non certifiée'):
            importer.save()
        self.assertFalse((self.root/'derived/budget.sqlite').exists())
        self.assertFalse((self.root/'derived/budget.build.sqlite').exists())


if __name__=='__main__':unittest.main()
