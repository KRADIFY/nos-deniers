"""Integration receipt: reconstruct in temporary storage, never replace the served DB."""
import json
import sqlite3
import tempfile
from pathlib import Path
from budget_service import normalize
from budget_service.normalize_more import extend
from budget_service.normalize_validated import extend as replay
from budget_service.normalize_replay import ROUTINE_META

original=normalize.DATA
manifest=json.loads((normalize.INPUTS/'MANIFEST-COLLECTE.json').read_text(encoding='utf-8-sig'))
importer=normalize.Importer(manifest)
importer.nomenclatures();importer.import_tables();extend(importer);replay(importer)
with tempfile.TemporaryDirectory(prefix='nos-deniers-rebuild-') as temp:
    root=Path(temp);(root/'derived').mkdir()
    for item in original.iterdir():
        if item.name!='derived':(root/item.name).symlink_to(item,target_is_directory=item.is_dir())
    with sqlite3.connect((original/'derived/budget.sqlite').as_uri()+'?mode=ro',uri=True) as db, sqlite3.connect(root/'derived/budget.sqlite') as copy:
        expected=db.execute('select count(*) from facts').fetchone()[0]
        expected_totals=set(db.execute('select * from reconciled_totals'))
        expected_sources={sid:json.loads(value)['sha256'] for sid,value in db.execute('select id,data from sources')}
        expected_receipts={k:json.loads(v) for k,v in db.execute('select key,value from meta') if k not in ROUTINE_META}
        db.backup(copy)
    normalize.DATA=root
    importer.save()
    with sqlite3.connect(root/'derived/budget.sqlite') as db:
        actual=db.execute('select count(*) from facts').fetchone()[0]
        assert actual==expected
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert db.execute('select count(*) from published_nodes').fetchone()[0]>0
        assert set(db.execute('select * from reconciled_totals'))==expected_totals
        assert {sid:json.loads(value)['sha256'] for sid,value in db.execute('select id,data from sources')}==expected_sources
        meta={k:json.loads(v) for k,v in db.execute('select * from meta')}
        assert sum(meta['stats'].values())==actual
        for key,value in expected_receipts.items():assert meta[key]==value,(key,'receipt changed')
    print(json.dumps(dict(rebuilt_facts=actual,preserved_facts=expected,served_database_modified=False,temporary_restore_checked=True)))
