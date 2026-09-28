"""Real SQLite transaction, preservation and interrupted-activation tests on copies."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tools import vectorisation_numeric_integration as integration


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


class NumericIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.source = cls.base/'source'
        cls.bundle = cls.base/'addendum'
        before = cls.source/'structured/versions/before.sqlite'
        before.parent.mkdir(parents=True)
        con = sqlite3.connect(before)
        con.execute('CREATE TABLE facts(year INTEGER,stage TEXT,measure TEXT,cents INTEGER,source TEXT)')
        con.executemany('INSERT INTO facts VALUES(?,?,?,?,?)', ((2023,'LFI','AE',123,'s0') for _ in range(119746)))
        con.commit()
        con.close()
        cls.bundle.mkdir()
        incoming = cls.bundle/'budget.sqlite'
        shutil.copyfile(before, incoming)
        con = sqlite3.connect(incoming)
        for measure in ('AE','CP'):
            con.executemany('INSERT INTO facts VALUES(?,?,?,?,?)', ((2023,'FDC_PREVU',measure,0 if i%2 else None,'s1') for i in range(415)))
        con.commit()
        con.close()
        events = cls.source/'structured/versions/events.sqlite'
        con = sqlite3.connect(events)
        con.execute('CREATE TABLE events(program TEXT,measure TEXT,amount_cents INTEGER)')
        con.executemany('INSERT INTO events VALUES(?,?,?)', [('174','AE',0),('174','CP',None)])
        con.commit()
        con.close()
        historical = cls.source/'structured/budget.sqlite'
        shutil.copyfile(before, historical)
        cls.active = {'budget':{'path':before.relative_to(cls.source).as_posix(),'sha256':integration._sha(before),'records':119746},
                      'events':{'path':events.relative_to(cls.source).as_posix(),'sha256':integration._sha(events),'records':2},
                      'historical_budget':{'path':'structured/budget.sqlite','records':119746}}
        save(cls.source/'structured/active_stores.json', cls.active)
        save(cls.bundle/'support/preparation-active-stores-before.json', cls.active)
        mappings, links = [], []
        for index in range(58):
            source_id = 's'+str(index)
            digest = hashlib.sha256(source_id.encode()).hexdigest()
            shard = hashlib.sha256(('shard'+source_id).encode()).hexdigest()
            mappings.append({'store':'budget','source_id':source_id,'asset_sha256':digest,
                             'metadata_json':json.dumps({'id':source_id,'sha256':digest})})
            links.append({'source_id':source_id,'source_sha256':digest,'extraction_shard_sha256':shard})
        cls.links = links
        save(cls.bundle/'import-plan.json', {'expected_previous_budget':cls.active['budget'],
            'events_unchanged':cls.active['events'], 'new_budget':{'bundle_path':'budget.sqlite',
                'destination':'structured/versions/after.sqlite','sha256':integration._sha(incoming),'records':120576},
            'budget_numeric_source_map_upserts':mappings})
        audit, citations = [], []
        for name in integration.REGISTRIES:
            file = cls.bundle/'registries'/name
            save(file, {'name':name,'year':2023,'measure':'AE','value':None})
            audit.append({'registry':name,'sha256':integration._sha(file),'role':'sidecar_registry_not_additive_to_annual_facts'})
            citations.append({'registry':name,'pointer':'/0','source_field':'source','source_id':'s0',
                              'source_sha256':links[0]['source_sha256'],'locator':{'page':8}})
        save(cls.bundle/'source-links.json', {'sources':links,'missing_asset_source_ids':[],
            'not_indexed_source_ids':[],'registry_occurrences':citations})
        save(cls.bundle/'registry-audit.json', {'registries':audit})
        save(cls.bundle/'numeric-comparison.json', {'passed':True})
        cls.refresh_manifest(cls.bundle)
        cls.source_catalogue = cls.source/'nos_deniers.sqlite'
        con = sqlite3.connect(cls.source_catalogue)
        con.executescript('''CREATE TABLE assets(sha256 TEXT PRIMARY KEY);
            CREATE TABLE indexed(asset_sha256 TEXT PRIMARY KEY,shard_sha256 TEXT);
            CREATE TABLE extraction(asset_sha256 TEXT PRIMARY KEY,status TEXT,shard_sha256 TEXT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE numeric_source_map(store TEXT,source_id TEXT,asset_sha256 TEXT,metadata_json TEXT,PRIMARY KEY(store,source_id));''')
        for index, link in enumerate(links):
            con.execute('INSERT INTO assets VALUES(?)',(link['source_sha256'],))
            con.execute('INSERT INTO indexed VALUES(?,?)',(link['source_sha256'],link['extraction_shard_sha256']))
            con.execute('INSERT INTO extraction VALUES(?,?,?)',(link['source_sha256'],'complete',link['extraction_shard_sha256']))
            if index < 57:
                con.execute('INSERT INTO numeric_source_map VALUES(?,?,?,?)', ('budget',link['source_id'],link['source_sha256'],'{}'))
        con.execute("INSERT INTO numeric_source_map VALUES('events','event-source','events-hash','{}')")
        con.execute("INSERT INTO metadata VALUES('complement_manifest_sha256','historical-complement')")
        con.commit()
        con.close()

    @staticmethod
    def refresh_manifest(bundle):
        files = [{'path':p.relative_to(bundle).as_posix(),'bytes':p.stat().st_size,'sha256':integration._sha(p)}
                 for p in sorted(bundle.rglob('*')) if p.is_file() and p.name!='manifest.json']
        save(bundle/'manifest.json', {'schema':'nos-deniers-numeric-addendum-v1','release':'test-release','files':files})

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.generation = self.base/self._testMethodName
        self.generation.mkdir()
        self.catalogue = self.generation/'catalogue.sqlite'
        shutil.copyfile(self.source_catalogue,self.catalogue)

    def run_integration(self, bundle=None):
        return integration.integrate_numeric_addendum(self.catalogue,self.generation,bundle or self.bundle,self.source)

    def test_complete_and_repeated_integration_preserves_sources_and_history(self):
        before = {p:integration._sha(p) for p in self.source.rglob('*') if p.is_file()}
        first = self.run_integration()
        receipt_bytes = (self.generation/'numeric_addendum_receipt.json').read_bytes()
        second = self.run_integration()
        self.assertEqual(first,second)
        self.assertEqual(receipt_bytes,(self.generation/'numeric_addendum_receipt.json').read_bytes())
        self.assertEqual(before,{p:integration._sha(p) for p in self.source.rglob('*') if p.is_file()})
        active = integration._read(self.generation/'structured/active_stores.json')
        self.assertEqual(active['budget']['records'],120576)
        self.assertEqual(active['events'],self.active['events'])
        locations = integration._read(self.generation/first['addendum_files_map_path'])
        for item in locations.values():
            self.assertEqual(integration._sha(self.generation/item['generation_path']),item['sha256'])
        con = sqlite3.connect(self.catalogue)
        self.assertEqual(con.execute("SELECT count(*) FROM numeric_source_map WHERE store='budget'").fetchone()[0],58)
        self.assertEqual(con.execute('SELECT count(*) FROM numeric_registry_versions').fetchone()[0],9)
        self.assertEqual(con.execute('SELECT count(*) FROM numeric_registry_citations').fetchone()[0],9)
        self.assertEqual(con.execute("SELECT value FROM metadata WHERE key='complement_manifest_sha256'").fetchone()[0],'historical-complement')
        self.assertEqual(con.execute("SELECT asset_sha256 FROM numeric_source_map WHERE store='events'").fetchone()[0],'events-hash')
        con.close()

    def test_resume_after_sql_commit_before_activation_pointer(self):
        original = integration._write
        def fail_pointer(path,value):
            if path == (self.generation/'structured/active_stores.json').resolve():
                raise OSError('simulated interruption before pointer')
            original(path,value)
        with patch.object(integration,'_write',side_effect=fail_pointer):
            with self.assertRaisesRegex(OSError,'simulated'):
                self.run_integration()
        self.assertFalse((self.generation/'numeric_addendum_receipt.json').exists())
        con = sqlite3.connect(self.catalogue)
        self.assertIsNotNone(con.execute('SELECT value FROM metadata WHERE key=?',(integration.STAMP,)).fetchone())
        con.close()
        self.assertTrue(self.run_integration()['passed'])

    def test_conflicting_source_mapping_does_not_partially_write(self):
        con = sqlite3.connect(self.catalogue)
        con.execute("UPDATE numeric_source_map SET asset_sha256='wrong' WHERE source_id='s0'")
        con.commit()
        con.close()
        before = integration._sha(self.catalogue)
        with self.assertRaisesRegex(ValueError,'Conflicting existing numeric source'):
            self.run_integration()
        self.assertEqual(before,integration._sha(self.catalogue))
        self.assertFalse((self.generation/'numeric_addendum_receipt.json').exists())

    def test_transaction_rolls_back_on_registry_conflict(self):
        con = sqlite3.connect(self.catalogue)
        con.execute('CREATE TABLE numeric_registry_versions(registry_key TEXT PRIMARY KEY,relative_path TEXT,sha256 TEXT,bytes INTEGER,source_release TEXT,role TEXT,addendum_manifest_sha256 TEXT)')
        con.execute('INSERT INTO numeric_registry_versions VALUES(?,?,?,?,?,?,?)',(integration.REGISTRIES[0],'existing','wrong',1,'before','sidecar','before'))
        con.commit()
        con.close()
        with self.assertRaisesRegex(ValueError,'Conflicting registry'):
            self.run_integration()
        con = sqlite3.connect(self.catalogue)
        self.assertEqual(con.execute("SELECT count(*) FROM numeric_source_map WHERE store='budget'").fetchone()[0],57)
        self.assertIsNone(con.execute('SELECT value FROM metadata WHERE key=?',(integration.STAMP,)).fetchone())
        con.close()
        self.assertFalse((self.generation/'structured/active_stores.json').exists())

    def test_changed_ocr_shard_is_preserved_when_verified(self):
        new_shard = hashlib.sha256(b'new verified OCR').hexdigest()
        con = sqlite3.connect(self.catalogue)
        con.execute('UPDATE indexed SET shard_sha256=? WHERE asset_sha256=?',(new_shard,self.links[0]['source_sha256']))
        con.execute('UPDATE extraction SET shard_sha256=? WHERE asset_sha256=?',(new_shard,self.links[0]['source_sha256']))
        con.commit()
        con.close()
        result = self.run_integration()
        self.assertEqual(result['preserved_extraction_updates'][0]['current_shard_sha256'],new_shard)

    def test_modified_old_fact_is_rejected_even_with_updated_bundle_hashes(self):
        alternative = self.generation/'test-bundle'
        shutil.copytree(self.bundle,alternative)
        con = sqlite3.connect(alternative/'budget.sqlite')
        con.execute('UPDATE facts SET cents=456 WHERE rowid=1')
        con.commit()
        con.close()
        plan = integration._read(alternative/'import-plan.json')
        plan['new_budget']['sha256'] = integration._sha(alternative/'budget.sqlite')
        save(alternative/'import-plan.json',plan)
        self.refresh_manifest(alternative)
        # Keep the bundle outside the generation to satisfy the independent-output guard.
        moved = self.base/(self._testMethodName+'-bundle')
        shutil.move(str(alternative),moved)
        before = integration._sha(self.catalogue)
        with self.assertRaisesRegex(ValueError,'Old annual observations'):
            self.run_integration(moved)
        self.assertEqual(before,integration._sha(self.catalogue))

    def test_active_preparation_is_refused(self):
        with self.assertRaisesRegex(ValueError,'active preparation'):
            integration.integrate_numeric_addendum(self.source_catalogue,self.source,self.bundle,self.source)


if __name__ == '__main__':
    unittest.main()
